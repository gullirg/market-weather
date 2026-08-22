"""The nervous-system registry (roadmap phases B and C, architecture).

Every capillary instrument is a declarative spec: source CSV, feature
construction, fixed templates, states, and REGISTERED held-out checks.
Membership rule, registered before any estimation: an instrument joins
the public network only by passing at least 2 of its 3 registered
checks, all results published on the chain whichever way they fall.
An entry whose CSV is absent stays a declared spec: adding the file is
the entire joining procedure (plus its one scored run).

Registered specs and checks, fixed here before estimation:

curve: GS10 minus GS2, monthly. Features: level z (240m, min 60),
  3m change z (120m, min 36). States calm [0,0], inversion
  [-1.3, -0.6], steepening [1.0, 0.8].
  CU1 2006-09..2007-05 inversion dominant.
  CU2 2019-06..2019-09 inversion present.
  CU3 2009-01..2010-12 steepening dominant.

real_yield: FII10, 2003+. Features: level z (240m, min 36), 3m change
  z (120m, min 24). States calm [0,0], real_tightening [0.8, 1.2],
  real_easing [-0.8, -1.2].
  RY1 2013-05..2013-09 real_tightening dominant (taper).
  RY2 2022-03..2022-10 real_tightening dominant.
  RY3 2020-03..2020-12 real_easing dominant.

breakevens: T10YIEM, 2003+. Features: level z (240m, min 36), 3m
  change z (120m, min 24). States calm [0,0], reflation [0.7, 1.0],
  deflation_scare [-1.2, -1.4].
  BE1 2008-09..2008-12 deflation_scare dominant.
  BE2 2021-01..2021-05 reflation dominant.
  BE3 2020-03..2020-04 deflation_scare present.

copper: PCOPPUSDM real (spliced deflator), 1992+. Features: 3m real
  momentum z (120m, min 24), 12m real momentum z (120m, min 24).
  States calm [0,0], boom [0.9, 1.0], bust [-1.0, -1.1].
  CO1 2003-10..2006-06 boom dominant.
  CO2 2008-10..2009-03 bust dominant.
  CO3 2014-09..2016-02 bust dominant.

Awaiting data (spec complete, CSV absent, host fetch):
em_dollar: TWEXEMEGSMTH. calm/em_stress[0.9,0.9]/em_bid[-0.9,-0.8];
  EM1 2008-09..2009-03 em_stress dominant; EM2 2014-07..2016-01
  em_stress dominant; EM3 2020-03..2020-04 em_stress present.
activity: WEI weekly to monthly mean. calm/expansion[1.0,0.8]/
  contraction[-1.2,-1.0]; AC1 2020-03..2020-06 contraction dominant;
  AC2 2021-03..2021-06 expansion dominant; AC3 2008-10..2009-06
  contraction dominant.
housing: HOUST. calm/boom[0.9,0.8]/bust[-1.1,-0.9]; HS1 2006-06..
  2009-06 bust dominant; HS2 2020-04..2020-05 bust present; HS3
  2012-10..2013-12 boom present.
money: M2SL yoy. calm/expansion[1.3,1.0]/contraction[-1.2,-0.9];
  M2a 2020-04..2021-02 expansion dominant; M2b 2022-12..2023-12
  contraction dominant (two checks; membership 2 of 2).

Tree leaves added for the composition hierarchy (registered before
estimation; joining rule unchanged, 2 of 3):
coal: PCOALAUUSDM real (spliced deflator), momentum features as
  copper. calm/boom[0.9,1.0]/bust[-1.0,-1.1].
  CL1 2008-01..2008-09 boom dominant. CL2 2020-03..2020-08 bust
  present. CL3 2021-06..2022-09 boom dominant.
uranium: PURANUSDM real, momentum as copper, prices the nuclear
  fuel cycle. calm/boom[0.9,1.0]/bust[-1.0,-1.1].
  UR1 2006-06..2007-07 boom dominant. UR2 2011-04..2012-12 bust
  dominant. UR3 2023-06..2024-02 boom dominant.
euro: EXUSEU, features 3m and 12m change z of 100*log, up = euro
  strong. calm/euro_strong[0.9,0.9]/euro_weak[-0.9,-0.9].
  EU1 2010-05..2010-06 euro_weak present. EU2 2014-09..2015-03
  euro_weak dominant. EU3 2017-05..2017-12 euro_strong dominant.
Awaiting (spec complete, CSV absent): yen EXJPUS (sign flipped so up
  = yen strong; JP1 2008-09..2009-01 yen_strong dom, JP2 2012-11..
  2013-05 yen_weak dom, JP3 2022-03..2022-10 yen_weak dom); yuan
  EXCHUS from 2006 only, pre-reform peg excluded by construction
  (CN1 2015-08..2016-12 yuan_weak dom, CN2 2020-07..2021-05
  yuan_strong dom, CN3 2022-04..2022-10 yuan_weak dom); the 2006
  start is enforced in build by YUAN_START, since a decade of hard
  peg has no dispersion for rolling_z to divide by; sterling
  EXUSUK (GB1 2008-08..2009-01 gbp_weak dom, GB2 2016-06..2016-10
  gbp_weak dom, GB3 2022-09 gbp_weak present).

Registered in the host campaign, before the first decode of this node
(rule: states, templates and three held-out checks fixed in this file
and chained, then one scored run, then the 2 of 3 membership rule
unchanged):
claims: ICSA weekly to monthly mean, feature series -100*log(claims)
  so that up means an improving labour market, exactly the sign
  convention `activity` uses. Features: level z (240m, min 60),
  3m change z (120m, min 36). States calm [0,0], expansion
  [1.0, 0.8], contraction [-1.2, -1.0], templates copied from
  `activity` because the two instruments measure the same object at
  different frequencies. Block: activity.
  CJ1 2008-11..2009-06 contraction dominant (the GFC layoff wave).
  CJ2 2020-03..2020-05 contraction present (the Covid claims
      explosion).
  CJ3 2022-01..2022-06 expansion present (claims at multi-decade
      lows through the post-Covid labour shortage).
  Checks chosen from labour-market history alone; the series was not
  decoded before they were written and chained.

Blocks (registered): energy {oil, gas}; rates_expectations {curve,
real_yield, breakevens, inflation}; credit {credit}; fx {dollar,
em_dollar}; equities {equities}; metals {gold, copper}; activity
{activity, housing}; liquidity {money}. Block series = equal-weight
mean of available member primary features. Sparse instrument map:
rolling 96-month GFEVD stepped 6 months on the joint sample; an edge
is drawn only if it reaches 3 percent in at least 70 percent of
windows (stability selection).
"""

