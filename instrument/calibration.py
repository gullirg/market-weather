"""The calibration audit, registered as REG-CAL before it was run.

No confidence number this system prints had ever been audited against
outcomes. This module asks one question: when the instrument printed a
maximum posterior of p at month t, how often was the state it printed
the state the full record later settled on?

Method, as registered:
  1. Causal decode. For every instrument and every month t, decode
     using observations through t only. For fixed parameters the
     endpoint of a smoothed decode on data through t is exactly the
     filtered posterior at t, so one forward pass per instrument gives
     the whole expanding window exactly.
  2. Ground truth. The final full sample modal state at t, which is
     what the live pages publish.
  3. Reliability. p bucketed into deciles, agreement frequency per
     bucket.
  4. Recalibration. Isotonic regression of agreement on p fitted on
     months before 2015-01, validated on 2015-01 onward.
  5. Adoption. Applied to displayed confidences, display layer only,
     if and only if validation Brier improves by at least 5 percent.

Disclosed in the registration: EM-fitted spreads and the deflator
splice constant are held at their full sample values, because the
legacy decoders are untouchable. The audit therefore isolates the
effect of smoothing, not of parameter drift.

Nothing here writes to a decoder. Everything is read-only
reconstruction plus a display-layer mapping.
"""

import json
import os

import numpy as np
import pandas as pd

from instrument import nodes, network as net
from instrument.hmm import TemplateHMM, SigmaHMM, em_sigmas

AUDIT_START = "1998-01"
TRAIN_END = "2015-01"      # training is strictly before this month
BRIER_IMPROVEMENT = 0.05
DECILES = 10


def _trim(X, idx):
    ok = np.where((~np.isnan(X)).any(1))[0]
    if len(ok) == 0:
        return None, None
    return X[ok[0]:], idx[ok[0]:]


def _em_spec(fdf, tpl, states):
    Xn, ni = _trim(fdf.to_numpy(float), fdf.index)
    if Xn is None:
        return None
    sg = em_sigmas(Xn, ni, np.asarray(tpl, float))
    return {"X": Xn, "index": ni, "hmm": SigmaHMM(np.asarray(tpl, float), sg),
            "states": states}


def founding_specs(data_dir, asof):
    """Read-only reconstruction of the seven legacy decoders from the
    locals build_features already returns. Nothing is modified."""
    L = nodes.build_features(data_dir, asof)
    f, idx = L["f"], L["f"].index
    out = {}

    X = f[["oil", "eq", "metals", "rv", "vix", "bw", "inv"]].to_numpy(float)
    s0 = np.where(~np.isnan(X[:, 0]))[0][0]
    Xo, io = X[s0:], idx[s0:]
    anchors = {s: v for s, v in nodes.OIL_ANCHORS.items()}
    sig = em_sigmas(Xo, io, nodes.OIL_T, anchors=anchors)
    out["oil"] = {"X": Xo, "index": io,
                  "hmm": SigmaHMM(nodes.OIL_T, sig),
                  "states": nodes.OIL_STATES, "primary": f["oil"]}

    gas_X = np.column_stack([L["zg"], L["zgv"], L["zrel"]])
    out["gas"] = {"X": gas_X, "index": idx,
                  "hmm": TemplateHMM(np.asarray(nodes.GAS_T, float)),
                  "states": nodes.GAS_STATES, "primary": L["zg"]}

    gold_X = np.column_stack([L["zau"], f["vix"], L["zry"]])
    out["gold"] = {"X": gold_X, "index": idx,
                   "hmm": TemplateHMM(np.asarray(nodes.GOLD_T, float)),
                   "states": nodes.GOLD_STATES, "primary": L["zau"]}

    for name, key, tpl, states, prim in [
            ("dollar", "fd", nodes.DOL_T, nodes.DOL_STATES, "d3"),
            ("credit", "fc", nodes.CR_T, nodes.CR_STATES, "lvl"),
            ("inflation", "fi", nodes.INF_T, nodes.INF_STATES, "lvl"),
            ("equities", "fe", nodes.EQ_T, nodes.EQ_STATES, "mom")]:
        spec = _em_spec(L[key], tpl, states)
        if spec is not None:
            spec["primary"] = L[key][prim]
            out[name] = spec
    return out


def network_specs(data_dir, asof):
    A = pd.Period(asof, "M")
    F = nodes.load_feeds(data_dir)
    F = net._load_extra(data_dir, F)
    defl = nodes._splice_deflator(F)
    out = {}
    for name, spec in net.REGISTRY.items():
        try:
            fdf = spec["build"](F, defl).loc[:A]
        except Exception:
            continue
        X, ni = _trim(fdf.to_numpy(float), fdf.index)
        if X is None:
            continue
        out[name] = {"X": X, "index": ni,
                     "hmm": TemplateHMM(np.asarray(spec["T"], float),
                                        p_stay=0.90),
                     "states": spec["states"],
                     "primary": fdf.iloc[:, 0]}
    return out


