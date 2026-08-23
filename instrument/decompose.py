"""S2, near-decomposability retested on residual structure.

Registered before computation, under the performance-1 campaign.

Diagnosis on the chain: S1 measured a within-sibling to between-sibling
mean spillover ratio of 1.34 against a registered bar of 1.5, on 14
instruments over 26 windows, and was published as an informative miss.

Hypothesis under test, stated as a hypothesis and not as a reason to
move the bar: the leak is the common factor. Everything in a macro
panel loads on one broad risk factor, and a pairwise spillover measure
counts that shared loading as a cross-family channel. Simon's thesis is
about residual structure once the common mode is taken out. The bar
stays at 1.5 either way.

S2a, the common-factor removal:
  1. Panel: the primary feature of every live instrument, the same
     primaries the sparse map uses, over their common sample.
  2. Each column standardized to zero mean and unit variance over that
     sample.
  3. The first principal component of the standardized panel is
     removed, leaving residuals.
  4. The sparse map's rolling GFEVD is rerun on the residuals with its
     registered settings unchanged: 96 month windows, step 6.
  5. The mean spillover matrix is averaged over windows, and the mean
     of the directed within-sibling entries is compared to the mean of
     the directed between-sibling entries. The registered bar is 1.5,
     unchanged from S1.

Sibling sets, S1's four extended only where the composition tree names
children that are now live:
  energy      oil, gas, coal, uranium
  currencies  dollar, euro, yen, yuan, sterling
  rates       curve, real_yield, breakevens, inflation
  metals      gold, copper
Every other live instrument is ungrouped and contributes only to
between-sibling pairs, exactly as equities and credit did under S1.
em_dollar is deliberately not a currency sibling: it is not a child of
the composition tree, and adding it would be inventing a family rather
than extending one.

S2b, the frequency split, run on the same standardized panel:
  fast  residuals from a centered 12 month moving average, tested with
        the same windows and the same 1.5 bar.
  slow  the centered moving averages themselves, tested on a single
        full sample GFEVD. Reported without a pass bar: the slow panel
        has too few effective observations for rolling windows, so the
        numbers are published and no verdict is claimed.

One run. S2a's verdict and S2b's numbers are chained whichever way they
fall, and the finding is stated in one sentence on the record page's
tree note.
"""

import numpy as np
import pandas as pd

from instrument.transmission import var_gfevd

SIBLINGS = {
    "energy": ["oil", "gas", "coal", "uranium"],
    "currencies": ["dollar", "euro", "yen", "yuan", "sterling"],
    "rates": ["curve", "real_yield", "breakevens", "inflation"],
    "metals": ["gold", "copper"],
}
BAR = 1.5
WINDOW = 96
STEP = 6
MA_MONTHS = 12


def standardize(P):
    return (P - P.mean()) / P.std(ddof=0)


def remove_pc1(Z):
    """Residuals after projecting out the first principal component."""
    X = Z.to_numpy(float)
    U, S, Vt = np.linalg.svd(X - X.mean(0), full_matrices=False)
    pc1 = np.outer(U[:, 0] * S[0], Vt[0])
    resid = (X - X.mean(0)) - pc1
    share = float(S[0] ** 2 / (S ** 2).sum())
    return pd.DataFrame(resid, index=Z.index, columns=Z.columns), share


def mean_spillover(P, window=WINDOW, step=STEP):
    starts = list(range(0, len(P) - window + 1, step))
    if not starts:
        return None, 0
    n = P.shape[1]
    acc = np.zeros((n, n))
    for s in starts:
        acc += var_gfevd(P.iloc[s:s + window]) * 100.0
    return acc / len(starts), len(starts)


def sibling_ratio(mean_S, names):
    idx = {n: i for i, n in enumerate(names)}
    within_of = {}
    for fam, members in SIBLINGS.items():
        live = [m for m in members if m in idx]
        for a in live:
            for b in live:
                if a != b:
                    within_of[(a, b)] = fam
    win, bet = [], []
    for a in names:
        for b in names:
            if a == b:
                continue
            v = float(mean_S[idx[a], idx[b]])
            (win if (a, b) in within_of else bet).append(v)
    wm = float(np.mean(win)) if win else None
    bm = float(np.mean(bet)) if bet else None
    ratio = (wm / bm) if (wm is not None and bm) else None
    return {"within_mean": round(wm, 2) if wm is not None else None,
            "between_mean": round(bm, 2) if bm is not None else None,
            "ratio": round(ratio, 2) if ratio is not None else None,
            "n_within_pairs": len(win), "n_between_pairs": len(bet)}


def run(primaries):
    """One run of S2a and S2b."""
    P = pd.DataFrame(primaries).dropna()
    names = list(P.columns)
    Z = standardize(P)
    out = {"nodes": names, "n_nodes": len(names),
           "sample": [str(P.index[0]), str(P.index[-1])],
           "months": int(len(P)), "bar": BAR,
           "siblings": {k: [m for m in v if m in names]
                        for k, v in SIBLINGS.items()}}

    resid, pc1_share = remove_pc1(Z)
    mean_S, nw = mean_spillover(resid)
    s2a = sibling_ratio(mean_S, names)
    s2a.update({"id": "S2a", "windows": nw,
                "pc1_variance_share": round(pc1_share, 3),
                "hit": bool(s2a["ratio"] is not None
                            and s2a["ratio"] >= BAR)})
    out["s2a"] = s2a

    raw_S, raw_nw = mean_spillover(Z)
    base = sibling_ratio(raw_S, names)
    base.update({"id": "S2-baseline", "windows": raw_nw, "hit": None})
    out["baseline_no_removal"] = base

    ma = Z.rolling(MA_MONTHS, center=True, min_periods=MA_MONTHS).mean()
    fast = (Z - ma).dropna()
    slow = ma.dropna()
    f_S, f_nw = mean_spillover(fast)
    s2b_fast = sibling_ratio(f_S, names)
    s2b_fast.update({"id": "S2b-fast", "windows": f_nw,
                     "months": int(len(fast)),
                     "hit": bool(s2b_fast["ratio"] is not None
                                 and s2b_fast["ratio"] >= BAR)})
    slow_S = var_gfevd(slow) * 100.0
    s2b_slow = sibling_ratio(slow_S, names)
    s2b_slow.update({"id": "S2b-slow", "windows": 1,
                     "months": int(len(slow)), "hit": None,
                     "verdict": "none claimed: single full sample "
                                "GFEVD, no pass bar registered"})
    out["s2b_fast"] = s2b_fast
    out["s2b_slow"] = s2b_slow
    return out
