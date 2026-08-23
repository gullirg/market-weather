"""Run the calibration audit registered as REG-CAL.

  python3 scripts/run_calibration.py [asof]

Per-instrument checkpoints land in state/cal_ckpt so an interruption
resumes: delete a checkpoint to recompute that instrument.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrument import calibration as cal


def main(asof="2026-08"):
    ckpt = os.path.join(ROOT, "state", "cal_ckpt")
    rows = cal.collect(os.path.join(ROOT, "data"), asof, ckpt)
    print(f"audit rows {len(rows)} over "
          f"{len({r['instrument'] for r in rows})} instruments")
    out = cal.run(rows)
    json.dump(out, open(os.path.join(ROOT, "state",
                                     "cal_result.json"), "w"), indent=1)
    keys = ("id", "n_total", "n_train", "n_valid", "train_span",
            "valid_span", "raw_mean_p", "raw_agreement", "brier_raw",
            "brier_calibrated", "relative_improvement", "threshold",
            "adopted")
    print(json.dumps({k: out[k] for k in keys}, indent=1))
    print("\nreliability over the whole audit:")
    for b in out["reliability"]:
        if b["n"]:
            print(f"  p in [{b['lo']:.1f},{b['hi']:.1f})  n={b['n']:6d}"
                  f"  mean p={b['mean_p']:.3f}"
                  f"  agreement={b['agreement']:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
