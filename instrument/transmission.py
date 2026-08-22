"""Seven-node transmission estimation (registered as G5 before running).

Registered design, fixed before estimation:
1. Method: the stage-4 generalized FEVD (VAR p=2, horizon 12) unchanged.
2. One flow feature per node, the primaries already frozen in nodes.py:
   oil = 3m real oil momentum z, gas = 3m real gas momentum z,
   inflation = 6m core-yoy acceleration z, equities = 3m real equity
   momentum z, gold = 3m real gold momentum z, credit = 3m spread
   change z, dollar = 3m log dollar change z computed on the LONG
   series: major-currencies index 1973 to 2005, broad index from 2006
   scaled by the exact 2006-01 ratio (84.5004 / 100). The dollar NODE's
   validated 2006+ decoding config is untouched; only the transmission
   estimation uses the long history.
3. Common sample: joint non-missing months of all seven features. Gas
   is the binding constraint (Henry Hub starts 1997), not the dollar.

Registered claims, scored below, published whichever way they fall:
G5a credit -> equities and equities -> credit both >= 3 percent.
G5b dollar -> gold >= 3 percent.
G5c dollar -> oil >= 3 percent.
G5d oil -> credit < 3 percent (investment grade should take little
    directly from oil).
G5e Non-regression: oil -> inflation remains oil's largest outgoing
    edge, and inflation remains the largest net receiver.
"""

import json
import os

import numpy as np
import pandas as pd

from instrument.hmm import rolling_z
from instrument import nodes

RATIO_2006_01 = 84.5004 / 100.0


def long_dollar(data_dir):
    major = pd.read_csv(f"{data_dir}/usd_major_hist.csv", index_col=0)
    major = major["usd_major"]
    major.index = pd.PeriodIndex(major.index, freq="M")
    broad = pd.read_csv(f"{data_dir}/usd_broad.csv", index_col=0)["usd"]
    broad.index = pd.PeriodIndex(broad.index, freq="M")
    return pd.concat([major.loc[:pd.Period("2005-12", "M")],
                      broad * RATIO_2006_01])


def var_gfevd(Y, p=2, H=12):
    Yv = Y.to_numpy()
    T, k = Yv.shape
    Z = np.column_stack([np.ones(T - p)] +
                        [Yv[p - l - 1:T - l - 1] for l in range(p)])
    B = np.linalg.lstsq(Z, Yv[p:], rcond=None)[0]
    U = Yv[p:] - Z @ B
    Sig = U.T @ U / (len(U) - Z.shape[1])
    A = [B[1 + l * k:1 + (l + 1) * k].T for l in range(p)]
    Psi = [np.eye(k)]
    for h in range(1, H):
        Ph = np.zeros((k, k))
        for l in range(min(h, p)):
            Ph += A[l] @ Psi[h - 1 - l]
        Psi.append(Ph)
    num = np.zeros((k, k))
    den = np.zeros(k)
    for h in range(H):
        Ph = Psi[h]
        num += (Ph @ Sig) ** 2 / np.diag(Sig)[None, :]
        den += np.diag(Ph @ Sig @ Ph.T)
    theta = num / den[:, None]
    return theta / theta.sum(1, keepdims=True)


def legacy_primaries(data_dir, asof):
    L = nodes.build_features(data_dir, asof)
    d3_long = rolling_z(np.log(long_dollar(data_dir)).diff(3), 120, 24)
    return {
        "oil": L["f"]["oil"], "gas": L["zg"],
        "inflation": L["fi"]["acc"].reindex(L["f"].index),
        "equities": L["fe"]["mom"], "gold": L["zau"],
        "dollar": d3_long.reindex(L["f"].index),
        "credit": L["fc"]["chg"].reindex(L["f"].index)}


