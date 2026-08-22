"""decode_all: the seven frozen instruments, ported faithfully.

Configs are the validated ones: oil is the stage-3 V3 sensor under the
stage-6 spliced deflator; gas and gold are the stage-4 nodes; dollar,
credit, inflation v2 and equity v2 are the stage-6 nodes. Changing any
template, window, or state meaning requires a registered scorecard item.
"""

import numpy as np
import pandas as pd

from instrument.hmm import TemplateHMM, SigmaHMM, em_sigmas, rolling_z

OIL_STATES = ["calm", "demand_boom", "demand_collapse",
              "supply_squeeze", "supply_glut", "precautionary"]
OIL_T = np.array([
    [0.0,  0.0,  0.0, -0.3, -0.3,  0.0,  0.0],
    [0.8,  0.7,  0.9, -0.2, -0.3,  0.0, -0.4],
    [-1.2, -1.2, -1.0,  1.2,  1.5,  0.0,  0.5],
    [1.2, -0.5, -0.2,  1.2,  0.8,  0.5, -0.6],
    [-1.0,  0.2,  0.0,  0.5,  0.0, -0.3,  0.8],
    [0.9,  0.0,  0.0,  0.8,  0.7,  0.0,  0.8],
])
OIL_ANCHORS = {"1990-08": 3, "1990-09": 3, "2008-10": 2, "2008-11": 2,
               "2015-01": 4, "2015-02": 4}
SPLICE_CUT = pd.Period("2023-09", "M")

GAS_STATES = ["calm", "squeeze", "glut"]
GAS_T = np.array([[0.0, -0.3, 0.0], [1.0, 1.0, 0.8], [-1.0, 0.3, -0.6]])
GOLD_STATES = ["calm", "fear_bid", "real_rate_bid", "selloff"]
GOLD_T = np.array([[0.0, 0.0, 0.0], [1.0, 1.2, 0.0],
                   [0.9, -0.2, -1.0], [-1.0, 0.0, 1.0]])
DOL_STATES = ["calm", "usd_up", "usd_down"]
DOL_T = np.array([[0.0, 0.0], [0.9, 0.8], [-0.9, -0.8]])
CR_STATES = ["calm", "stress", "easing"]
CR_T = np.array([[-0.1, 0.0], [1.3, 1.2], [-0.5, -0.8]])
INF_STATES = ["calm", "surge", "easing"]
INF_T = np.array([[0.0, 0.0, 0.0], [1.1, 1.0, 0.7], [-0.9, -0.8, -1.1]])
EQ_STATES = ["calm", "rally", "correction", "stress"]
EQ_T = np.array([[0.0, -0.3], [0.9, -0.4], [-0.6, 0.7], [-1.5, 2.0]])

CODES = {"calm": 0, "boom": 1, "demand_boom": 1, "rally": 1,
         "real_rate_bid": 1, "collapse": 2, "demand_collapse": 2,
         "stress": 2, "easing": 2, "selloff": 2, "usd_down": 2,
         "squeeze": 3, "supply_squeeze": 3, "surge": 3, "usd_up": 3,
         "glut": 4, "supply_glut": 4,
         "precautionary": 5, "fear_bid": 5, "inverted": 5, "correction": 5}

NODE_ORDER = ["oil", "gas", "dollar", "credit", "inflation",
              "equities", "gold"]


def _read_price(path, date_col="Date", price_col="Price"):
    d = pd.read_csv(path)
    d.columns = [c.strip() for c in d.columns]
    d[date_col] = pd.to_datetime(d[date_col])
    return d.set_index(date_col)[price_col].astype(float).sort_index()


def _monthly(series_daily):
    return series_daily.groupby(lambda t: t.to_period("M")).mean()


def _pseries(path, col):
    s = pd.read_csv(path, index_col=0)[col]
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s


def real_brent(F):
    brent_m = _monthly(F["brent_d"])
    return (brent_m / _splice_deflator(F).reindex(brent_m.index)
            .ffill()).dropna()


