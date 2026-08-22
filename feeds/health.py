"""Feed-health monitor, the stage-6 gatekeeper. A flagged feed is masked
upstream and the bulletin says so. Flags: a tail run of four or more
identical values, or any trailing zeros. Missing single months are gaps,
reported but not flagged."""

import numpy as np
import pandas as pd

PRICE_FEEDS = {"brent", "wti", "henry hub", "gold", "vix", "realized vol"}


def check(series, name):
    raw = series
    n = len(raw)
    vals = raw.to_numpy(float)
    last = str(raw.dropna().index[-1]) if raw.notna().any() else "never"
    run = 1
    for i in range(n - 1, 0, -1):
        if np.isfinite(vals[i]) and vals[i] == vals[i - 1]:
            run += 1
        else:
            break
    zeros_tail = 0
    for i in range(n - 1, -1, -1):
        if vals[i] == 0:
            zeros_tail += 1
        else:
            break
    gaps = int(pd.isna(raw).sum())
    flag = bool((run >= 4) or (zeros_tail >= 1) or n == 0)
    return {"feed": name, "last_obs": last, "tail_identical_run": int(run),
            "tail_zeros": int(zeros_tail), "missing_months": gaps,
            "FLAG": flag}


def run_all(F, monthly_map):
    """monthly_map: name -> monthly series. Returns (report, masked_names)."""
    report = [check(s, n) for n, s in monthly_map.items()]
    masked = [r["feed"] for r in report if r["FLAG"]]
    return report, masked
