"""BACKTEST-1: the replayed record.

Registered as BACKTEST-1 before this ran. For every origin month from
2002-01 through 2026-05 the bulletin claim slate of B-CLAIMS-REG is
generated causally and scored at its maturity against the realized
decoded states, with a slate level verdict per PROPER-SCORE-REG-2.

Causality is the convention CAL-1, HORIZON-1 and HORIZON-2 already use,
adopted here unchanged rather than invented: decoder emission
parameters and the state alphabet come from a single fit on the full
sample, the analysis state at an origin is the argmax of the filtered
causal posterior at that month, and the forecaster is fit only on the
causal decoded history through the origin month. Realized states are
the full sample smoothed decode, which is what the live pipeline
resolves a matured claim against.

Nothing here re-implements a scoring rule. The claims are built in the
shape analyst.bulletin.forward_claims builds them and resolved by
analyst.bulletin._resolve and analyst.bulletin._persistence_p
unchanged, so the replay is scored by the same code the live record is.

This is a replay of the current architecture over revised data, not a
reconstruction of what could have been known at the time. The caveat
registered with it says so and prints beside the row.
"""

import numpy as np
import pandas as pd

from analyst import bulletin as B
from instrument import calibration as cal, hazards, network as net
from instrument import nodes, synoptic
from instrument.outlook import semi_markov, simulate

FIRST_ORIGIN = "2002-01"
LAST_ORIGIN = "2026-05"
HORIZON_M = B.CONT_HORIZON_M
N_PATHS = 2000
SYN_SEED = 3000
DUR1_CUT = "2016-01"
CAVEAT = ("replayed on revised data with an architecture designed in "
          "hindsight; the live record below is the uncontaminated test")


def _decoded(spec):
    """Causal and realized decodes for one instrument, on the registered
    convention: filtered posterior for what was knowable at the origin,
    smoothed posterior for what the record later settled on."""
    X = np.asarray(spec["X"], float).copy()
    X[~np.isfinite(X)] = np.nan
    states = spec["states"]
    causal = spec["hmm"].filtered(X)
    smoothed = spec["hmm"].posteriors(X)
    idx = spec["index"]
    return {"index": idx, "states": states, "causal": causal,
            "cstate": [states[i] for i in causal.argmax(1)],
            "truth": pd.Series([states[i] for i in smoothed.argmax(1)],
                               index=idx)}


def specs_in_registered_order(data_dir, asof):
    """The seven founding decoders in founding_specs order then the
    fifteen network decoders in REGISTRY order, each with the seed
    BACKTEST-1 registered for it."""
    f = cal.founding_specs(data_dir, asof)
    n = cal.network_specs(data_dir, asof)
    out = []
    for i, name in enumerate(f):
        out.append((name, f[name], 1000 + i))
    for i, name in enumerate(net.REGISTRY):
        if name in n:
            out.append((name, n[name], 2000 + i))
    return out


def _syn_series(preds, months):
    """The synoptic series over a prefix. Only the registered checks
    whose windows have closed inside the prefix are evaluated, which is
    the registered replay gate rule; the series itself is computed by
    synoptic.run untouched."""
    closed = [c for c in synoptic.CHECKS
              if pd.Period(c[2], "M") <= months[-1]]
    keep = synoptic.CHECKS
    try:
        synoptic.CHECKS = closed
        out = synoptic.run(preds, months)
    finally:
        synoptic.CHECKS = keep
    return out, closed


def _state_claim(cid, kind, node, target, p, matures, quarter=None):
    side = B._side(p)
    if side is None:
        return None
    return {"id": cid, "group": B.CLAIM_GROUP, "status": "pending",
            "auto": True,
            "claim": (f"{kind}, replayed: the chance that {node} is "
                      f"still {target} three months later is {p}"),
            "window": f"{matures}..{matures}", "matures": str(matures),
            "rule": {"kind": "state", "node": node, "target": target,
                     "scoring": "brier", "mode": "present", "p": p,
                     "side": side, "claim_kind": kind,
                     "outlook_quarter": quarter}}


