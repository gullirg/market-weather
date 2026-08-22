"""OUTLOOK v1, the forecast layer, registered as OUTLOOK-REG before any
estimate existed. Nothing in this module may be changed after a quarter
has been scored against it.

The decoded present is the analysis. The forecast is the outlook.

Registered form, restated here so the code and the chain entry can be
read side by side:

1. Forecaster M, Markov. Per instrument a semi-Markov transition
   structure: empirical duration distributions per state, a
   duration-dependent exit hazard, and a next-state distribution
   conditional on exit. Re-estimated once per quarter on full history.
   Horizons 1 to 12 months, by forward simulation of 2000 sampled
   paths from the current posterior. Synoptic occupancy additionally
   as the discounted successor representation over the joint decoded
   synoptic series, discount 0.9.
2. Forecaster A, analogue ensemble. The top K of 20 analogues of the
   current joint state under the registered analogue weights, with the
   existing 12 month exclusion window, then the empirical distribution
   of states at each horizon.
3. Baselines. Persistence, the current state with probability one at
   every horizon. Climatology, the unconditional state frequencies
   over full history.
4. Scoring happens at quarter end against decoded realizations, never
   here. This module issues forecasts and freezes them.

Implementation choices the registration did not fix, recorded here
because they are load bearing:

a. The exit hazard is right-censoring aware. The final run of a series
   is still in progress, so it contributes to the survivor denominator
   at each duration it reached but never to the exit numerator.
b. Durations beyond the longest observed run for a state reuse that
   state's overall exit rate, so a simulated path can always leave.
c. A path that starts in a state other than the analysis state starts
   with an elapsed duration of one month, since the posterior gives no
   duration for a state the analysis did not select.
d. The random seed is derived from the asof month, so a rebuild of the
   same month reproduces the same forecast exactly.
"""

import hashlib
import json

import numpy as np
import pandas as pd

from instrument import analogue

HORIZONS = list(range(1, 13))
K_ANALOGUE = 20
EXCLUDE_M = 12
N_PATHS = 2000
SR_DISCOUNT = 0.9


def seed_for(asof):
    """Deterministic seed from the asof month, so builds are idempotent."""
    h = hashlib.sha256(f"outlook-v1:{asof}".encode()).hexdigest()
    return int(h[:8], 16)


def quarter_of(asof):
    p = pd.Period(asof, "M")
    return f"{p.year}Q{(p.month - 1) // 3 + 1}"


def _runs(seq):
    """[(state, length), ...] over a list of state labels."""
    out = []
    for s in seq:
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1])
    return [(s, n) for s, n in out]


def semi_markov(seq):
    """Duration-dependent exit hazards and the exit transition matrix."""
    runs = _runs(seq)
    states = sorted({s for s, _ in runs})
    idx = {s: i for i, s in enumerate(states)}
    k = len(states)
    if not runs:
        return None
    dmax = max(n for _, n in runs)
    exits = np.zeros((k, dmax + 1))
    surv = np.zeros((k, dmax + 1))
    for j, (s, n) in enumerate(runs):
        censored = (j == len(runs) - 1)
        i = idx[s]
        for d in range(1, n + 1):
            surv[i, d] += 1
        if not censored:
            exits[i, n] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        haz = np.where(surv > 0, exits / np.maximum(surv, 1e-12), 0.0)
    # fallback rate per state: completed exits over total months lived
    lived = np.zeros(k)
    done = np.zeros(k)
    for j, (s, n) in enumerate(runs):
        lived[idx[s]] += n
        if j < len(runs) - 1:
            done[idx[s]] += 1
    fallback = np.where(lived > 0, done / np.maximum(lived, 1e-12), 1.0)
    fallback = np.clip(fallback, 1e-4, 1.0)
    nxt = np.zeros((k, k))
    for a, b in zip(runs[:-1], runs[1:]):
        nxt[idx[a[0]], idx[b[0]]] += 1
    rows = nxt.sum(1, keepdims=True)
    nxt = np.where(rows > 0, nxt / np.maximum(rows, 1e-12), 1.0 / k)
    return {"states": states, "idx": idx, "haz": haz, "dmax": dmax,
            "fallback": fallback, "next": nxt, "runs": runs}


def _start_duration(seq, state):
    """Elapsed months of the run in progress, if it is in `state`."""
    if not seq or seq[-1] != state:
        return 1
    d = 0
    for s in reversed(seq):
        if s != state:
            break
        d += 1
    return d


