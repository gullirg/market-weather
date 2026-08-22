"""Phase A: the daily sensing clock, piloted on the oil instrument.

Design, registered before estimation:
1. Business-day grid. Daily features where daily data exists: 63-day
   real momentum, 21-day realized volatility, Brent-WTI spread, VIX,
   each z-scored on a rolling 2520-day window (min 504). Monthly-only
   dimensions (equities, commodity factor, inventories) are placed on
   their month-end date and masked on every other day: the masked
   decoder is natively mixed-frequency.
2. Same six states, same templates, same anchors as the monthly
   instrument (anchors applied to every day of the anchored month).
   Sigmas re-estimated by the same EM procedure on the daily panel.
   Stay probability 0.995 daily, the monthly 0.90 rescaled to the
   business-day clock.
3. Filtered (causal) decode is the sensing output: the state on day t
   uses only data through day t. Smoothed decode is computed for
   reference only.

Registered gates, scored once, published as they fall:
  PA1 Non-regression: the daily filtered state's monthly mode agrees
      with the monthly instrument's state in at least 85 percent of
      months where both are defined.
  PA2 Latency: across the pinned episode starts (1990-08 squeeze,
      2008-10 collapse, 2014-11 glut, 2020-03 collapse, 2026-03
      squeeze), the daily clock's first sustained flip (5 consecutive
      business days in the episode's state family) leads the monthly
      confirmation (last business day of the flip month) by a median
      of at least 10 business days.

Phase G12: the daily clock as its own instrument. Registered here
before any estimation of it.

The clock above is the monthly decoder run on a daily grid and it
failed three registered gates: PA1 0.567 exact state, G10 0.682 exact
state after the causal carry-forward repair, G11 0.703 at family
level. Agreement with the monthly clock is not retried in any form.
What follows is a different instrument, with its own states, its own
features and its own checks.

1. Grid: business days, from the first day of the daily Brent series
   to the asof month end. The decode is filtered and causal only: the
   family on day t uses data through day t and nothing later.
2. Features, each z-scored on a rolling 2520-business-day window with
   a 504-day minimum, the daily convention already used above:
     mom  63-business-day real Brent momentum, diff(63) of log real
          price
     rv   21-business-day realized volatility of daily log returns,
          annualized by sqrt(252)
     ovx  the CBOE crude oil volatility index level, daily, absent
          and therefore masked before 2007-05
     inv  US crude inventories ex-SPR, a monthly print placed on that
          month's last business day and carried forward causally
   Missing dimensions are masked, never imputed.
3. States, four, at family level, with fixed templates over
   [mom, rv, ovx, inv]:
     calm      [ 0.0,  0.0,  0.0,  0.0]
     boom      [ 1.1,  0.0,  0.0, -0.6]  price up, ordinary
                                          volatility, inventories
                                          drawing
     fear      [ 0.8,  1.2,  1.2, -0.3]  price up with a volatility
                                          spike, the war premium
     downturn  [-1.2,  0.9,  0.9,  0.7]  price down hard, volatility
                                          up, inventories building
   Nothing is fitted. Unit spreads, means held fixed, stay
   probability 0.995 on the business-day clock.
4. Episode families, fixed from oil history before any decode:
   1990-08 fear (Iraq invades Kuwait), 2008-10 downturn (Lehman),
   2014-11 downturn (OPEC declines to cut into the shale glut),
   2020-03 downturn (Covid demand collapse), 2026-03 fear (the
   strait war).

Registered checks, scored once, published whichever way they fall:
  D1 Episode capture. For each of the five pinned episodes, the daily
     family equals the episode family on at least one business day in
     the window running from the episode month's first business day
     through the twenty-fifth business day after it, inclusive. The
     check hits if at least 4 of the 5 episodes are captured.
  D2 False-flip budget. Consider only business days outside the five
     pinned episode months and their three-month halos on either
     side. A family flip is a day whose family differs from the
     previous day's, counted only when both days are outside the
     halos. The flip rate must be at most 6 per decade, a decade
     being 2520 business days.
  D3 Persistence. The median family run length over the whole
     filtered series is at least 40 business days.

Registered public gate: the daily chip appears on the site only if D1
and D2 both hit. If the gate stays shut, the daily clock stays a
shadow instrument on this architecture, permanently.
"""

import numpy as np
import pandas as pd

from instrument.hmm import SigmaHMM, em_sigmas
from instrument import nodes