def load_feeds(data):
    F = {}
    F["brent_d"] = _read_price(f"{data}/brent-daily.csv")
    F["wti_d"] = _read_price(f"{data}/wti-daily.csv")
    F["gas_d"] = _read_price(f"{data}/gas-daily.csv")
    gold = pd.read_csv(f"{data}/gold-monthly.csv")
    gold["Date"] = pd.to_datetime(gold["Date"])
    gm = gold.set_index("Date")["Price"].astype(float)
    gm.index = gm.index.to_period("M")
    F["gold_m"] = gm
    vix = pd.read_csv(f"{data}/vix-daily.csv")
    vix.columns = [c.strip().upper() for c in vix.columns]
    vix["DATE"] = pd.to_datetime(vix["DATE"])
    F["vix_m"] = vix.set_index("DATE")["CLOSE"].astype(float).groupby(
        lambda t: t.to_period("M")).mean()
    sh = pd.read_csv(f"{data}/shiller.csv")
    sh.columns = [c.strip() for c in sh.columns]
    sh["Date"] = pd.to_datetime(sh["Date"])
    shp = sh.set_index(sh["Date"].dt.to_period("M"))
    F["sh_cpi"] = shp["Consumer Price Index"].astype(float).where(
        lambda s: s > 0)
    F["sh_gs10"] = shp["Long Interest Rate"].astype(float).where(
        lambda s: s > 0)
    F["spx"] = shp["SP500"].astype(float)
    F["imf"] = pd.read_csv(f"{data}/imf-commodities.csv")
    tot = pd.read_csv(f"{data}/us_total_stocks_exspr.csv")
    tot.index = pd.PeriodIndex(tot["Month"], freq="M")
    F["stocks"] = tot["Stocks"].astype(float)
    tb = pd.read_csv(f"{data}/tb3ms.csv")
    tb.index = pd.PeriodIndex(tb["Month"], freq="M")
    F["tb3"] = tb["TB3MS"].astype(float)
    F["c1"] = _pseries(f"{data}/futures_c1.csv", "c1")
    F["c4"] = _pseries(f"{data}/futures_c4.csv", "c4")
    F["usd"] = _pseries(f"{data}/usd_broad.csv", "usd")
    F["baa"] = _pseries(f"{data}/baa_yield.csv", "baa")
    F["gs10"] = _pseries(f"{data}/gs10_fred.csv", "gs10")
    F["cpi"] = _pseries(f"{data}/cpi_fred.csv", "cpi").interpolate(limit=2)
    F["core"] = _pseries(f"{data}/core_cpi_fred.csv",
                         "core").interpolate(limit=2)
    return F


def _splice_deflator(F):
    ratio = float(F["sh_cpi"].loc[SPLICE_CUT] / F["cpi"].loc[SPLICE_CUT])
    return pd.concat([F["sh_cpi"].loc[:SPLICE_CUT],
                      F["cpi"].loc[SPLICE_CUT + 1:] * ratio])


