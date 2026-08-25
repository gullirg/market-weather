"""Run BACKTEST-1: the replayed record.

  python3 scripts/run_backtest1.py [asof]

Registered as BACKTEST-1 before this ran. One run and one scoring: the
script refuses to overwrite an existing state/backtest1.json, because
the registration allows the replayed record no second estimation and no
entries after the first run.
"""

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrument import backtest as bt

OUT = os.path.join(ROOT, "state", "backtest1.json")


def main(asof="2026-08"):
    if os.path.exists(OUT):
        sys.exit(f"refusing to rerun: {OUT} exists and BACKTEST-1 "
                 f"registered one run and one scoring")
    t0 = time.time()
    seen = [0]

    def progress(t, n, s):
        seen[0] += 1
        if seen[0] % 25 == 0:
            print(f"  {t}  {seen[0]:>3} origins  {time.time() - t0:.0f}s")

    r = bt.run(os.path.join(ROOT, "data"), asof, progress=progress)
    json.dump(r, open(OUT, "w"), indent=1)

    a, pre, post = r["aggregate"], r["pre_2016"], r["post_2016"]
    print(f"\nreplayed record, laboratory: {r['window']}")
    print(f"  slates {a['slates']}  hits {a['hits']}  misses "
          f"{a['misses']}  win rate {a['win_rate']}")
    print(f"  claims {a['claims']}, of which {a['claim_wins']} beat "
          f"their own baseline")
    print(f"  before {r['dur1_cut']}: {pre['hits']}/{pre['slates']} "
          f"= {pre['win_rate']}")
    print(f"  from   {r['dur1_cut']}: {post['hits']}/{post['slates']} "
          f"= {post['win_rate']}")
    print(f"  synoptic gate open at {r['gate_open_origins']} origins")
    for k, v in sorted(r["by_kind"].items()):
        print(f"  {k:14s} {v['wins']}/{v['claims']} claims beat baseline")
    print(f"\n{r['caveat']}")
    print(f"\n{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(*sys.argv[1:])