def simulate(sm, seq, post_now, rng, n_paths=N_PATHS,
             horizons=HORIZONS):
    """Forward simulation from the current posterior. Returns a dict
    horizon -> {state: probability}."""
    states = sm["states"]
    k = len(states)
    p0 = np.array([float(post_now.get(s, 0.0)) for s in states])
    if p0.sum() <= 0:
        p0 = np.zeros(k)
        p0[sm["idx"].get(seq[-1], 0)] = 1.0
    p0 = p0 / p0.sum()
    cur = rng.choice(k, size=n_paths, p=p0)
    analysis = seq[-1] if seq else None
    dur0 = _start_duration(seq, analysis)
    dur = np.where(cur == sm["idx"].get(analysis, -1), dur0, 1)
    cnxt = np.cumsum(sm["next"], axis=1)
    hmax = max(horizons)
    out = {}
    for h in range(1, hmax + 1):
        dcap = np.minimum(dur, sm["dmax"])
        hz = sm["haz"][cur, dcap]
        hz = np.where(hz > 0, hz, sm["fallback"][cur])
        leaving = rng.random(n_paths) < hz
        if leaving.any():
            u = rng.random(int(leaving.sum()))
            rowc = cnxt[cur[leaving]]
            picked = (u[:, None] < rowc).argmax(1)
            cur = cur.copy()
            cur[leaving] = picked
            dur = dur + 1
            dur[leaving] = 1
        else:
            dur = dur + 1
        if h in horizons:
            cnt = np.bincount(cur, minlength=k).astype(float)
            out[h] = {states[i]: round(float(cnt[i] / n_paths), 4)
                      for i in range(k) if cnt[i] > 0}
    return out


def climatology(seq):
    s = pd.Series(seq)
    v = s.value_counts(normalize=True)
    return {str(i): round(float(x), 4) for i, x in v.items()}


def persistence(seq):
    return {seq[-1]: 1.0} if seq else {}


def analogue_ensemble(tab, months, series, node, k=K_ANALOGUE,
                      exclude=EXCLUDE_M, horizons=HORIZONS):
    """Empirical distribution of what followed the K nearest analogues
    of the current joint state. Uses the registered analogue weights
    and exclusion window."""
    i = len(tab) - 1
    top = analogue.analogues(tab, i, k=k, exclude=exclude)
    out = {}
    for h in horizons:
        tally = {}
        n = 0
        for j, _sim in top:
            t = j + h
            if t >= len(months):
                continue
            st = series.get(months[t])
            if not isinstance(st, str):
                continue
            tally[st] = tally.get(st, 0) + 1
            n += 1
        if n:
            out[h] = {s: round(c / n, 4) for s, c in tally.items()}
        else:
            out[h] = {}
    return out, len(top)


def successor_representation(seq, discount=SR_DISCOUNT):
    """Discounted occupancy from the current state, (I - gP)^-1 row."""
    states = sorted(set(seq))
    idx = {s: i for i, s in enumerate(states)}
    k = len(states)
    P = np.zeros((k, k))
    for a, b in zip(seq[:-1], seq[1:]):
        P[idx[a], idx[b]] += 1
    rows = P.sum(1, keepdims=True)
    P = np.where(rows > 0, P / np.maximum(rows, 1e-12), 1.0 / k)
    M = np.linalg.inv(np.eye(k) - discount * P)
    row = M[idx[seq[-1]]]
    row = row / row.sum()
    return {states[i]: round(float(row[i]), 4) for i in range(k)}


def _series_list(pred):
    s = pred.dropna()
    return [x for x in s.tolist() if isinstance(x, str)], s.index


def run(preds, posts, syn_series, months, asof, issued=None):
    """Issue the outlook. Scores nothing."""
    rng = np.random.default_rng(seed_for(asof))
    mlist = list(months)
    tab = analogue.state_table(preds, syn_series, months)
    out = {"asof": str(asof), "quarter": quarter_of(asof),
           "issued": issued, "horizons": list(HORIZONS),
           "k_analogue": K_ANALOGUE, "exclusion_months": EXCLUDE_M,
           "paths": N_PATHS, "sr_discount": SR_DISCOUNT,
           "seed": seed_for(asof), "instruments": {}, "synoptic": None,
           "registration": "OUTLOOK-REG"}
    for name in sorted(preds):
        seq, _ix = _series_list(preds[name])
        if len(seq) < 24:
            continue
        sm = semi_markov(seq)
        if sm is None:
            continue
        po = posts.get(name)
        post_now = {}
        if po is not None and len(po):
            row = po.iloc[-1]
            post_now = {str(c): float(row[c]) for c in po.columns}
        m = simulate(sm, seq, post_now, rng)
        a, nk = analogue_ensemble(tab, mlist, preds[name], name)
        out["instruments"][name] = {
            "states": sm["states"],
            "analysis": {"state": seq[-1],
                         "elapsed_months": _start_duration(seq, seq[-1])},
            "M": {str(h): m.get(h, {}) for h in HORIZONS},
            "A": {str(h): a.get(h, {}) for h in HORIZONS},
            "climatology": climatology(seq),
            "persistence": persistence(seq),
            "analogues_used": nk}
    sseq = [syn_series.get(str(p)) for p in months]
    sseq = [x for x in sseq if isinstance(x, str)]
    if len(sseq) >= 24:
        sm = semi_markov(sseq)
        m = simulate(sm, sseq, {sseq[-1]: 1.0}, rng)
        sser = pd.Series(
            {p: syn_series.get(str(p)) for p in months})
        a, nk = analogue_ensemble(tab, mlist, sser, "synoptic")
        out["synoptic"] = {
            "states": sm["states"],
            "analysis": {"state": sseq[-1],
                         "elapsed_months": _start_duration(sseq, sseq[-1])},
            "M": {str(h): m.get(h, {}) for h in HORIZONS},
            "A": {str(h): a.get(h, {}) for h in HORIZONS},
            "climatology": climatology(sseq),
            "persistence": persistence(sseq),
            "sr_occupancy": successor_representation(sseq),
            "analogues_used": nk}
    return out
