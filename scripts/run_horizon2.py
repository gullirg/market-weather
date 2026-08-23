"""Run HORIZON-2: the identical pseudo-issue set scored against the
persistence baseline.

  python3 scripts/run_horizon2.py [asof]

Identical means identical. The job list, seeds and order match
run_horizon.py exactly, so the forecasts are the same draws; the only
change is the baseline. That the forecasts are unchanged is asserted
against HORIZON-1's own recorded per-lead scores before anything is
written, and HORIZON-1's frozen result is never rewritten.
"""

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrument import calibration as cal, horizon, network as net


def _job(args):
    data_dir, asof, name, kind, seed = args
    specs = (cal.founding_specs(data_dir, asof) if kind == "founding"
             else cal.network_specs(data_dir, asof))
    if name not in specs:
        return name, None
    return name, horizon.audit_instrument(name, specs[name], seed=seed)


def jobs_for(data, asof):
    """The same list, in the same order, with the same seeds as
    run_horizon.py. Changing this changes the forecasts."""
    founding = list(cal.founding_specs(data, asof))
    out = [(data, asof, n, "founding", 1000 + i)
           for i, n in enumerate(founding)]
    out += [(data, asof, n, "network", 2000 + i)
            for i, n in enumerate(net.REGISTRY)]
    return out


def main(asof="2026-08"):
    data = os.path.join(ROOT, "data")
    ck = os.path.join(ROOT, "state", "horizon2_ckpt")
    os.makedirs(ck, exist_ok=True)
    rows, todo = [], []
    for j in jobs_for(data, asof):
        p = os.path.join(ck, f"{j[2]}.json")
        if os.path.exists(p):
            d = json.load(open(p))
            if d:
                rows.append(d)
        else:
            todo.append(j)
    if todo:
        w = max(1, min(8, (os.cpu_count() or 2) - 2))
        with ProcessPoolExecutor(max_workers=w) as ex:
            for name, r in ex.map(_job, todo):
                json.dump(r, open(os.path.join(ck, f"{name}.json"), "w"))
                if r:
                    rows.append(r)

    # the forecasts must be identical to HORIZON-1's before anything
    # is written
    h1 = json.load(open(os.path.join(ROOT, "state", "horizon1.json")))
    check = horizon.pool(rows, baseline="c")
    for a, b in zip(h1["curve"], check["curve"]):
        assert a["lead"] == b["lead"]
        assert a["n"] == b["n"], (a["lead"], a["n"], b["n"])
        assert abs(a["rps_forecast"] - b["rps_baseline"] * 0 -
                   b["rps_forecast"]) < 1e-9, (a["lead"],
                                               a["rps_forecast"],
                                               b["rps_forecast"])
    print(f"forecasts identical to HORIZON-1 at every lead over "
          f"{check['issues']} pseudo-issues")

    out = horizon.pool(rows, baseline="p")
    out["id"] = "HORIZON-2"
    out["estimated_at"] = asof
    out["registration"] = "HORIZON-2"
    out["refresh"] = "yearly adjudication"
    out["baseline_name"] = "persistence"
    out["min_history_months"] = horizon.MIN_HISTORY
    out["paths"] = horizon.N_PATHS
    json.dump(out, open(os.path.join(ROOT, "state", "horizon2.json"), "w"),
              indent=1)
    print(f"\ninstruments {out['instruments']}  "
          f"pseudo-issues {out['issues']}  baseline persistence")
    print(f"{'lead':>5} {'n':>7} {'rpss':>9} {'pooled':>9} {'worst':>9}")
    for r in out["curve"]:
        if r.get("rpss") is None:
            print(f"{r['lead']:>5} {'':>7} {'no data':>9}")
            continue
        print(f"{r['lead']:>5} {r['n']:>7} {r['rpss']:>9.4f} "
              f"{r['rpss_sum_pooled']:>9.4f} "
              f"{r['rpss_worst_instrument']:>9.4f}")
    print("\nwhere the edge ends against persistence, first lead with "
          f"mean skill at or below zero: {out['edge_ends_at_lead']}")
    cr = out["per_instrument_crossing"]
    print(f"per-instrument crossing spread: {out['crossing_spread_leads']} "
          f"leads, materially different: "
          f"{out['crossing_materially_different']}")
    for n in sorted(cr, key=lambda k: (cr[k] is None, cr[k] or 0, k)):
        print(f"   {n:14s} {cr[n] if cr[n] is not None else 'never'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