def _dz(s, window=2520, minp=504):
    mu = s.rolling(window, min_periods=minp).mean()
    sd = s.rolling(window, min_periods=minp).std()
    return (s - mu) / sd


def build_daily_panel(data_dir, asof):
    F = nodes.load_feeds(data_dir)
    A = pd.Period(asof, "M")
    end = A.to_timestamp(how="end")
    brent = F["brent_d"].loc[:end]
    wti = F["wti_d"].loc[:end]
    vix = pd.read_csv(f"{data_dir}/vix-daily.csv")
    vix.columns = [c.strip().upper() for c in vix.columns]
    vix["DATE"] = pd.to_datetime(vix["DATE"])
    vix_d = vix.set_index("DATE")["CLOSE"].astype(float).loc[:end]
    grid = pd.bdate_range(brent.index[0], min(brent.index[-1], end))
    b = brent.reindex(grid).ffill(limit=3)
    w = wti.reindex(grid).ffill(limit=3)
    v = vix_d.reindex(grid).ffill(limit=3)
    # monthly splice deflator carried daily
    ratio = float(F["sh_cpi"].loc[nodes.SPLICE_CUT]
                  / F["cpi"].loc[nodes.SPLICE_CUT])
    splice = pd.concat([F["sh_cpi"].loc[:nodes.SPLICE_CUT],
                        F["cpi"].loc[nodes.SPLICE_CUT + 1:] * ratio])
    defl = splice.reindex(pd.PeriodIndex(grid, freq="M")).ffill()
    defl.index = grid
    real = np.log(b / defl)
    f = pd.DataFrame(index=grid)
    f["oil"] = _dz(real.diff(63))
    f["rv"] = _dz(np.log(b).diff().rolling(21).std() * np.sqrt(252))
    f["vix"] = _dz(v)
    f["bw"] = _dz((b - w) / b)
    # monthly dims at month-end, masked elsewhere
    L = nodes.build_features(data_dir, asof)
    fm = L["f"]
    month_end = {p: d for d, p in
                 zip(grid, pd.PeriodIndex(grid, freq="M"))
                 for p in [pd.Period(d, "M")]}
    # last business day per month
    me = pd.Series(grid, index=grid).groupby(
        pd.PeriodIndex(grid, freq="M")).last()
    for col in ["eq", "metals", "inv"]:
        col_d = pd.Series(np.nan, index=grid)
        for p, d in me.items():
            if p in fm.index:
                col_d.loc[d] = fm.loc[p, col]
        # G10: carry the last monthly print forward causally, the way a
        # human analyst holds the latest known figure until the next one
        f[col] = col_d.ffill()
    return f[["oil", "eq", "metals", "rv", "vix", "bw", "inv"]]


FAMILY = {"supply_squeeze": {"supply_squeeze", "precautionary"},
          "demand_collapse": {"demand_collapse"},
          "supply_glut": {"supply_glut"}}
EPISODES = [("1990-08", "supply_squeeze"), ("2008-10", "demand_collapse"),
            ("2014-11", "supply_glut"), ("2020-03", "demand_collapse"),
            ("2026-03", "supply_squeeze")]