def estimate(data_dir, asof):
    L = nodes.build_features(data_dir, asof)
    d3_long = rolling_z(np.log(long_dollar(data_dir)).diff(3), 120, 24)
    Y = pd.DataFrame({
        "oil": L["f"]["oil"], "gas": L["zg"],
        "inflation": L["fi"]["acc"].reindex(L["f"].index),
        "equities": L["fe"]["mom"], "gold": L["zau"],
        "dollar": d3_long.reindex(L["f"].index),
        "credit": L["fc"]["chg"].reindex(L["f"].index)}).dropna()
    theta = var_gfevd(Y)
    names = list(Y.columns)
    off = theta - np.diag(np.diag(theta))
    to_others = off.sum(0) * 100
    from_others = off.sum(1) * 100
    pair = {f"{a}->{b}": round(float(theta[j, i] * 100), 1)
            for i, a in enumerate(names)
            for j, b in enumerate(names) if i != j}
    net = {n: round(float(to_others[i] - from_others[i]), 1)
           for i, n in enumerate(names)}

    def p(a, b):
        return pair[f"{a}->{b}"]

    oil_out = {b: p("oil", b) for b in names if b != "oil"}
    claims = {
        "G5a": {"claim": "credit<->equities both >= 3",
                "value": {"credit->equities": p("credit", "equities"),
                          "equities->credit": p("equities", "credit")},
                "hit": p("credit", "equities") >= 3
                and p("equities", "credit") >= 3},
        "G5b": {"claim": "dollar->gold >= 3",
                "value": p("dollar", "gold"),
                "hit": p("dollar", "gold") >= 3},
        "G5c": {"claim": "dollar->oil >= 3",
                "value": p("dollar", "oil"),
                "hit": p("dollar", "oil") >= 3},
        "G5d": {"claim": "oil->credit < 3",
                "value": p("oil", "credit"),
                "hit": p("oil", "credit") < 3},
        "G5e": {"claim": "oil->inflation largest oil edge; "
                         "inflation largest net receiver",
                "value": {"oil_out": oil_out, "net": net},
                "hit": max(oil_out, key=oil_out.get) == "inflation"
                and min(net, key=net.get) == "inflation"},
    }
    return {"sample": [str(Y.index[0]), str(Y.index[-1])],
            "months": len(Y), "spill": pair, "net": net,
            "claims": {k: {"claim": v["claim"], "value": v["value"],
                           "hit": bool(v["hit"])}
                       for k, v in claims.items()}}


def frames(data_dir, asof, window=120, step=6):
    """Rolling seven-node GFEVD frames for the time scrubber. Same
    method, same features, estimated on trailing windows."""
    L = nodes.build_features(data_dir, asof)
    d3_long = rolling_z(np.log(long_dollar(data_dir)).diff(3), 120, 24)
    Y = pd.DataFrame({
        "oil": L["f"]["oil"], "gas": L["zg"],
        "inflation": L["fi"]["acc"].reindex(L["f"].index),
        "equities": L["fe"]["mom"], "gold": L["zau"],
        "dollar": d3_long.reindex(L["f"].index),
        "credit": L["fc"]["chg"].reindex(L["f"].index)}).dropna()
    names = list(Y.columns)
    out = []
    i = window
    while i <= len(Y):
        th = var_gfevd(Y.iloc[i - window:i])
        pair = {f"{a}->{b}": round(float(th[j, m] * 100), 1)
                for m, a in enumerate(names)
                for j, b in enumerate(names) if m != j}
        out.append({"end": str(Y.index[i - 1]), "spill": pair})
        i += step
    if out and out[-1]["end"] != str(Y.index[-1]):
        th = var_gfevd(Y.iloc[-window:])
        pair = {f"{a}->{b}": round(float(th[j, m] * 100), 1)
                for m, a in enumerate(names)
                for j, b in enumerate(names) if m != j}
        out.append({"end": str(Y.index[-1]), "spill": pair})
    return out


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(root, "data")
    res = estimate(data, "2026-08")
    print(json.dumps(res["claims"], indent=1))
    print("sample:", res["sample"], res["months"], "months")
    top = sorted(res["spill"].items(), key=lambda x: -x[1])[:10]
    print("top edges:", top)
    print("net:", res["net"])
    json.dump(res, open(os.path.join(root, "state",
                                     "transmission_7node.json"), "w"),
              indent=1)