import numpy as np
import pandas as pd

from instrument.hmm import TemplateHMM, rolling_z
from instrument import nodes

YUAN_START = pd.Period("2006-01", "M")

CODES = {"calm": 0, "boom": 1, "steepening": 1, "reflation": 1,
         "expansion": 1, "em_bid": 1, "real_easing": 2, "bust": 2,
         "deflation_scare": 2, "contraction": 2, "inversion": 5,
         "real_tightening": 3, "em_stress": 3, "euro_strong": 1,
         "euro_weak": 2, "yen_strong": 1, "yen_weak": 2,
         "yuan_strong": 1, "yuan_weak": 2, "gbp_strong": 1,
         "gbp_weak": 2}
WORDS = {"calm": "calm", "inversion": "inversion",
         "euro_strong": "euro strong", "euro_weak": "euro weak",
         "yen_strong": "yen strong", "yen_weak": "yen weak",
         "yuan_strong": "yuan strong", "yuan_weak": "yuan weak",
         "gbp_strong": "sterling strong",
         "gbp_weak": "sterling weak",
         "steepening": "steepening", "real_tightening": "real tightening",
         "real_easing": "real easing", "reflation": "reflation",
         "deflation_scare": "deflation scare", "boom": "boom",
         "bust": "bust", "em_stress": "EM stress", "em_bid": "EM bid",
         "expansion": "expansion", "contraction": "contraction"}