def audit_one(name, spec, start=AUDIT_START):
    """One instrument: causal state and confidence against the final
    full sample state, month by month."""
    X = np.asarray(spec["X"], float).copy()
    X[~np.isfinite(X)] = np.nan
    idx = spec["index"]
    smoothed = spec["hmm"].posteriors(X)
    causal = spec["hmm"].filtered(X)
    states = spec["states"]
    truth = pd.Series([states[i] for i in smoothed.argmax(1)], index=idx)
    cs = pd.Series([states[i] for i in causal.argmax(1)], index=idx)
    cp = pd.Series(causal.max(1), index=idx)
    pv = spec["primary"].dropna()
    if len(pv):
        last = pv.index[-1]
        truth, cs, cp = truth.loc[:last], cs.loc[:last], cp.loc[:last]
    lo = pd.Period(start, "M")
    keep = truth.index >= lo
    rows = []
    for m, t_, c_, p_ in zip(truth.index[keep], truth[keep], cs[keep],
                             cp[keep]):
        if not (isinstance(t_, str) and isinstance(c_, str)):
            continue
        rows.append({"instrument": name, "month": str(m),
                     "p": float(p_), "agree": int(t_ == c_)})
    return rows


def _worker(args):
    data_dir, asof, name, kind = args
    specs = (founding_specs(data_dir, asof) if kind == "founding"
             else network_specs(data_dir, asof))
    if name not in specs:
        return name, []
    return name, audit_one(name, specs[name])


def collect(data_dir, asof, ckpt_dir, workers=None):
    """Per-instrument checkpoints so an interruption resumes."""
    from concurrent.futures import ProcessPoolExecutor
    os.makedirs(ckpt_dir, exist_ok=True)
    founding = list(founding_specs(data_dir, asof))
    network = [n for n in net.REGISTRY]
    jobs = ([(data_dir, asof, n, "founding") for n in founding]
            + [(data_dir, asof, n, "network") for n in network])
    todo, rows = [], []
    for j in jobs:
        p = os.path.join(ckpt_dir, f"{j[2]}.json")
        if os.path.exists(p):
            rows.extend(json.load(open(p)))
        else:
            todo.append(j)
    if todo:
        w = workers or max(1, min(8, (os.cpu_count() or 2) - 2))
        with ProcessPoolExecutor(max_workers=w) as ex:
            for name, r in ex.map(_worker, todo):
                json.dump(r, open(os.path.join(ckpt_dir,
                                               f"{name}.json"), "w"))
                rows.extend(r)
    return rows


def reliability(rows, buckets=DECILES):
    p = np.array([r["p"] for r in rows])
    a = np.array([r["agree"] for r in rows], float)
    edges = np.linspace(0.0, 1.0, buckets + 1)
    out = []
    for i in range(buckets):
        lo, hi = edges[i], edges[i + 1]
        sel = (p >= lo) & (p < hi) if i < buckets - 1 else (p >= lo)
        n = int(sel.sum())
        if n == 0:
            out.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": 0,
                        "mean_p": None, "agreement": None})
            continue
        out.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": n,
                    "mean_p": round(float(p[sel].mean()), 4),
                    "agreement": round(float(a[sel].mean()), 4)})
    return out


def run(rows, train_end=TRAIN_END, threshold=BRIER_IMPROVEMENT):
    from sklearn.isotonic import IsotonicRegression
    cut = pd.Period(train_end, "M")
    tr = [r for r in rows if pd.Period(r["month"], "M") < cut]
    va = [r for r in rows if pd.Period(r["month"], "M") >= cut]
    ptr = np.array([r["p"] for r in tr])
    atr = np.array([r["agree"] for r in tr], float)
    pva = np.array([r["p"] for r in va])
    ava = np.array([r["agree"] for r in va], float)
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(ptr, atr)
    cal = iso.predict(pva)
    brier_raw = float(np.mean((pva - ava) ** 2))
    brier_cal = float(np.mean((cal - ava) ** 2))
    rel = (brier_raw - brier_cal) / brier_raw if brier_raw > 0 else 0.0
    adopt = bool(rel >= threshold)
    grid = np.round(np.linspace(0.0, 1.0, 21), 2)
    return {"id": "CAL-1",
            "n_total": len(rows), "n_train": len(tr), "n_valid": len(va),
            "train_span": [tr[0]["month"], tr[-1]["month"]] if tr else None,
            "valid_span": [va[0]["month"], va[-1]["month"]] if va else None,
            "raw_mean_p": round(float(pva.mean()), 4),
            "raw_agreement": round(float(ava.mean()), 4),
            "brier_raw": round(brier_raw, 5),
            "brier_calibrated": round(brier_cal, 5),
            "relative_improvement": round(float(rel), 4),
            "threshold": threshold, "adopted": adopt,
            "reliability": reliability(rows),
            "reliability_valid": reliability(va),
            "mapping": {str(g): round(float(v), 4)
                        for g, v in zip(grid, iso.predict(grid))}}
