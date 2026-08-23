"""Run HORIZON-1, the causal skill-by-lead study.

  python3 scripts/run_horizon.py [asof]

Per-instrument checkpoints land in state/horizon_ckpt so an
interruption resumes. The result is frozen in state/horizon1.json and
refreshes only at a yearly adjudication, as registered.
"""

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrument import calibration as cal, horizon


def _job(args):
    data_dir, asof, name, kind, seed = args
    specs = (cal.founding_specs(data_dir, asof) if kind == "founding"
             else cal.network_specs(data_dir, asof))
    if name not in specs:
        return name, None
    return name, horizon.audit_instrument(name, specs[name], seed=seed)


def main(asof="2026-08"):
    data = os.path.join(ROOT, "data")
    ck = os.path.join(ROOT, "state", "horizon_ckpt")
    os.makedirs(ck, exist_ok=True)
    founding = list(cal.founding_specs(data, asof))
    from instrument import network as net
    jobs, rows = [], []
    for i, n in enumerate(founding):
        jobs.append((data, asof, n, "founding", 1000 + i))
    for i, n in enumerate(net.REGISTRY):
        jobs.append((data, asof, n, "network", 2000 + i))
    todo = []
    for j in jobs:
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
    out = horizon.pool(rows)
    out["id"] = "HORIZON-1"
    out["estimated_at"] = asof
    out["registration"] = "HORIZON-1"
    out["refresh"] = "yearly adjudication"
    out["min_history_months"] = horizon.MIN_HISTORY
    out["paths"] = horizon.N_PATHS
    json.dump(out, open(os.path.join(ROOT, "state", "horizon1.json"), "w"),
              indent=1)
    print(f"instruments {out['instruments']}  pseudo-issues {out['issues']}")
    print(f"{'lead':>5} {'n':>7} {'rpss':>9} {'pooled':>9} {'worst':>9}")
    for r in out["curve"]:
        if r.get("rpss") is None:
            print(f"{r['lead']:>5} {'':>7} {'no data':>9}")
            continue
        print(f"{r['lead']:>5} {r['n']:>7} {r['rpss']:>9.4f} "
              f"{r['rpss_sum_pooled']:>9.4f} "
              f"{r['rpss_worst_instrument']:>9.4f}")
    print("\nwhere the edge ends, first lead with mean skill at or below "
          f"zero: {out['edge_ends_at_lead']}")


if __name__ == "__main__":
    main(*sys.argv[1:])