def slate_for_origin(t, dec, rngs, syn, oil_causal, real_brent):
    """The claim slate one origin month registers, in the shape
    forward_claims registers it."""
    claims = []
    tgt = t + HORIZON_M
    for name, d, rng in dec:
        idx = d["index"]
        pos = idx.get_indexer([t])[0]
        if pos < 0:
            continue
        seq = d["cstate"][:pos + 1]
        if len(set(seq)) < 2:
            continue
        sm = semi_markov(seq)
        if sm is None:
            continue
        post_now = {d["states"][j]: float(d["causal"][pos, j])
                    for j in range(len(d["states"]))}
        try:
            dist, _ = simulate(sm, seq, post_now, rng, n_paths=N_PATHS,
                               horizons=[HORIZON_M])
        except Exception:
            continue
        st = d["cstate"][pos]
        p = round(float((dist.get(HORIZON_M) or {}).get(st, 0.0)), 4)
        if abs(p - 0.5) < B.CONT_BAND:
            continue
        c = _state_claim(f"R{t}-CONT-{name}", "continuation", name, st,
                         p, tgt)
        if c:
            claims.append(c)

    if syn is not None:
        sseq, spost, srng = syn["seq"], syn["post"], syn["rng"]
        sm = semi_markov(sseq)
        if sm is not None and len(set(sseq)) >= 2:
            try:
                dist, _ = simulate(sm, sseq, spost, srng,
                                   n_paths=N_PATHS, horizons=[HORIZON_M])
            except Exception:
                dist = {}
            st = sseq[-1]
            p = round(float((dist.get(HORIZON_M) or {}).get(st, 0.0)), 4)
            c = _state_claim(f"R{t}-SYN", "synoptic", "synoptic", st, p,
                             tgt)
            if c:
                claims.append(c)

    # risk lamp, from the causal oil decode and real Brent through t
    try:
        hz = hazards.run(oil_causal, real_brent)
    except Exception:
        hz = None
    if hz:
        st = hz["current"]["state"]
        tail = (hz["lamp"].get(st) or {}).get("tail_freq")
        side = B._side(tail)
        if tail is not None and side is not None:
            claims.append({
                "id": f"R{t}-LAMP", "group": B.CLAIM_GROUP,
                "status": "pending", "auto": True,
                "claim": (f"risk lamp, replayed: from the {st} regime "
                          f"the stated chance of a real Brent drawdown "
                          f"of fifteen percent or worse within three "
                          f"months is {tail}"),
                "window": f"{t + 1}..{t + HORIZON_M}",
                "matures": str(t + HORIZON_M),
                "rule": {"kind": "drawdown", "series": "real_brent",
                         "scoring": "brier", "base": str(t),
                         "threshold_pct": B.LAMP_THRESHOLD_PCT,
                         "p": tail, "side": side}})
    return claims


def score_slate(t, claims, preds, series):
    """Resolve every claim through the live resolver and return the
    slate verdict PROPER-SCORE-REG-2 defines."""
    rows = []
    for c in claims:
        a = pd.Period(c["window"].split("..")[0], "M")
        b = pd.Period(c["window"].split("..")[1], "M")
        res = B._resolve(c["rule"], a, b, preds, series)
        if res is None:
            continue
        status, note, m = res
        if m.get("brier") is None or m.get("brier_baseline") is None:
            continue
        rows.append({"id": c["id"], "kind": c["rule"].get("claim_kind")
                     or c["rule"]["kind"], "status": status,
                     "brier": m["brier"],
                     "brier_baseline": m["brier_baseline"],
                     "p": c["rule"]["p"]})
    if not rows or len(rows) != len(claims):
        return None
    mc = round(sum(r["brier"] for r in rows) / len(rows), 5)
    mb = round(sum(r["brier_baseline"] for r in rows) / len(rows), 5)
    wins = sum(1 for r in rows if r["brier"] < r["brier_baseline"])
    return {"month": str(t), "status": "hit" if mc < mb else "miss",
            "claims": len(rows), "brier": mc, "brier_baseline": mb,
            "claim_wins": wins, "rows": rows}


