"""Explicit-duration hidden semi-Markov machinery.

A vanilla HMM implies a geometric sojourn: a one-day stay costs the
same per day as a hundred-day stay, which is what makes a daily
regime decoder chatter. This module gives each state its own duration
distribution, so short stays are expensive inside the model rather
than being discouraged after the fact.

Duration law: d = d_min + NegBin(r, p), so no stay shorter than d_min
is representable at all. Emissions are diagonal Gaussian with missing
dimensions masked, never imputed. Everything is estimated by
expectation maximization; nothing here is tuned by hand.

Conventions: time is 0-indexed over T observations, K states, F
features. All recursions are in log space.
"""

import numpy as np


def _lse(a, axis=-1):
    m = np.max(a, axis=axis, keepdims=True)
    m = np.where(np.isfinite(m), m, 0.0)
    return (m + np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True))
            ).squeeze(axis)


def negbin_logpmf(d_grid, r, p, d_min):
    """log P(d) for d = d_min + NegBin(r, p), zero below d_min."""
    from scipy.special import gammaln
    m = d_grid - d_min
    out = np.full(d_grid.shape, -np.inf)
    ok = m >= 0
    mm = m[ok]
    out[ok] = (gammaln(mm + r) - gammaln(r) - gammaln(mm + 1.0)
               + r * np.log(p) + mm * np.log1p(-p))
    return out


def emission_loglik(X, mu, var):
    """(T, K) diagonal Gaussian log-likelihood, NaN dimensions masked."""
    T, F = X.shape
    K = mu.shape[0]
    obs = ~np.isnan(X)
    Xz = np.where(obs, X, 0.0)
    out = np.zeros((T, K))
    for k in range(K):
        z = (Xz - mu[k]) ** 2 / var[k]
        c = np.log(2.0 * np.pi * var[k])
        out[:, k] = -0.5 * np.sum(obs * (c + z), axis=1)
    return out


