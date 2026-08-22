"""Analogue engine (Phase B core). The honest cousin of "what if":
represent each month as the vector of all node states plus the synoptic
state, retrieve the most similar historical months, and report what
followed them, labeled as history.

Registered before estimation:
Similarity between months = weighted share of matching node states
(oil weight 2, others 1, synoptic 1.5; nodes without data in either
month excluded from numerator and denominator). Analogue retrieval
excludes the 12 months on either side of the query month.

Registered check, scored once, published as it falls:
  AN1 Crisis months resemble crisis months: define the crisis set as
      2008-09..2009-03 and 2020-02..2020-05. For each month in that
      set, retrieve the top 5 analogues leave-one-out (excluding own
      window plus/minus 12 months). Averaged over crisis months, at
      least 60 percent of retrieved analogues must themselves lie in
      the crisis set.
"""

import numpy as np
import pandas as pd

# The registered rule is "oil weight 2, others 1, synoptic 1.5". This
# map is the roster at weight 1; any node not listed is an "other" and
# takes the registered default, so the panel can grow without the
# similarity rule changing.
OTHER_W = 1.0
W = {"oil": 2.0, "gas": 1.0, "dollar": 1.0, "credit": 1.0,
     "curve": 1.0, "real_yield": 1.0, "breakevens": 1.0, "copper": 1.0,
     "coal": 1.0, "uranium": 1.0, "euro": 1.0, "yen": 1.0,
     "yuan": 1.0, "sterling": 1.0, "em_dollar": 1.0, "activity": 1.0,
     "housing": 1.0, "money": 1.0,
     "inflation": 1.0, "equities": 1.0, "gold": 1.0, "synoptic": 1.5}


def state_table(preds, syn_series, months):
    rows = {}
    for n, s in preds.items():
        rows[n] = [s.get(m) for m in months]
    rows["synoptic"] = [syn_series.get(str(m)) for m in months]
    return pd.DataFrame(rows, index=months)


def similarity(tab, i, j):
    got = tot = 0.0
    for n in tab.columns:
        a, b = tab.iloc[i][n], tab.iloc[j][n]
        if not (isinstance(a, str) and isinstance(b, str)):
            continue
        w = W.get(n, OTHER_W)
        tot += w
        if a == b:
            got += w
    return got / tot if tot > 0 else 0.0


def analogues(tab, i, k=5, exclude=12):
    sims = []
    for j in range(len(tab)):
        if abs(j - i) <= exclude:
            continue
        sims.append((j, similarity(tab, i, j)))
    sims.sort(key=lambda x: -x[1])
    return sims[:k]


def followed(months, j, real_brent, pred_oil, horizon=3):
    m = months[j]
    fut = pred_oil.loc[m + 1:m + horizon]
    lp = np.log(real_brent)
    r = None
    if m in lp.index and (m + horizon) in lp.index:
        r = round(float((lp.loc[m + horizon] - lp.loc[m]) * 100), 1)
    return {"month": str(m), "then_oil": list(fut.values),
            "real_return_3m_pct": r}


def run(preds, syn_series, months, real_brent):
    tab = state_table(preds, syn_series, months)
    # AN1
    crisis = list(pd.period_range("2008-09", "2009-03", freq="M")) + \
        list(pd.period_range("2020-02", "2020-05", freq="M"))
    crisis_set = set(crisis)
    shares = []
    for m in crisis:
        if m not in months:
            continue
        i = list(months).index(m)
        top = analogues(tab, i, k=5)
        inset = sum(1 for j, _ in top if months[j] in crisis_set)
        shares.append(inset / 5)
    avg = float(np.mean(shares)) if shares else None
    an1 = {"id": "AN1", "value": round(avg, 3) if avg is not None
           else None, "hit": bool(avg is not None and avg >= 0.60)}
    # current analogues
    i = len(tab) - 1
    top = analogues(tab, i, k=5)
    cur = [{"month": str(months[j]), "similarity": round(s, 2),
            **followed(months, j, real_brent, preds["oil"])}
           for j, s in top]
    return {"check": an1, "current_analogues": cur,
            "asof": str(months[-1])}