def _tally(slates):
    hits = sum(1 for s in slates if s["status"] == "hit")
    n = len(slates)
    return {"slates": n, "hits": hits, "misses": n - hits,
            "win_rate": round(hits / n, 4) if n else None,
            "claims": sum(s["claims"] for s in slates),
            "claim_wins": sum(s["claim_wins"] for s in slates)}


def run(data_dir="data", asof="2026-08", first=FIRST_ORIGIN,
        last=LAST_ORIGIN, progress=None):
    rows = specs_in_registered_order(data_dir, asof)
    dec = []
    for name, spec, seed in rows:
        d = _decoded(spec)
        dec.append((name, d, np.random.default_rng(seed)))
    preds = {name: d["truth"] for name, d, _ in dec}

    F = nodes.build_features(data_dir, asof)["F"]
    real_brent = nodes.real_brent(F)

    # the realized synoptic series, full sample, is what a matured
    # synoptic claim resolves against, exactly as live
    full_months = pd.PeriodIndex(sorted(set(
        m for d in preds.values() for m in d.index)), freq="M")
    syn_full, _ = _syn_series(preds, full_months)
    preds["synoptic"] = pd.Series(
        {pd.Period(k, "M"): v for k, v in syn_full["series"].items()}
    ).sort_index()

    oil = dict((n, d) for n, d, _ in dec)["oil"]
    oil_causal = pd.Series(oil["cstate"], index=oil["index"])
    syn_rng = np.random.default_rng(SYN_SEED)

    origins = pd.period_range(first, last, freq="M")
    slates, gate_open = [], 0
    for t in origins:
        # causal synoptic through t, and the replay gate
        cpreds = {n: pd.Series(d["cstate"], index=d["index"]).loc[:t]
                  for n, d, _ in dec}
        months = pd.PeriodIndex(sorted(set(
            m for s in cpreds.values() for m in s.index)), freq="M")
        months = months[months <= t]
        syn = None
        try:
            sr, closed = _syn_series(cpreds, months)
            open_ = bool(closed) and all(c["hit"] for c in sr["checks"])
            if open_:
                gate_open += 1
                sseq = [sr["series"][str(m)] for m in months
                        if str(m) in sr["series"]]
                syn = {"seq": sseq, "rng": syn_rng,
                       "post": {sseq[-1]: 1.0}}
        except Exception:
            syn = None
        claims = slate_for_origin(t, dec, None, syn, oil_causal.loc[:t],
                                  real_brent.loc[:t])
        s = score_slate(t, claims, preds, {"real_brent": real_brent})
        if s:
            slates.append(s)
        if progress:
            progress(t, len(claims), s)

    cut = pd.Period(DUR1_CUT, "M")
    pre = [s for s in slates if pd.Period(s["month"], "M") < cut]
    post = [s for s in slates if pd.Period(s["month"], "M") >= cut]
    kinds = {}
    for s in slates:
        for r in s["rows"]:
            k = kinds.setdefault(r["kind"], {"claims": 0, "wins": 0})
            k["claims"] += 1
            k["wins"] += 1 if r["brier"] < r["brier_baseline"] else 0
    return {"id": "BACKTEST-1", "registration": "BACKTEST-1",
            "estimated_at": asof, "window": f"{first}..{last}",
            "label": "replayed record, laboratory",
            "caveat": CAVEAT,
            "paths": N_PATHS, "horizon_months": HORIZON_M,
            "band": B.CONT_BAND, "dur1_cut": DUR1_CUT,
            "gate_open_origins": gate_open,
            "aggregate": _tally(slates),
            "pre_2016": _tally(pre), "post_2016": _tally(post),
            "by_kind": kinds,
            "row": [{"month": s["month"], "status": s["status"],
                     "claims": s["claims"], "brier": s["brier"],
                     "brier_baseline": s["brier_baseline"],
                     "claim_wins": s["claim_wins"]} for s in slates]}
