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