def _lvl_chg(series, lvl_w=240, lvl_m=60, chg_w=120, chg_m=36):
    return pd.DataFrame({
        "lvl": rolling_z(series, lvl_w, lvl_m),
        "chg": rolling_z(series.diff(3), chg_w, chg_m)})


def _mom(series, defl):
    lp = np.log(series / defl.reindex(series.index).ffill())
    return pd.DataFrame({
        "m3": rolling_z(lp.diff(3), 120, 24),
        "m12": rolling_z(lp.diff(12), 120, 24)})


REGISTRY = {
    "curve": {
        "block": "rates_expectations",
        "build": lambda F, defl: _lvl_chg(
            (F["gs10"] - F["_gs2"]).dropna()),
        "needs": ["gs2.csv"],
        "states": ["calm", "inversion", "steepening"],
        "T": [[0.0, 0.0], [-1.3, -0.6], [1.0, 0.8]],
        "checks": [("CU1", "2006-09", "2007-05", "inversion", "dom"),
                   ("CU2", "2019-06", "2019-09", "inversion", "pres"),
                   ("CU3", "2009-01", "2010-12", "steepening", "dom")]},
    "real_yield": {
        "block": "rates_expectations",
        "build": lambda F, defl: _lvl_chg(F["_ry10"].dropna(),
                                          lvl_m=36, chg_m=24),
        "needs": ["real_yield10.csv"],
        "states": ["calm", "real_tightening", "real_easing"],
        "T": [[0.0, 0.0], [0.8, 1.2], [-0.8, -1.2]],
        "checks": [("RY1", "2013-05", "2013-09", "real_tightening",
                    "dom"),
                   ("RY2", "2022-03", "2022-10", "real_tightening",
                    "dom"),
                   ("RY3", "2020-03", "2020-12", "real_easing", "dom")]},
    "breakevens": {
        "block": "rates_expectations",
        "build": lambda F, defl: _lvl_chg(F["_be10"].dropna(),
                                          lvl_m=36, chg_m=24),
        "needs": ["breakeven10.csv"],
        "states": ["calm", "reflation", "deflation_scare"],
        "T": [[0.0, 0.0], [0.7, 1.0], [-1.2, -1.4]],
        "checks": [("BE1", "2008-09", "2008-12", "deflation_scare",
                    "dom"),
                   ("BE2", "2021-01", "2021-05", "reflation", "dom"),
                   ("BE3", "2020-03", "2020-04", "deflation_scare",
                    "pres")]},
    "copper": {
        "block": "metals",
        "build": lambda F, defl: _mom(F["_copper"].dropna(), defl),
        "needs": ["copper.csv"],
        "states": ["calm", "boom", "bust"],
        "T": [[0.0, 0.0], [0.9, 1.0], [-1.0, -1.1]],
        "checks": [("CO1", "2003-10", "2006-06", "boom", "dom"),
                   ("CO2", "2008-10", "2009-03", "bust", "dom"),
                   ("CO3", "2014-09", "2016-02", "bust", "dom")]},
    "coal": {
        "block": "energy",
        "build": lambda F, defl: _mom(F["_coal"].dropna(), defl),
        "needs": ["coal.csv"],
        "states": ["calm", "boom", "bust"],
        "T": [[0.0, 0.0], [0.9, 1.0], [-1.0, -1.1]],
        "checks": [("CL1", "2008-01", "2008-09", "boom", "dom"),
                   ("CL2", "2020-03", "2020-08", "bust", "pres"),
                   ("CL3", "2021-06", "2022-09", "boom", "dom")]},
    "uranium": {
        "block": "energy",
        "build": lambda F, defl: _mom(F["_uranium"].dropna(), defl),
        "needs": ["uranium.csv"],
        "states": ["calm", "boom", "bust"],
        "T": [[0.0, 0.0], [0.9, 1.0], [-1.0, -1.1]],
        "checks": [("UR1", "2006-06", "2007-07", "boom", "dom"),
                   ("UR2", "2011-04", "2012-12", "bust", "dom"),
                   ("UR3", "2023-06", "2024-02", "boom", "dom")]},
    "euro": {
        "block": "fx",
        "build": lambda F, defl: pd.DataFrame({
            "m3": rolling_z((100 * np.log(F["_euro"])).diff(3),
                            120, 24),
            "m12": rolling_z((100 * np.log(F["_euro"]))
                             .diff(12), 120, 24)}),
        "needs": ["euro.csv"],
        "states": ["calm", "euro_strong",
                   "euro_weak"],
        "T": [[0.0, 0.0], [0.9, 0.9], [-0.9, -0.9]],
        "checks": [("EU1", "2010-05", "2010-06", "euro_weak", "pres"), ("EU2", "2014-09", "2015-03", "euro_weak", "dom"), ("EU3", "2017-05", "2017-12", "euro_strong", "dom")]},
    "yen": {
        "block": "fx",
        "build": lambda F, defl: pd.DataFrame({
            "m3": rolling_z((-100 * np.log(F["_yen"])).diff(3),
                            120, 24),
            "m12": rolling_z((-100 * np.log(F["_yen"]))
                             .diff(12), 120, 24)}),
        "needs": ["yen.csv"],
        "states": ["calm", "yen_strong",
                   "yen_weak"],
        "T": [[0.0, 0.0], [0.9, 0.9], [-0.9, -0.9]],
        "checks": [("JP1", "2008-09", "2009-01", "yen_strong", "dom"), ("JP2", "2012-11", "2013-05", "yen_weak", "dom"), ("JP3", "2022-03", "2022-10", "yen_weak", "dom")]},
    "yuan": {
        "block": "fx",
        # registered above as "EXCHUS from 2006 only, pre-reform peg
        # excluded by construction"; the slice enforces that clause.
        "build": lambda F, defl: pd.DataFrame({
            "m3": rolling_z((-100 * np.log(
                F["_yuan"].loc[YUAN_START:])).diff(3), 120, 24),
            "m12": rolling_z((-100 * np.log(
                F["_yuan"].loc[YUAN_START:])).diff(12), 120, 24)}),
        "needs": ["yuan.csv"],
        "states": ["calm", "yuan_strong",
                   "yuan_weak"],
        "T": [[0.0, 0.0], [0.9, 0.9], [-0.9, -0.9]],
        "checks": [("CN1", "2015-08", "2016-12", "yuan_weak", "dom"), ("CN2", "2020-07", "2021-05", "yuan_strong", "dom"), ("CN3", "2022-04", "2022-10", "yuan_weak", "dom")]},
    "sterling": {
        "block": "fx",
        "build": lambda F, defl: pd.DataFrame({
            "m3": rolling_z((100 * np.log(F["_sterling"])).diff(3),
                            120, 24),
            "m12": rolling_z((100 * np.log(F["_sterling"]))
                             .diff(12), 120, 24)}),
        "needs": ["sterling.csv"],
        "states": ["calm", "gbp_strong",
                   "gbp_weak"],
        "T": [[0.0, 0.0], [0.9, 0.9], [-0.9, -0.9]],
        "checks": [("GB1", "2008-08", "2009-01", "gbp_weak", "dom"), ("GB2", "2016-06", "2016-10", "gbp_weak", "dom"), ("GB3", "2022-09", "2022-09", "gbp_weak", "pres")]},
    "em_dollar": {
        "block": "fx",
        "build": lambda F, defl: _lvl_chg(
            np.log(F["_em_usd"]).dropna() * 100, lvl_m=36, chg_m=24),
        "needs": ["em_dollar.csv"],
        "states": ["calm", "em_stress", "em_bid"],
        "T": [[0.0, 0.0], [0.9, 0.9], [-0.9, -0.8]],
        "checks": [("EM1", "2008-09", "2009-03", "em_stress", "dom"),
                   ("EM2", "2014-07", "2016-01", "em_stress", "dom"),
                   ("EM3", "2020-03", "2020-04", "em_stress", "pres")]},
    "activity": {
        "block": "activity",
        "build": lambda F, defl: _lvl_chg(F["_wei"].dropna(),
                                          lvl_w=120, lvl_m=24,
                                          chg_w=120, chg_m=24),
        "needs": ["wei.csv"],
        "states": ["calm", "expansion", "contraction"],
        "T": [[0.0, 0.0], [1.0, 0.8], [-1.2, -1.0]],
        "checks": [("AC1", "2020-03", "2020-06", "contraction", "dom"),
                   ("AC2", "2021-03", "2021-06", "expansion", "dom"),
                   ("AC3", "2008-10", "2009-06", "contraction", "dom")]},
    "housing": {
        "block": "activity",
        "build": lambda F, defl: _mom(F["_houst"].dropna(),
                                      pd.Series(1.0, index=F["_houst"]
                                                .index)),
        "needs": ["houst.csv"],
        "states": ["calm", "boom", "bust"],
        "T": [[0.0, 0.0], [0.9, 0.8], [-1.1, -0.9]],
        "checks": [("HS1", "2006-06", "2009-06", "bust", "dom"),
                   ("HS2", "2020-04", "2020-05", "bust", "pres"),
                   ("HS3", "2012-10", "2013-12", "boom", "pres")]},
    "money": {
        "block": "liquidity",
        "build": lambda F, defl: _lvl_chg(
            (100 * (F["_m2"] / F["_m2"].shift(12) - 1)).dropna(),
            lvl_w=240, lvl_m=60),
        "needs": ["m2.csv"],
        "states": ["calm", "expansion", "contraction"],
        "T": [[0.0, 0.0], [1.3, 1.0], [-1.2, -0.9]],
        "checks": [("M2a", "2020-04", "2021-02", "expansion", "dom"),
                   ("M2b", "2022-12", "2023-12", "contraction", "dom")]},
    "claims": {
        "block": "activity",
        "build": lambda F, defl: _lvl_chg(
            (-100 * np.log(F["_claims"])).dropna()),
        "needs": ["claims.csv"],
        "states": ["calm", "expansion", "contraction"],
        "T": [[0.0, 0.0], [1.0, 0.8], [-1.2, -1.0]],
        "checks": [("CJ1", "2008-11", "2009-06", "contraction", "dom"),
                   ("CJ2", "2020-03", "2020-05", "contraction", "pres"),
                   ("CJ3", "2022-01", "2022-06", "expansion", "pres")]},
}
BLOCKS = {"energy": ["oil", "gas", "coal", "uranium"],
          "rates_expectations": ["curve", "real_yield", "breakevens",
                                 "inflation"],
          "credit": ["credit"], "fx": ["dollar", "euro", "yen", "yuan", "sterling", "em_dollar"],
          "equities": ["equities"], "metals": ["gold", "copper"],
          "activity": ["activity", "housing", "claims"],
          "liquidity": ["money"]}