def build_features(data_dir, asof, masked=()):
    """Decode every instrument on feeds truncated to `asof` (a YYYY-MM
    string). `masked` names feeds forced dead for degraded-mode tests.
    Returns (site_data dict, diagnostics dict)."""
    A = pd.Period(asof, "M")
    F = load_feeds(data_dir)
    for k in list(F):
        s = F[k]
        if isinstance(s, pd.Series) and isinstance(s.index, pd.PeriodIndex):
            F[k] = s.loc[:A]
        elif isinstance(s, pd.Series):
            F[k] = s.loc[:A.to_timestamp(how="end")]
    for name in masked:
        F[name] = F[name].iloc[0:0]

    brent_m = _monthly(F["brent_d"])
    wti_m = _monthly(F["wti_d"])
    rv_m = (np.log(F["brent_d"]).diff()
            .groupby(lambda t: t.to_period("M")).std() * np.sqrt(252))
    idx = brent_m.index
    defl = _splice_deflator(F).reindex(idx).ffill()

    f = pd.DataFrame(index=idx)
    f["oil"] = rolling_z(np.log(brent_m / defl).diff(3))
    f["eq"] = rolling_z(np.log((F["spx"] / defl).reindex(idx)).diff(3))
    imf = F["imf"].copy()
    imf["Date"] = pd.to_datetime(imf["Date"])
    imf = imf.set_index("Date")
    imf.index = imf.index.to_period("M")
    WANT = ["crude", "wheat", "maize", "soybean", "sugar", "cotton",
            "coffee", "cocoa", "aluminum", "copper", "zinc", "tin",
            "nickel", "lead", "beef", "swine"]
    cols = [next(c for c in imf.columns if w in c.lower())
            for w in WANT if any(w in c.lower() for c in imf.columns)]
    p16 = imf[cols].apply(pd.to_numeric, errors="coerce").div(
        _splice_deflator(F).reindex(imf.index), axis=0)
    d3 = np.log(p16).diff(3)
    d3 = (d3 - d3.mean()) / d3.std()
    comp = d3.dropna(how="any")
    if len(comp) > 24:
        U, S, Vt = np.linalg.svd(comp.to_numpy(), full_matrices=False)
        load = Vt[0]
        cu = [i for i, c in enumerate(comp.columns)
              if "copper" in c.lower()][0]
        if load[cu] < 0:
            load = -load
        fact = pd.Series(comp.to_numpy() @ load, index=comp.index)
    else:
        fact = pd.Series(np.nan, index=idx)
    f["metals"] = rolling_z(fact.reindex(idx), 120, 24)
    f["rv"] = rolling_z(rv_m.reindex(idx))
    f["vix"] = rolling_z(F["vix_m"].reindex(idx))
    f["bw"] = rolling_z(((brent_m - wti_m) / brent_m).reindex(idx))
    f["inv"] = rolling_z(np.log(F["stocks"]).diff(12).reindex(idx), 120, 24)

    X = f[["oil", "eq", "metals", "rv", "vix", "bw", "inv"]].to_numpy(float)
    s0 = np.where(~np.isnan(X[:, 0]))[0][0]
    X, i7 = X[s0:], f.index[s0:]
    anchors = {s: OIL_STATES.index(OIL_STATES[v]) if isinstance(v, str)
               else v for s, v in OIL_ANCHORS.items()}
    sig = em_sigmas(X, i7, OIL_T, anchors=anchors)
    hmm = SigmaHMM(OIL_T, sig)
    Xc = X.copy()
    Xc[~np.isfinite(Xc)] = np.nan
    po = hmm.posteriors(Xc)
    pred_oil = pd.Series([OIL_STATES[p] for p in po.argmax(1)], index=i7)
    oil_post = pd.DataFrame(po, index=i7, columns=OIL_STATES)

    def _truncate(pred, post, primary):
        pv = primary.dropna()
        if len(pv) == 0:
            return pred.iloc[0:0], post.iloc[0:0]
        last = pv.index[-1]
        return pred.loc[:last], post.loc[:last]

    def em_decode(fdf, tpl, states):
        Xn = fdf.to_numpy(float)
        ok = np.where((~np.isnan(Xn)).any(1))[0]
        if len(ok) == 0:
            return pd.Series(dtype=object), pd.DataFrame(columns=states)
        Xn, ni = Xn[ok[0]:], fdf.index[ok[0]:]
        sg = em_sigmas(Xn, ni, np.asarray(tpl, float))
        h = SigmaHMM(np.asarray(tpl, float), sg)
        Xc = Xn.copy()
        Xc[~np.isfinite(Xc)] = np.nan
        p = h.posteriors(Xc)
        return (pd.Series([states[i] for i in p.argmax(1)], index=ni),
                pd.DataFrame(p, index=ni, columns=states))

    def plain_decode(Xn, ni, tpl, states):
        h = TemplateHMM(np.asarray(tpl, float))
        Xc = np.asarray(Xn, float).copy()
        Xc[~np.isfinite(Xc)] = np.nan
        p = h.posteriors(Xc)
        return (pd.Series([states[i] for i in p.argmax(1)], index=ni),
                pd.DataFrame(p, index=ni, columns=states))

    # gas (stage 4 config: Shiller deflator ffilled, rel move vs brent)
    gas_m = _monthly(F["gas_d"])
    gas_rv = (np.log(F["gas_d"]).diff()
              .groupby(lambda t: t.to_period("M")).std() * np.sqrt(252))
    shcpi = F["sh_cpi"].reindex(gas_m.index).ffill()
    zg = rolling_z(np.log(gas_m / shcpi).diff(3).reindex(idx), 120, 24)
    zgv = rolling_z(gas_rv.reindex(idx), 120, 24)
    zrel = rolling_z((np.log(gas_m).diff(3)
                      - np.log(brent_m).diff(3)).reindex(idx), 120, 24)
    pred_gas, gas_post = plain_decode(
        np.column_stack([zg, zgv, zrel]), idx, GAS_T, GAS_STATES)
    pred_gas, gas_post = _truncate(pred_gas, gas_post, zg)

    # gold (stage 4 config: Shiller cpi and guarded Shiller yields)
    zau = rolling_z(np.log(F["gold_m"]
                           / F["sh_cpi"].reindex(F["gold_m"].index).ffill())
                    .diff(3).reindex(idx), 120, 24)
    infl12 = 100 * np.log(F["sh_cpi"]).diff(12)
    real_y = (F["sh_gs10"] - infl12)
    zry = rolling_z(real_y.diff(3).reindex(idx), 120, 24)
    pred_au, au_post = plain_decode(
        np.column_stack([zau, f["vix"], zry]), idx, GOLD_T, GOLD_STATES)
    pred_au, au_post = _truncate(pred_au, au_post, zau)

    # dollar, credit, inflation v2 (stage 6 configs)
    lu = np.log(F["usd"])
    fd = pd.DataFrame({"d3": rolling_z(lu.diff(3), 120, 24),
                       "d12": rolling_z(lu.diff(12), 120, 24)})
    pred_d, d_post = em_decode(fd, DOL_T, DOL_STATES)
    pred_d, d_post = _truncate(pred_d, d_post, fd["d3"])
    spread = (F["baa"] - F["gs10"]).dropna()
    fc = pd.DataFrame({"lvl": rolling_z(spread, 240, 60),
                       "chg": rolling_z(spread.diff(3), 120, 36)})
    pred_c, c_post = em_decode(fc, CR_T, CR_STATES)
    pred_c, c_post = _truncate(pred_c, c_post, fc["lvl"])
    yoy = 100 * (F["core"] / F["core"].shift(12) - 1)
    fi = pd.DataFrame({"lvl": rolling_z(yoy, 240, 60),
                       "acc": rolling_z(yoy.diff(6), 120, 36),
                       "y10c": rolling_z(F["gs10"].diff(3), 120, 36)})
    pred_i, i_post = em_decode(fi, INF_T, INF_STATES)
    pred_i, i_post = _truncate(pred_i, i_post, fi["lvl"])
    fe = pd.DataFrame({"mom": f["eq"], "vix": f["vix"]})
    pred_e, e_post = em_decode(fe, EQ_T, EQ_STATES)
    pred_e, e_post = _truncate(pred_e, e_post, f["eq"])
    return locals()


