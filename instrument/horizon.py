"""HORIZON-1: where the edge ends.

Registered as HORIZON-1 before this ran. Forecaster M is re-issued at
every adjudication month over history using data through that month
only, on the CAL-1 pattern, and scored by ranked probability skill
score against climatology at leads 1 through 12. The published result
is the pooled mean skill by lead and the first lead at which that mean
is at or below zero.

Causality, as registered: each pseudo-issue fits on the causal decoded
history through its own month, starts from the causal posterior at that
month, and is scored against the states the full record later settled
on. Climatology is computed from the same causal history, so the
baseline is causal too.

Ordering for the ranked probability score, fixed in the registration:
states sorted by family code, calm before easing before up before
strained before hot, ties broken by state name.

Where the edge ends is descriptive. Nothing is published or withheld on
the strength of it.
"""

import numpy as np
import pandas as pd

from instrument import calibration as cal
from instrument.outlook import HORIZONS, N_PATHS, semi_markov, simulate

MIN_HISTORY = 60
LEADS = list(range(1, 13))

from instrument.families import FAM_CODE


def order_states(states):
    """The registered category order for the ranked probability score."""
    return sorted(states, key=lambda s: (FAM_CODE.get(s, 9), s))


def rps(dist, observed, order):
    """Ranked probability score over the registered ordering."""
    k = len(order)
    if k < 2 or observed not in order:
        return None
    f = np.array([float(dist.get(s, 0.0)) for s in order])
    tot = f.sum()
    if tot <= 0:
        return None
    f = f / tot
    o = np.zeros(k)
    o[order.index(observed)] = 1.0
    return float(np.sum((np.cumsum(f) - np.cumsum(o)) ** 2) / (k - 1))


def audit_instrument(name, spec, seed, leads=None, min_history=MIN_HISTORY,
                     n_paths=N_PATHS):
    """Causal pseudo-issues for one instrument. Returns per lead the
    forecast and climatology scores, one pair per pseudo-issue."""
    leads = leads or LEADS
    X = np.asarray(spec["X"], float).copy()
    X[~np.isfinite(X)] = np.nan
    idx = spec["index"]
    states = spec["states"]
    causal = spec["hmm"].filtered(X)
    smoothed = spec["hmm"].posteriors(X)
    truth = [states[i] for i in smoothed.argmax(1)]
    cstate = [states[i] for i in causal.argmax(1)]
    pv = spec["primary"].dropna()
    last = len(idx) - 1
    if len(pv):
        pos = np.where(idx == pv.index[-1])[0]
        if len(pos):
            last = int(pos[0])
    rng = np.random.default_rng(seed)
    order = order_states(states)
    out = {L: {"f": [], "c": [], "p": []} for L in leads}
    issues = 0
    hi = last - max(leads)
    for i in range(min_history - 1, hi + 1):
        seq = cstate[:i + 1]
        if len(set(seq)) < 2:
            continue
        sm = semi_markov(seq)
        if sm is None:
            continue
        post_now = {states[j]: float(causal[i, j])
                    for j in range(len(states))}
        try:
            dist, _ = simulate(sm, seq, post_now, rng, n_paths=n_paths,
                               horizons=leads)
        except Exception:
            continue
        vc = pd.Series(seq).value_counts(normalize=True)
        clim = {str(k): float(v) for k, v in vc.items()}
        # HORIZON-2: persistence is a point mass on the causal state at
        # the issue month, carried unchanged to every lead. Deterministic,
        # so it consumes no randomness and cannot perturb the forecasts.
        pers = {seq[-1]: 1.0}
        issues += 1
        for L in leads:
            obs = truth[i + L]
            a = rps(dist.get(L, {}), obs, order)
            b = rps(clim, obs, order)
            c2 = rps(pers, obs, order)
            if a is None or b is None or c2 is None:
                continue
            out[L]["f"].append(a)
            out[L]["c"].append(b)
            out[L]["p"].append(c2)
    return {"instrument": name, "issues": issues,
            "states": len(states),
            "per_lead": {str(L): {"f": out[L]["f"], "c": out[L]["c"],
                                  "p": out[L]["p"]}
                         for L in leads}}


def pool(rows, leads=None, baseline="c"):
    """Skill by lead and the lead where the edge ends.

    The published statistic is the one registered: the mean across
    instruments of each instrument's own skill score at that lead. The
    sum-pooled score is reported beside it, since the two answer
    slightly different questions and the difference between them is
    itself worth seeing."""
    leads = leads or LEADS
    curve = []
    for L in leads:
        per_inst = []
        for r in rows:
            f = r["per_lead"][str(L)]["f"]
            c = r["per_lead"][str(L)].get(baseline) or []
            if f and c and sum(c) > 0:
                per_inst.append((r["instrument"],
                                 1.0 - float(np.sum(f)) / float(np.sum(c))))
        f = [v for r in rows for v in r["per_lead"][str(L)]["f"]]
        c = [v for r in rows
             for v in (r["per_lead"][str(L)].get(baseline) or [])]
        if not per_inst or not f or sum(c) <= 0:
            curve.append({"lead": L, "n": 0, "rpss": None})
            continue
        vals = [v for _n, v in per_inst]
        curve.append({"lead": L, "n": len(f),
                      "instruments": len(per_inst),
                      "rpss": round(float(np.mean(vals)), 4),
                      "rpss_sum_pooled": round(
                          1.0 - float(np.sum(f)) / float(np.sum(c)), 4),
                      "rpss_worst_instrument": round(
                          float(np.min(vals)), 4),
                      "rps_forecast": round(float(np.mean(f)), 5),
                      "rps_baseline": round(float(np.mean(c)), 5),
                      "per_instrument": {n: round(v, 4)
                                         for n, v in per_inst}})
    ends = None
    for row in curve:
        if row["rpss"] is not None and row["rpss"] <= 0:
            ends = row["lead"]
            break
    # per-instrument crossing leads: the first lead at which that
    # instrument's own skill is at or below zero
    cross = {}
    for r in rows:
        cross[r["instrument"]] = None
        for row in curve:
            v = (row.get("per_instrument") or {}).get(r["instrument"])
            if v is not None and v <= 0:
                cross[r["instrument"]] = row["lead"]
                break
    seen = [v for v in cross.values() if v is not None]
    spread = (max(seen) - min(seen)) if len(seen) > 1 else 0
    return {"curve": curve, "edge_ends_at_lead": ends,
            "baseline": baseline,
            "per_instrument_crossing": cross,
            "crossing_spread_leads": spread,
            "crossing_materially_different": bool(spread >= 3
                                                  or (seen and
                                                      len(seen) < len(rows))),
            "instruments": len(rows),
            "issues": int(sum(r["issues"] for r in rows)),
            "leads": list(leads)}