def block_estimate(primaries, blocks, months):
    """GFEVD on block series: equal-weight mean of available member
    primary features (registered). Returns block names and spill
    matrix on the longest common sample."""
    cols = {}
    for b, members in blocks.items():
        avail = [primaries[m] for m in members if m in primaries]
        if not avail:
            continue
        df = pd.concat(avail, axis=1)
        cols[b] = df.mean(axis=1, skipna=True)
    P = pd.DataFrame(cols).dropna()
    names = list(P.columns)
    S = var_gfevd(P) * 100.0
    edges = []
    n = len(names)
    for i in range(n):
        for j in range(n):
            if i != j and S[i, j] >= 3.0:
                edges.append({"src": names[j], "dst": names[i],
                              "pct": round(float(S[i, j]), 1)})
    return {"blocks": names, "edges": edges,
            "sample": [str(P.index[0]), str(P.index[-1])],
            "months": int(len(P))}


def sparse_map(primaries, months, window=96, step=6,
               thr=3.0, stability=0.7):
    """Rolling-window GFEVD over all instrument primaries; an edge
    survives only if it clears thr percent in at least stability of
    the windows (registered)."""
    P = pd.DataFrame(primaries).dropna()
    names = list(P.columns)
    X = P.to_numpy(float)
    n = len(names)
    starts = list(range(0, len(P) - window + 1, step))
    if not starts:
        return {"nodes": names, "edges": [], "windows": 0}
    counts = np.zeros((n, n)); sums = np.zeros((n, n))
    for s in starts:
        S = var_gfevd(P.iloc[s:s + window]) * 100.0
        counts += (S >= thr).astype(float)
        sums += S
    frac = counts / len(starts)
    mean_S = sums / len(starts)
    edges = []
    for i in range(n):
        for j in range(n):
            if i != j and frac[i, j] >= stability:
                edges.append({"src": names[j], "dst": names[i],
                              "pct": round(float(sums[i, j]
                                                 / len(starts)), 1),
                              "stability": round(float(frac[i, j]),
                                                 2)})
    return {"nodes": names, "edges": edges,
            "windows": len(starts),
            "mean_matrix": mean_S.round(2).tolist(),
            "sample": [str(P.index[0]), str(P.index[-1])]}


def block_frames(primaries, blocks, window=120, step=6, thr=3.0):
    """Rolling GFEVD on block series (equal-weight mean of available
    members). Each frame records which members actually inform each
    block in that window (>= 80 percent coverage), so the replay can
    say what it is made of."""
    cols, mem = {}, {}
    for b, members in blocks.items():
        avail = {m: primaries[m] for m in members if m in primaries}
        if not avail:
            continue
        df = pd.concat(avail.values(), axis=1)
        df.columns = list(avail.keys())
        cols[b] = df.mean(axis=1, skipna=True)
        mem[b] = df
    P = pd.DataFrame(cols).dropna(how="all").dropna()
    names = list(P.columns)
    frames = []
    for s0 in range(0, len(P) - window + 1, step):
        W = P.iloc[s0:s0 + window]
        S = var_gfevd(W) * 100.0
        edges = []
        for i in range(len(names)):
            for j in range(len(names)):
                if i != j and S[i, j] >= thr:
                    edges.append({"src": names[j], "dst": names[i],
                                  "pct": round(float(S[i, j]), 1)})
        comp = {}
        for b in names:
            sub = mem[b].loc[W.index]
            comp[b] = [m for m in sub.columns
                       if sub[m].notna().mean() >= 0.8]
        frames.append({"end": str(W.index[-1]), "edges": edges,
                       "members": comp})
    return {"blocks": names, "frames": frames,
            "window": window, "step": step}
