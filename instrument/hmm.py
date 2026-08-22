"""Masked-template HMM machinery, ported unchanged from the validated
stage 1-6 pipeline. State meanings live in the templates; nothing here
is fitted except per-state diagonal spreads with means held fixed."""

import numpy as np
import pandas as pd


def rolling_z(s, window=120, min_periods=36):
    mu = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std()
    return (s - mu) / sd


def _logsumexp(a, axis):
    m = np.max(a, axis=axis, keepdims=True)
    return (m + np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True))
            ).squeeze(axis)


class TemplateHMM:
    """Fixed-mean, unit-sigma masked Gaussian HMM."""

    def __init__(self, templates, p_stay=0.90):
        self.mu = np.asarray(templates, float)
        self.k = self.mu.shape[0]
        A = np.full((self.k, self.k), (1 - p_stay) / (self.k - 1))
        np.fill_diagonal(A, p_stay)
        self.logA = np.log(A)

    def _loglik(self, X):
        T, d = X.shape
        L = np.zeros((T, self.k))
        for t in range(T):
            m = ~np.isnan(X[t])
            if m.sum() == 0:
                continue
            diff = X[t, m][None, :] - self.mu[:, m]
            L[t] = (-0.5 * (diff ** 2).sum(1)) / m.sum() * d
        return L

    def posteriors(self, X):
        logB = self._loglik(np.asarray(X, float))
        T = logB.shape[0]
        la = np.zeros((T, self.k))
        lb = np.zeros((T, self.k))
        la[0] = -np.log(self.k) + logB[0]
        for t in range(1, T):
            la[t] = logB[t] + _logsumexp(la[t - 1][:, None] + self.logA, 0)
        for t in range(T - 2, -1, -1):
            lb[t] = _logsumexp(self.logA + (logB[t + 1] + lb[t + 1])[None, :],
                               1)
        g = la + lb
        return np.exp(g - _logsumexp(g, 1)[:, None])


class SigmaHMM(TemplateHMM):
    def __init__(self, templates, sigmas, p_stay=0.90):
        super().__init__(templates, p_stay=p_stay)
        self.sig = np.asarray(sigmas, float)

    def _loglik(self, X):
        T, d = X.shape
        L = np.zeros((T, self.k))
        for t in range(T):
            m = ~np.isnan(X[t])
            if m.sum() == 0:
                continue
            diff = (X[t, m][None, :] - self.mu[:, m]) / self.sig[:, m]
            L[t] = (-0.5 * (diff ** 2).sum(1)
                    - np.log(self.sig[:, m]).sum(1)) / m.sum() * d
        return L


def em_sigmas(X, idx, templates, p_stay=0.90, iters=8, anchors=None,
              floor=0.5, cap=2.5):
    """Per-state diagonal sigmas, means fixed; anchored months clamped in
    the E-step only."""
    X = np.asarray(X, float).copy()
    X[~np.isfinite(X)] = np.nan
    k, d = templates.shape
    sig = np.ones((k, d))
    A = np.full((k, k), (1 - p_stay) / (k - 1))
    np.fill_diagonal(A, p_stay)
    logA = np.log(A)
    anchor_pos = {}
    if anchors:
        for mth, s in anchors.items():
            p = pd.Period(mth, "M")
            if p in idx:
                anchor_pos[list(idx).index(p)] = s
    for _ in range(iters):
        T = X.shape[0]
        logB = np.zeros((T, k))
        for t in range(T):
            m = ~np.isnan(X[t])
            if m.sum() == 0:
                continue
            diff = (X[t, m][None, :] - templates[:, m]) / sig[:, m]
            logB[t] = (-0.5 * (diff ** 2).sum(1)
                       - np.log(sig[:, m]).sum(1)) / m.sum() * d
        for pos, s in anchor_pos.items():
            logB[pos] += np.where(np.arange(k) == s, 0.0, -50.0)
        la = np.zeros((T, k))
        lb = np.zeros((T, k))
        la[0] = -np.log(k) + logB[0]
        for t in range(1, T):
            la[t] = logB[t] + _logsumexp(la[t - 1][:, None] + logA, 0)
        for t in range(T - 2, -1, -1):
            lb[t] = _logsumexp(logA + (logB[t + 1] + lb[t + 1])[None, :], 1)
        g = la + lb
        g = np.exp(g - _logsumexp(g, 1)[:, None])
        for s in range(k):
            for j in range(d):
                m = ~np.isnan(X[:, j])
                w = g[m, s]
                if w.sum() < 5:
                    continue
                v = ((X[m, j] - templates[s, j]) ** 2 * w).sum() / w.sum()
                sig[s, j] = np.clip(np.sqrt(v), floor, cap)
    return sig