def run(data_dir, asof, monthly_pred):
    f = build_daily_panel(data_dir, asof)
    X = f.to_numpy(float)
    s0 = np.where(~np.isnan(X[:, 0]))[0][0]
    X, idx = X[s0:], f.index[s0:]
    periods = pd.PeriodIndex(idx, freq="M")
    anchors = {}
    for mth, s in nodes.OIL_ANCHORS.items():
        p = pd.Period(mth, "M")
        for i, pp in enumerate(periods):
            if pp == p:
                anchors[i] = s
    # EM by the same rule; anchors handled inside on positions
    k, d = nodes.OIL_T.shape
    sig = em_sigmas(X, pd.RangeIndex(len(X)), nodes.OIL_T,
                    p_stay=0.995, anchors=None)
    hmm = SigmaHMM(nodes.OIL_T, sig, p_stay=0.995)
    Xc = X.copy()
    Xc[~np.isfinite(Xc)] = np.nan
    logB = hmm._loglik(Xc)
    for pos, s in anchors.items():
        logB[pos] += np.where(np.arange(k) == s, 0.0, -30.0)
    # causal filtered decode
    from instrument.hmm import _logsumexp
    T = logB.shape[0]
    la = np.zeros((T, k))
    filt = np.zeros((T, k))
    la[0] = -np.log(k) + logB[0]
    filt[0] = np.exp(la[0] - _logsumexp(la[0][None, :], 1))
    for t in range(1, T):
        la[t] = logB[t] + _logsumexp(la[t - 1][:, None] + hmm.logA, 0)
        la[t] -= la[t].max()
        filt[t] = np.exp(la[t] - _logsumexp(la[t][None, :], 1))
    daily_state = pd.Series(
        [nodes.OIL_STATES[i] for i in filt.argmax(1)], index=idx)
    FAM = {"calm": "calm", "demand_boom": "boom",
           "supply_squeeze": "fear", "precautionary": "fear",
           "demand_collapse": "downturn", "supply_glut": "downturn"}
    # PA1: monthly mode agreement
    mode = daily_state.groupby(periods).agg(
        lambda s: s.value_counts().index[0])
    both = mode.index.intersection(monthly_pred.index)
    agree = float((mode.loc[both] == monthly_pred.loc[both]).mean())
    pa1 = {"id": "PA1", "value": round(agree, 3),
           "hit": bool(agree >= 0.85), "months": int(len(both))}
    fam_mode = daily_state.map(FAM).groupby(periods).agg(
        lambda s: s.value_counts().index[0])
    fam_agree = float((fam_mode.loc[both]
                       == monthly_pred.loc[both].map(FAM)).mean())
    g11 = {"id": "G11", "value": round(fam_agree, 3),
           "hit": bool(fam_agree >= 0.85), "months": int(len(both))}
    # PA2: latency at episode starts
    leads = {}
    for start, fam in EPISODES:
        M = pd.Period(start, "M")
        target = FAMILY[fam]
        lo = (M - 2).to_timestamp()
        hi = (M + 1).to_timestamp(how="end")
        win = daily_state.loc[lo:hi]
        flip = None
        run_len = 0
        for dgd, st in win.items():
            run_len = run_len + 1 if st in target else 0
            if run_len >= 5:
                flip = dgd
                break
        if flip is None:
            leads[start] = None
            continue
        confirm = daily_state.loc[:M.to_timestamp(how="end")].index[-1]
        leads[start] = int(np.busday_count(
            flip.date(), confirm.date()))
    valid = [v for v in leads.values() if v is not None]
    med = float(np.median(valid)) if valid else None
    pa2 = {"id": "PA2", "value": {"leads_bd": leads, "median": med},
           "hit": bool(med is not None and med >= 10
                       and all(v is not None for v in leads.values()))}
    return {"checks": [pa1, pa2, g11],
            "current": {"state": daily_state.iloc[-1],
                        "family": FAM[daily_state.iloc[-1]],
                        "date": str(idx[-1].date())},
            "monthly_mode_tail": {str(p): mode.get(p) for p in
                                  mode.index[-6:]}}


# ------------------------------------------------------- G12 instrument
G12_STATES = ["calm", "boom", "fear", "downturn"]
G12_T = np.array([[0.0, 0.0, 0.0, 0.0],
                  [1.1, 0.0, 0.0, -0.6],
                  [0.8, 1.2, 1.2, -0.3],
                  [-1.2, 0.9, 0.9, 0.7]], float)
G12_P_STAY = 0.995
G12_EPISODES = [("1990-08", "fear"), ("2008-10", "downturn"),
                ("2014-11", "downturn"), ("2020-03", "downturn"),
                ("2026-03", "fear")]
G12_CAPTURE_BD = 25
G12_HALO_M = 3
G12_DECADE_BD = 2520


def build_g12_panel(data_dir, asof):
    """The registered G12 feature panel: mom, rv, ovx, inv."""
    F = nodes.load_feeds(data_dir)
    A = pd.Period(asof, "M")
    end = A.to_timestamp(how="end")
    brent = F["brent_d"].loc[:end]
    grid = pd.bdate_range(brent.index[0], min(brent.index[-1], end))
    b = brent.reindex(grid).ffill(limit=3)
    ratio = float(F["sh_cpi"].loc[nodes.SPLICE_CUT]
                  / F["cpi"].loc[nodes.SPLICE_CUT])
    splice = pd.concat([F["sh_cpi"].loc[:nodes.SPLICE_CUT],
                        F["cpi"].loc[nodes.SPLICE_CUT + 1:] * ratio])
    defl = splice.reindex(pd.PeriodIndex(grid, freq="M")).ffill()
    defl.index = grid
    real = np.log(b / defl)
    f = pd.DataFrame(index=grid)
    f["mom"] = _dz(real.diff(63))
    f["rv"] = _dz(np.log(b).diff().rolling(21).std() * np.sqrt(252))
    ov = pd.read_csv(f"{data_dir}/ovx-daily.csv")
    ov["DATE"] = pd.to_datetime(ov["DATE"])
    ovd = ov.set_index("DATE")["CLOSE"].astype(float).loc[:end]
    f["ovx"] = _dz(ovd.reindex(grid).ffill(limit=3))
    L = nodes.build_features(data_dir, asof)
    inv_m = L["f"]["inv"]
    me = pd.Series(grid, index=grid).groupby(
        pd.PeriodIndex(grid, freq="M")).last()
    inv_d = pd.Series(np.nan, index=grid)
    for p, d in me.items():
        if p in inv_m.index:
            inv_d.loc[d] = inv_m.loc[p]
    f["inv"] = inv_d.ffill()
    return f[["mom", "rv", "ovx", "inv"]]


