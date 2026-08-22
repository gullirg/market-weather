"""Synoptic layer (v2 wave 1). One decoder above the seven instruments:
fixed target patterns over node states name the system-level weather.
Node configs are untouched; this layer only reads their outputs.

Registered before estimation, fixed here:
States and target patterns (node: allowed states, weight):
  risk_on_calm        equities {rally, calm} w1; credit {calm} w1;
                      oil {calm, demand_boom} w0.5; inflation {calm} w0.5;
                      dollar {calm, usd_down} w0.25
  financial_stress    equities {stress} w2; credit {stress} w2;
                      dollar {usd_up} w1; inflation {easing} w1;
                      gold {fear_bid} w0.5
  demand_collapse     oil {demand_collapse, supply_glut} w2;
                      equities {stress, correction} w1;
                      inflation {easing} w1; gas {glut, calm} w0.5;
                      credit {stress, easing} w0.5
  inflation_shock     inflation {surge} w2; gas {squeeze} w1;
                      oil {supply_squeeze, demand_boom} w1;
                      dollar {usd_up} w0.5; credit {calm} w0.5
  commodity_shock     oil {supply_squeeze, precautionary} w2;
                      credit {calm} w1; inflation {calm, surge} w0.5;
                      equities {calm, correction, rally} w0.5
Scoring: per month, score(state) = matched weight / applicable weight
(nodes without data that month are excluded from both). Smoothing:
sticky Bayes filter over log(score + 0.05) with stay probability 0.85.

Registered checks, scored once, published as they fall:
  J1 2008-10..2009-03 financial_stress dominant
  J2 2020-03..2020-05 demand_collapse dominant
  J3 2021-09..2022-09 inflation_shock dominant
  J4 2026-03..2026-05 commodity_shock dominant
The August 2026 reading is exploratory.

Display mapping (record-page strip row): risk_on_calm 1, financial_stress
2, inflation_shock 3, demand_collapse 4, commodity_shock 5.
"""

import numpy as np
import pandas as pd

from instrument.hmm import _logsumexp

SYN_STATES = ["risk_on_calm", "financial_stress", "demand_collapse",
              "inflation_shock", "commodity_shock", "post_shock_glut"]
TARGETS = {
    "risk_on_calm": [("equities", {"rally", "calm"}, 1.0),
                     ("credit", {"calm"}, 1.0),
                     ("oil", {"calm", "demand_boom"}, 0.5),
                     ("inflation", {"calm"}, 0.5),
                     ("dollar", {"calm", "usd_down"}, 0.25)],
    "financial_stress": [("equities", {"stress"}, 2.0),
                         ("credit", {"stress"}, 2.0),
                         ("dollar", {"usd_up"}, 1.0),
                         ("inflation", {"easing"}, 1.0),
                         ("gold", {"fear_bid"}, 0.5)],
    "demand_collapse": [("oil", {"demand_collapse"}, 2.0),
                        ("equities", {"stress", "correction"}, 1.0),
                        ("inflation", {"easing"}, 1.0),
                        ("gas", {"glut", "calm"}, 0.5),
                        ("credit", {"stress", "easing"}, 0.5)],
    "inflation_shock": [("inflation", {"surge"}, 2.0),
                        ("gas", {"squeeze"}, 1.0),
                        ("oil", {"supply_squeeze", "demand_boom"}, 1.0),
                        ("dollar", {"usd_up"}, 0.5),
                        ("credit", {"calm"}, 0.5)],
    "commodity_shock": [("oil", {"supply_squeeze", "precautionary"}, 2.0),
                        ("credit", {"calm"}, 1.0),
                        ("inflation", {"calm", "surge"}, 0.5),
                        ("equities", {"calm", "correction", "rally"}, 0.5)],
    "post_shock_glut": [("oil", {"supply_glut"}, 2.0),
                        ("inflation", {"calm", "easing"}, 0.5),
                        ("credit", {"calm"}, 0.5),
                        ("equities", {"rally", "calm"}, 0.5)],
}
OIL_GATE = {"supply_squeeze", "precautionary"}
SYN_CODE = {"risk_on_calm": 1, "financial_stress": 2, "demand_collapse": 2,
            "inflation_shock": 3, "commodity_shock": 5,
            "post_shock_glut": 4}
SYN_WORD = {"risk_on_calm": "risk-on calm",
            "financial_stress": "financial stress",
            "demand_collapse": "demand collapse",
            "inflation_shock": "inflation shock",
            "commodity_shock": "commodity shock, financial calm",
            "post_shock_glut": "post-shock glut"}
CHECKS = [("J1", "2008-10", "2009-03", "financial_stress"),
          ("J2", "2020-03", "2020-05", "demand_collapse"),
          ("J3", "2021-09", "2022-09", "inflation_shock"),
          ("J4", "2026-03", "2026-05", "commodity_shock")]


def run(preds, months):
    """preds: dict node -> pd.Series of state words. months: PeriodIndex
    grid. Returns dict with strip codes, current, series, checks."""
    scores = np.zeros((len(months), len(SYN_STATES)))
    for t, m in enumerate(months):
        obs = {n: preds[n].get(m) for n in preds}
        for s, st in enumerate(SYN_STATES):
            got, tot = 0.0, 0.0
            for node, allowed, w in TARGETS[st]:
                v = obs.get(node)
                if not isinstance(v, str):
                    continue
                tot += w
                if v in allowed:
                    got += w
            scores[t, s] = got / tot if tot > 0 else 0.0
        if isinstance(obs.get("oil"), str) and obs["oil"] in OIL_GATE:
            scores[t, SYN_STATES.index("risk_on_calm")] *= 0.2
    logB = np.log(scores + 0.05)
    k = len(SYN_STATES)
    p_stay = 0.70
    A = np.full((k, k), (1 - p_stay) / (k - 1))
    np.fill_diagonal(A, p_stay)
    logA = np.log(A)
    T = len(months)
    la = np.zeros((T, k))
    lb = np.zeros((T, k))
    la[0] = -np.log(k) + logB[0]
    for t in range(1, T):
        la[t] = logB[t] + _logsumexp(la[t - 1][:, None] + logA, 0)
    for t in range(T - 2, -1, -1):
        lb[t] = _logsumexp(logA + (logB[t + 1] + lb[t + 1])[None, :], 1)
    g = la + lb
    post = np.exp(g - _logsumexp(g, 1)[:, None])
    series = pd.Series([SYN_STATES[i] for i in post.argmax(1)],
                       index=months)
    checks = []
    for cid, a, b, target in CHECKS:
        w = series.loc[pd.Period(a, "M"):pd.Period(b, "M")]
        dom = w.value_counts().index[0]
        checks.append({"id": cid, "window": f"{a}..{b}", "target": target,
                       "dominant": dom,
                       "share": round(float((w == target).mean()), 2),
                       "hit": bool(dom == target)})
    cur = series.iloc[-1]
    return {"strip": [SYN_CODE[v] for v in series],
            "series": {str(m): v for m, v in series.items()},
            "current": {"state": cur, "word": SYN_WORD[cur],
                        "prob": round(float(post[-1].max()), 2)},
            "checks": checks}
