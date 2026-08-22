"""Hazard layer (v2 wave 1). Replaces price prediction, which failed and
stays retired. Two honest forward-facing objects, both conditional
history: regime episode durations, and the risk lamp, the frequency of
large drawdowns given the current oil regime.

Registered before estimation:
  Episodes: maximal runs of the same decoded oil state, full sample.
  Durations reported for states with at least 5 episodes as median and
  range, plus the continuation rate at the current episode's elapsed
  length (share of historical episodes of that state that lasted
  strictly longer).
  Risk lamp: for each oil regime, the share of months in that regime
  from which the minimum forward real Brent return over the next 3
  months was -15 percent or worse, against the unconditional share.
Registered checks, published as they fall:
  RL1 The squeeze lamp re-test: conditional share for supply_squeeze at
      least 1.5 times the unconditional share (the one robust finding
      of the failed prediction stage, re-tested under the spliced
      deflator).
  DUR1 Stability: for every state with at least 5 episodes on each side
      of 2016-01, the post-2016 median duration lies within 0.5x to
      2.0x the pre-2016 median.
"""

import numpy as np
import pandas as pd


def episodes(pred):
    out = []
    cur, start = None, None
    for m, v in pred.items():
        if v != cur:
            if cur is not None:
                out.append((cur, start, (m - start).n))
            cur, start = v, m
    out.append((cur, start, (pred.index[-1] - start).n + 1))
    return [(s, str(a), int(l)) for s, a, l in out]


def run(pred_oil, real_brent):
    eps = episodes(pred_oil)
    by = {}
    for s, a, l in eps:
        by.setdefault(s, []).append((a, l))
    cur_state = pred_oil.iloc[-1]
    cur_len = by[cur_state][-1][1]
    dur = {}
    for s, lst in by.items():
        L = [l for _, l in lst]
        if len(L) < 5:
            continue
        longer = sum(1 for _, l in lst[:-1] if l > cur_len) \
            if s == cur_state else None
        past = lst[:-1] if s == cur_state else lst
        cont = (round(sum(1 for _, l in past if l > cur_len)
                      / max(len(past), 1), 2) if s == cur_state else None)
        dur[s] = {"episodes": len(L), "median": float(np.median(L)),
                  "min": min(L), "max": max(L),
                  "continuation_at_current": cont}
    # risk lamp
    logp = np.log(real_brent)
    fwd_min = pd.Series(index=logp.index, dtype=float)
    for i, m in enumerate(logp.index):
        w = logp.iloc[i + 1:i + 4]
        if len(w) == 3:
            fwd_min[m] = float((w - logp.iloc[i]).min())
    thr = np.log(1 - 0.15)
    joint = pd.DataFrame({"state": pred_oil, "fmin": fwd_min}).dropna()
    uncond = float((joint["fmin"] <= thr).mean())
    lamp = {}
    for s in joint["state"].unique():
        sub = joint[joint["state"] == s]
        if len(sub) >= 24:
            lamp[s] = {"months": int(len(sub)),
                       "tail_freq": round(float(
                           (sub["fmin"] <= thr).mean()), 3)}
    lamp["unconditional"] = round(uncond, 3)
    # registered checks
    sq = lamp.get("supply_squeeze", {}).get("tail_freq")
    rl1 = {"id": "RL1", "value": {"squeeze": sq, "uncond": lamp[
        "unconditional"]},
        "hit": bool(sq is not None and sq >= 1.5 * uncond)}
    cut = pd.Period("2016-01", "M")
    dur1_details, ok = {}, True
    for s, lst in by.items():
        pre = [l for a, l in lst if pd.Period(a, "M") < cut]
        post = [l for a, l in lst if pd.Period(a, "M") >= cut]
        if len(pre) >= 5 and len(post) >= 5:
            r = float(np.median(post) / np.median(pre))
            dur1_details[s] = round(r, 2)
            ok = ok and 0.5 <= r <= 2.0
    dur1 = {"id": "DUR1", "value": dur1_details,
            "hit": bool(ok if dur1_details else None)}
    return {"episodes": len(eps), "durations": dur,
            "current": {"state": cur_state, "elapsed": int(cur_len)},
            "lamp": lamp, "checks": [rl1, dur1]}