def _g12_filtered(f):
    """Causal filtered family series from the registered templates."""
    from instrument.hmm import TemplateHMM, _logsumexp
    X = f.to_numpy(float)
    s0 = np.where(~np.isnan(X[:, 0]))[0][0]
    X, idx = X[s0:], f.index[s0:]
    X = X.copy()
    X[~np.isfinite(X)] = np.nan
    hmm = TemplateHMM(G12_T, p_stay=G12_P_STAY)
    logB = hmm._loglik(X)
    k = G12_T.shape[0]
    T = logB.shape[0]
    la = np.zeros((T, k))
    out = np.zeros((T, k))
    la[0] = -np.log(k) + logB[0]
    out[0] = np.exp(la[0] - _logsumexp(la[0][None, :], 1))
    for t in range(1, T):
        la[t] = logB[t] + _logsumexp(la[t - 1][:, None] + hmm.logA, 0)
        la[t] -= la[t].max()
        out[t] = np.exp(la[t] - _logsumexp(la[t][None, :], 1))
    fam = pd.Series([G12_STATES[i] for i in out.argmax(1)], index=idx)
    prob = pd.Series(out.max(1), index=idx)
    return fam, prob


def _runs(fam):
    lens, cur = [], 1
    v = fam.to_numpy()
    for i in range(1, len(v)):
        if v[i] == v[i - 1]:
            cur += 1
        else:
            lens.append(cur)
            cur = 1
    lens.append(cur)
    return lens


def run_g12(data_dir, asof):
    """One estimation, one scoring of D1, D2 and D3."""
    f = build_g12_panel(data_dir, asof)
    fam, prob = _g12_filtered(f)
    periods = pd.PeriodIndex(fam.index, freq="M")

    # D1 episode capture
    caps = {}
    for start, target in G12_EPISODES:
        M = pd.Period(start, "M")
        pos = np.where(periods == M)[0]
        if len(pos) == 0:
            caps[start] = None
            continue
        i = int(pos[0])
        win = fam.iloc[i:i + G12_CAPTURE_BD + 1]
        caps[start] = bool((win == target).any())
    got = sum(1 for v in caps.values() if v)
    d1 = {"id": "D1", "value": {"captured": caps, "n": got},
          "hit": bool(got >= 4)}

    # D2 false-flip budget outside the pinned episodes and their halos
    excl = set()
    for start, _t in G12_EPISODES:
        M = pd.Period(start, "M")
        for j in range(-G12_HALO_M, G12_HALO_M + 1):
            excl.add(M + j)
    elig = np.array([p not in excl for p in periods])
    v = fam.to_numpy()
    flips = int(sum(1 for t in range(1, len(v))
                    if elig[t] and elig[t - 1] and v[t] != v[t - 1]))
    ndays = int(elig.sum())
    rate = (flips / (ndays / G12_DECADE_BD)) if ndays else None
    d2 = {"id": "D2", "value": {"flips": flips, "eligible_bd": ndays,
                                "per_decade": round(rate, 2)
                                if rate is not None else None},
          "hit": bool(rate is not None and rate <= 6)}

    # D3 persistence
    lens = _runs(fam)
    med = float(np.median(lens))
    d3 = {"id": "D3", "value": {"median_run_bd": med,
                                "runs": len(lens)},
          "hit": bool(med >= 40)}

    gate = "open" if (d1["hit"] and d2["hit"]) else "closed"
    return {"checks": [d1, d2, d3], "gate": gate,
            "current": {"family": fam.iloc[-1],
                        "prob": round(float(prob.iloc[-1]), 2),
                        "date": str(fam.index[-1].date())},
            "span": [str(fam.index[0].date()), str(fam.index[-1].date())]}