class HSMM:
    def __init__(self, mu, var, A, r, p, d_min=5, d_max=250, pi=None):
        self.mu = np.asarray(mu, float)
        self.var = np.asarray(var, float)
        self.A = np.asarray(A, float)
        self.r = np.asarray(r, float)
        self.p = np.asarray(p, float)
        self.d_min = int(d_min)
        self.d_max = int(d_max)
        K = self.mu.shape[0]
        self.pi = (np.full(K, 1.0 / K) if pi is None
                   else np.asarray(pi, float))

    # ------------------------------------------------------- internals
    def _duration_tables(self):
        K = self.mu.shape[0]
        d_grid = np.arange(1, self.d_max + 1)
        logpd = np.stack([negbin_logpmf(d_grid, self.r[k], self.p[k],
                                        self.d_min) for k in range(K)])
        pd = np.exp(logpd)
        rowsum = pd.sum(1, keepdims=True)
        pd = pd / np.maximum(rowsum, 1e-300)
        logpd = np.log(np.maximum(pd, 1e-300))
        # survival: S[k, m] = P(d >= m), m = 1..d_max
        tail = np.cumsum(pd[:, ::-1], axis=1)[:, ::-1]
        logS = np.log(np.maximum(tail, 1e-300))
        return logpd, logS

    def _cumemit(self, logb):
        T, K = logb.shape
        Cb = np.zeros((K, T + 1))
        Cb[:, 1:] = np.cumsum(logb.T, axis=1)
        return Cb

    def _forward(self, logb, logpd, logS):
        """A_end[t, k]: a segment of k ends at day t-1. Ain[u, k]: a
        segment of k starts at day u. Both causal."""
        T, K = logb.shape
        D = self.d_max
        Cb = self._cumemit(logb)
        logA = np.log(np.maximum(self.A, 1e-300))
        np.fill_diagonal(logA, -np.inf)
        A_end = np.full((T + 1, K), -np.inf)
        Ain = np.full((T + 1, K), -np.inf)
        Ain[0] = np.log(np.maximum(self.pi, 1e-300))
        for t in range(1, T + 1):
            dmax = min(D, t)
            ds = np.arange(1, dmax + 1)
            starts = t - ds                       # (dmax,)
            emit = Cb[:, t][:, None] - Cb[:, starts]      # (K, dmax)
            val = logpd[:, :dmax] + emit + Ain[starts].T  # (K, dmax)
            A_end[t] = _lse(val, axis=1)
            if t < T:
                Ain[t] = _lse(A_end[t][:, None] + logA, axis=0)
        # censored likelihood: the final segment may still be running
        term = np.full(K, -np.inf)
        dmax = min(D, T)
        ds = np.arange(1, dmax + 1)
        starts = T - ds
        emit = Cb[:, T][:, None] - Cb[:, starts]
        term = _lse(logS[:, :dmax] + emit + Ain[starts].T, axis=1)
        logZ = _lse(term)
        return A_end, Ain, Cb, logZ, logA

    def _backward(self, logb, logpd, logS, Cb, logA):
        T, K = logb.shape
        D = self.d_max
        Bin = np.full((T + 1, K), -np.inf)
        Bend = np.full((T + 1, K), -np.inf)
        Bend[T] = 0.0
        for t in range(T - 1, -1, -1):
            dmax = min(D, T - t)
            ds = np.arange(1, dmax + 1)
            ends = t + ds
            emit = Cb[:, ends] - Cb[:, t][:, None]
            val = logpd[:, :dmax] + emit + Bend[ends].T
            # censored tail: a segment that outlives the sample, which
            # needs P(d > T - t) and is impossible once the remaining
            # span already reaches the maximum representable duration
            rem = T - t
            if rem < D:
                cens = logS[:, rem] + (Cb[:, T] - Cb[:, t])
            else:
                cens = np.full(K, -np.inf)
            Bin[t] = _lse(np.concatenate(
                [val, cens[:, None]], axis=1), axis=1)
            Bend[t] = _lse(logA + Bin[t][None, :], axis=1)
        return Bin, Bend

    # ------------------------------------------------------------- EM
    def _estep(self, X, logb):
        T, K = logb.shape
        D = self.d_max
        logpd, logS = self._duration_tables()
        A_end, Ain, Cb, logZ, logA = self._forward(logb, logpd, logS)
        Bin, Bend = self._backward(logb, logpd, logS, Cb, logA)
        diff = np.zeros((K, T + 2))
        durc = np.zeros((K, D))
        for t in range(0, T):
            dmax = min(D, T - t)
            ds = np.arange(1, dmax + 1)
            ends = t + ds
            emit = Cb[:, ends] - Cb[:, t][:, None]
            w = np.exp(Ain[t][:, None] + logpd[:, :dmax] + emit
                       + Bend[ends].T - logZ)
            if not np.any(w):
                continue
            durc[:, :dmax] += w
            diff[:, t] += w.sum(1)
            np.add.at(diff, (slice(None), ends), -w)
        gamma = np.cumsum(diff[:, :T], axis=1).T
        gamma = np.clip(gamma, 0.0, None)
        rs = gamma.sum(1, keepdims=True)
        gamma = gamma / np.maximum(rs, 1e-300)
        xi = np.zeros((K, K))
        for u in range(1, T):
            xi += np.exp(A_end[u][:, None] + logA + Bin[u][None, :]
                         - logZ)
        pic = np.exp(np.log(np.maximum(self.pi, 1e-300)) + Bin[0] - logZ)
        return gamma, durc, xi, pic, logZ

    def _mstep(self, X, gamma, durc, xi, pic):
        K, F = self.mu.shape
        obs = ~np.isnan(X)
        Xz = np.where(obs, X, 0.0)
        for k in range(K):
            wk = gamma[:, k][:, None] * obs
            den = np.maximum(wk.sum(0), 1e-8)
            self.mu[k] = (wk * Xz).sum(0) / den
            v = (wk * (Xz - self.mu[k]) ** 2).sum(0) / den
            self.var[k] = np.maximum(v, 1e-3)
        rows = xi.sum(1, keepdims=True)
        A = np.where(rows > 0, xi / np.maximum(rows, 1e-300), 0.0)
        np.fill_diagonal(A, 0.0)
        rows = A.sum(1, keepdims=True)
        bad = (rows.ravel() <= 0)
        if bad.any():
            fill = np.full((K, K), 1.0 / max(K - 1, 1))
            np.fill_diagonal(fill, 0.0)
            A[bad] = fill[bad]
            rows = A.sum(1, keepdims=True)
        self.A = A / np.maximum(rows, 1e-300)
        d_grid = np.arange(1, self.d_max + 1)
        m_grid = d_grid - self.d_min
        for k in range(K):
            w = durc[k]
            tot = w.sum()
            if tot <= 0:
                continue
            mean = float((w * m_grid).sum() / tot)
            var = float((w * (m_grid - mean) ** 2).sum() / tot)
            mean = max(mean, 1e-3)
            if var > mean * 1.0001:
                self.r[k] = max(mean ** 2 / (var - mean), 0.05)
                self.p[k] = min(max(self.r[k] / (self.r[k] + mean),
                                    1e-4), 0.9999)
            else:
                self.r[k] = 1000.0
                self.p[k] = min(max(1000.0 / (1000.0 + mean), 1e-4),
                                0.9999)
        s = pic.sum()
        if s > 0:
            self.pi = pic / s

    def fit(self, X, max_iter=60, tol=1e-5, verbose=False):
        prev = None
        hist = []
        for it in range(max_iter):
            logb = emission_loglik(X, self.mu, self.var)
            gamma, durc, xi, pic, logZ = self._estep(X, logb)
            self._mstep(X, gamma, durc, xi, pic)
            hist.append(float(logZ))
            if verbose:
                print(f"  EM {it + 1:3d}  loglik {logZ:,.2f}")
            if prev is not None and abs(logZ - prev) <= tol * abs(prev):
                break
            prev = logZ
        self.loglik_history = hist
        self.iterations = len(hist)
        return self

    # -------------------------------------------------------- decoding
    def filtered(self, X):
        """P(S_t = k | observations through day t). Causal: day t uses
        no data after day t."""
        logb = emission_loglik(X, self.mu, self.var)
        T, K = logb.shape
        D = self.d_max
        logpd, logS = self._duration_tables()
        A_end, Ain, Cb, logZ, logA = self._forward(logb, logpd, logS)
        out = np.zeros((T, K))
        for t in range(T):
            mmax = min(D, t + 1)
            ms = np.arange(1, mmax + 1)
            starts = t - ms + 1
            emit = Cb[:, t + 1][:, None] - Cb[:, starts]
            val = logS[:, :mmax] + emit + Ain[starts].T
            lp = _lse(val, axis=1)
            lp -= _lse(lp)
            out[t] = np.exp(lp)
        return out

    def map_segmentation(self, X):
        """Viterbi over segments. Unlike the filtered marginal this
        returns an actual segmentation, so every run it produces
        respects the model's minimum stay by construction."""
        logb = emission_loglik(X, self.mu, self.var)
        T, K = logb.shape
        D = self.d_max
        logpd, logS = self._duration_tables()
        Cb = self._cumemit(logb)
        logA = np.log(np.maximum(self.A, 1e-300))
        np.fill_diagonal(logA, -np.inf)
        NEG = -np.inf
        delta = np.full((T + 1, K), NEG)
        bk_d = np.zeros((T + 1, K), int)
        bk_s = np.full((T + 1, K), -1, int)
        ent = np.full((T + 1, K), NEG)
        ent[0] = np.log(np.maximum(self.pi, 1e-300))
        for t in range(1, T + 1):
            dmax = min(D, t)
            ds = np.arange(1, dmax + 1)
            starts = t - ds
            emit = Cb[:, t][:, None] - Cb[:, starts]
            val = logpd[:, :dmax] + emit + ent[starts].T
            bi = np.argmax(val, axis=1)
            delta[t] = val[np.arange(K), bi]
            bk_d[t] = ds[bi]
            for k in range(K):
                u = t - bk_d[t, k]
                if u == 0:
                    bk_s[t, k] = -1
                else:
                    cand = delta[u] + logA[:, k]
                    bk_s[t, k] = int(np.argmax(cand))
            if t < T:
                for k in range(K):
                    cand = delta[t] + logA[:, k]
                    ent[t, k] = np.max(cand)
        # the final segment is censored: score it by survival
        dmax = min(D, T)
        ds = np.arange(1, dmax + 1)
        starts = T - ds
        emit = Cb[:, T][:, None] - Cb[:, starts]
        val = logS[:, :dmax] + emit + ent[starts].T
        flat = int(np.argmax(val))
        k = flat // dmax
        d = int(ds[flat % dmax])
        out = np.zeros(T, int)
        t = T
        while t > 0:
            out[t - d:t] = k
            u = t - d
            if u <= 0:
                break
            k = int(np.argmax(delta[u] + logA[:, k]))
            d = int(bk_d[u, k])
            t = u
        return out
