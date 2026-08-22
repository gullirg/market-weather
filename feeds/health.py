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


# Standalone monitored feeds: landed on the host, watched by the
# monitor, and not yet wired to any registered instrument. Adding a
# feed here is always allowed; it changes no decoder.
MONITORED = {"HY OAS": ("hy_oas.csv", "hy_oas"),
             "IG OAS": ("ig_oas.csv", "ig_oas"),
             "OVX": ("ovx.csv", "ovx"),
             "claims": ("claims.csv", "claims"),
             "mortgage 30y": ("mortgage.csv", "mortgage"),
             "Fed balance sheet": ("fed_bs.csv", "fed_bs"),
             "bitcoin": ("btc.csv", "btc"),
             "EU equities": ("eu_equities.csv", "eu_equities")}


def load_monitored(data_dir):
    """Load whichever standalone monitored feeds are present."""
    import os
    out = {}
    for name, (fname, col) in MONITORED.items():
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            continue
        s = pd.read_csv(path, index_col=0)[col]
        s.index = pd.PeriodIndex(s.index, freq="M")
        out[name] = s
    return out


def run_all(F, monthly_map):
    """monthly_map: name -> monthly series. Returns (report, masked_names)."""
    report = [check(s, n) for n, s in monthly_map.items()]
    masked = [r["feed"] for r in report if r["FLAG"]]
    return report, masked