def decode_all(data_dir, asof, masked=()):
    L = build_features(data_dir, asof, masked)
    (A, f, zg, zau, fd, fc, fi, fe, pred_oil, oil_post, pred_gas, gas_post,
     pred_au, au_post, pred_d, d_post, pred_c, c_post, pred_i, i_post,
     pred_e, e_post) = (L[k] for k in
        ["A", "f", "zg", "zau", "fd", "fc", "fi", "fe", "pred_oil",
         "oil_post", "pred_gas", "gas_post", "pred_au", "au_post",
         "pred_d", "d_post", "pred_c", "c_post", "pred_i", "i_post",
         "pred_e", "e_post"])

    months = pd.period_range(pd.Period("1998-01", "M"), A, freq="M")
    preds = {"oil": pred_oil, "gas": pred_gas, "dollar": pred_d,
             "credit": pred_c, "inflation": pred_i,
             "equities": pred_e, "gold": pred_au}
    posts = {"oil": oil_post, "gas": gas_post, "dollar": d_post,
             "credit": c_post, "inflation": i_post,
             "equities": e_post, "gold": au_post}

    def striprow(pred):
        return [CODES.get(pred.get(p), -1)
                if isinstance(pred.get(p), str) else -1 for p in months]

    strip = {n: striprow(preds[n]) for n in NODE_ORDER}

    def cur(n):
        pr, po_ = preds[n], posts[n]
        pr = pr.dropna()
        if len(pr) == 0:
            return {"state": "no_data", "prob": 0.0, "asof": "never",
                    "stale": True}
        when = pr.index[-1]
        row = po_.loc[when]
        out = {"state": pr.iloc[-1].replace("demand_", "")
               .replace("supply_", ""),
               "prob": round(float(row.max()), 2), "asof": str(when)}
        if when < A - 1:
            out["stale"] = True
        return out

    current = {n: cur(n) for n in NODE_ORDER}
    oil36 = oil_post.loc[A - 35:].round(3)
    site = {"months": [str(p) for p in months], "strip": strip,
            "current": current,
            "oil36": {"months": [str(p) for p in oil36.index],
                      "series": {c: oil36[c].tolist()
                                 for c in oil36.columns}}}
    return site, {"preds": preds, "posts": posts}