def _load_extra(data_dir, F):
    import os

    def rd(fname, col):
        p = f"{data_dir}/{fname}"
        if not os.path.exists(p):
            return None
        s = pd.read_csv(p, index_col=0)[col]
        s.index = pd.PeriodIndex(s.index, freq="M")
        return s
    F["_gs2"] = rd("gs2.csv", "gs2")
    F["_ry10"] = rd("real_yield10.csv", "ry10")
    F["_be10"] = rd("breakeven10.csv", "be10")
    F["_copper"] = rd("copper.csv", "copper")
    F["_coal"] = rd("coal.csv", "coal")
    F["_uranium"] = rd("uranium.csv", "uranium")
    F["_euro"] = rd("euro.csv", "euro")
    F["_yen"] = rd("yen.csv", "yen")
    F["_yuan"] = rd("yuan.csv", "yuan")
    F["_sterling"] = rd("sterling.csv", "sterling")
    F["_em_usd"] = rd("em_dollar.csv", "em_usd")
    F["_wei"] = rd("wei.csv", "wei")
    F["_houst"] = rd("houst.csv", "houst")
    F["_m2"] = rd("m2.csv", "m2")
    F["_claims"] = rd("claims.csv", "claims")
    return F


def decode_network(data_dir, asof):
    """Decode every registry node whose data exists. Returns preds,
    posts, features (primary per node), current, strips, membership
    check results, and the active/awaiting split."""
    A = pd.Period(asof, "M")
    F = nodes.load_feeds(data_dir)
    F = _load_extra(data_dir, F)
    defl = nodes._splice_deflator(F)
    months = pd.period_range(pd.Period("1998-01", "M"), A, freq="M")
    out = {"preds": {}, "posts": {}, "primary": {}, "current": {},
           "strip": {}, "checks": [], "active": [], "awaiting": []}
    for name, spec in REGISTRY.items():
        missing = [f for f in spec["needs"]
                   if F.get("_" + f.split(".")[0]
                            .replace("real_yield10", "ry10")
                            .replace("breakeven10", "be10")
                            .replace("em_dollar", "em_usd")
                            .replace("houst", "houst")
                            .replace("m2", "m2")
                            .replace("wei", "wei")
                            .replace("gs2", "gs2")
                            .replace("copper", "copper")) is None]
        if missing:
            out["awaiting"].append(name)
            continue
        f = spec["build"](F, defl)
        f = f.loc[:A]
        T = np.asarray(spec["T"], float)
        h = TemplateHMM(T, p_stay=0.90)
        X = f.to_numpy(float)
        ok = np.where((~np.isnan(X)).any(1))[0]
        X, ni = X[ok[0]:], f.index[ok[0]:]
        Xc = X.copy()
        Xc[~np.isfinite(Xc)] = np.nan
        po = h.posteriors(Xc)
        pred = pd.Series([spec["states"][i] for i in po.argmax(1)],
                         index=ni)
        post = pd.DataFrame(po, index=ni, columns=spec["states"])
        pv = f.iloc[:, 0].dropna()
        last = pv.index[-1] if len(pv) else None
        if last is not None:
            pred, post = pred.loc[:last], post.loc[:last]
        out["preds"][name] = pred
        out["posts"][name] = post
        out["primary"][name] = f.iloc[:, 0]
        hits = 0
        for cid, a, b, target, mode in spec["checks"]:
            w = pred.loc[pd.Period(a, "M"):pd.Period(b, "M")].dropna()
            if len(w) == 0:
                res = {"id": cid, "hit": None, "note": "no data"}
            else:
                dom = w.value_counts().index[0]
                hit = (dom == target if mode == "dom"
                       else bool((w == target).any()))
                res = {"id": cid, "node": name, "target": target,
                       "mode": mode, "dominant": dom,
                       "share": round(float((w == target).mean()), 2),
                       "hit": bool(hit)}
                hits += int(hit)
            out["checks"].append(res)
        member = hits >= 2
        out["active"].append({"name": name, "member": bool(member),
                              "hits": hits,
                              "of": len(spec["checks"])})
        pr = pred.dropna()
        row = post.loc[pr.index[-1]]
        out["current"][name] = {
            "state": pr.iloc[-1], "prob": round(float(row.max()), 2),
            "asof": str(pr.index[-1]),
            "word": WORDS.get(pr.iloc[-1], pr.iloc[-1]),
            "member": bool(member)}
        out["strip"][name] = [CODES.get(pred.get(p), -1)
                              if isinstance(pred.get(p), str) else -1
                              for p in months]
    return out
