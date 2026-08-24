"""OUTLOOK v1, the forecast layer, registered as OUTLOOK-REG before any
estimate existed. Nothing in this module may be changed after a quarter
has been scored against it.

The decoded present is the analysis. The forecast is the outlook.

Registered form, restated here so the code and the chain entry can be
read side by side:

1. Forecaster M, Markov. Per instrument a semi-Markov transition
   structure: empirical duration distributions per state, a
   duration-dependent exit hazard, and a next-state distribution
   conditional on exit. Re-estimated once per quarter on full history.
   Horizons 1 to 12 months, by forward simulation of 2000 sampled
   paths from the current posterior. Synoptic occupancy additionally
   as the discounted successor representation over the joint decoded
   synoptic series, discount 0.9.
2. Forecaster A, analogue ensemble. The top K of 20 analogues of the
   current joint state under the registered analogue weights, with the
   existing 12 month exclusion window, then the empirical distribution
   of states at each horizon.
3. Baselines. Persistence, the current state with probability one at
   every horizon. Climatology, the unconditional state frequencies
   over full history.
4. Scoring happens at quarter end against decoded realizations, never
   here. This module issues forecasts and freezes them.

Implementation choices the registration did not fix, recorded here
because they are load bearing:

a. The exit hazard is right-censoring aware. The final run of a series
   is still in progress, so it contributes to the survivor denominator
   at each duration it reached but never to the exit numerator.
b. Durations beyond the longest observed run for a state reuse that
   state's overall exit rate, so a simulated path can always leave.
c. A path that starts in a state other than the analysis state starts
   with an elapsed duration of one month, since the posterior gives no
   duration for a state the analysis did not select.
d. The random seed is derived from the asof month, so a rebuild of the
   same month reproduces the same forecast exactly.
"""

import hashlib
import json

import numpy as np
import pandas as pd

from instrument import analogue
from instrument.families import FAM_CODE, SYN_FAM, FAM_WORD, HOT

HORIZONS = list(range(1, 13))
K_ANALOGUE = 20
EXCLUDE_M = 12
N_PATHS = 2000
SR_DISCOUNT = 0.9
# forecaster C, added by OUTLOOK-REG-2. Shrinkage weight and the first
# quarter C may issue in; C cannot join the frozen 2026Q3 issue.
C_SHRINK_K = 24.0
C_FIRST_QUARTER = "2026Q4"
# OUTLOOK-REG-3: issuance moves from quarterly to monthly from this
# month onward. Earlier issues keep their quarterly key and their
# original scoring schedule.
MONTHLY_FROM = "2026-10"
# BLEND-REG: forecaster E, the equal weight average of whichever
# forecasters issue in a month. Weights are never fitted.
E_FIRST_MONTH = "2026-10"
# WEATHER-DIALS-REG: an issue stores its own derived weather at freeze
# time, so the display reads frozen numbers and never recomputes a
# forecast.
WEATHER_FROM = "2026-10"
WEATHER_CARDS = 3
HERO_LO, HERO_HI = 10, 90
VISIBILITY_P = 0.50
LEADS = [3, 6, 12]
# BUST-REG: the envelope and the only registered observable mapping.
ENVELOPE_LO, ENVELOPE_HI = 10, 90
BUST_RUN_BD = 5
OBSERVABLE = {"oil": "real_brent"}


def seed_for(asof):
    """Deterministic seed from the asof month, so builds are idempotent."""
    h = hashlib.sha256(f"outlook-v1:{asof}".encode()).hexdigest()
    return int(h[:8], 16)


def quarter_of(asof):
    p = pd.Period(asof, "M")
    return f"{p.year}Q{(p.month - 1) // 3 + 1}"


def issue_key(asof):
    """The key an issue is filed under. Monthly from MONTHLY_FROM,
    quarterly before it, so the frozen 2026Q3 issue keeps its name."""
    return str(asof) if str(asof) >= MONTHLY_FROM else quarter_of(asof)


def lead_months(asof, horizons=None):
    """Calendar month each lead lands on. Probabilities are labelled by
    the month they refer to, never by a relative horizon."""
    base = pd.Period(str(asof), "M")
    return {str(h): str(base + h) for h in (horizons or HORIZONS)}


def _runs(seq):
    """[(state, length), ...] over a list of state labels."""
    out = []
    for s in seq:
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1])
    return [(s, n) for s, n in out]


def semi_markov(seq):
    """Duration-dependent exit hazards and the exit transition matrix."""
    runs = _runs(seq)
    states = sorted({s for s, _ in runs})
    idx = {s: i for i, s in enumerate(states)}
    k = len(states)
    if not runs:
        return None
    dmax = max(n for _, n in runs)
    exits = np.zeros((k, dmax + 1))
    surv = np.zeros((k, dmax + 1))
    for j, (s, n) in enumerate(runs):
        censored = (j == len(runs) - 1)
        i = idx[s]
        for d in range(1, n + 1):
            surv[i, d] += 1
        if not censored:
            exits[i, n] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        haz = np.where(surv > 0, exits / np.maximum(surv, 1e-12), 0.0)
    # fallback rate per state: completed exits over total months lived
    lived = np.zeros(k)
    done = np.zeros(k)
    for j, (s, n) in enumerate(runs):
        lived[idx[s]] += n
        if j < len(runs) - 1:
            done[idx[s]] += 1
    fallback = np.where(lived > 0, done / np.maximum(lived, 1e-12), 1.0)
    fallback = np.clip(fallback, 1e-4, 1.0)
    nxt = np.zeros((k, k))
    for a, b in zip(runs[:-1], runs[1:]):
        nxt[idx[a[0]], idx[b[0]]] += 1
    rows = nxt.sum(1, keepdims=True)
    nxt = np.where(rows > 0, nxt / np.maximum(rows, 1e-12), 1.0 / k)
    return {"states": states, "idx": idx, "haz": haz, "dmax": dmax,
            "fallback": fallback, "next": nxt, "runs": runs}


def _start_duration(seq, state):
    """Elapsed months of the run in progress, if it is in `state`."""
    if not seq or seq[-1] != state:
        return 1
    d = 0
    for s in reversed(seq):
        if s != state:
            break
        d += 1
    return d


def simulate(sm, seq, post_now, rng, n_paths=N_PATHS,
             horizons=HORIZONS):
    """Forward simulation from the current posterior. Returns a dict
    horizon -> {state: probability}."""
    states = sm["states"]
    k = len(states)
    p0 = np.array([float(post_now.get(s, 0.0)) for s in states])
    if p0.sum() <= 0:
        p0 = np.zeros(k)
        p0[sm["idx"].get(seq[-1], 0)] = 1.0
    p0 = p0 / p0.sum()
    cur = rng.choice(k, size=n_paths, p=p0)
    analysis = seq[-1] if seq else None
    dur0 = _start_duration(seq, analysis)
    dur = np.where(cur == sm["idx"].get(analysis, -1), dur0, 1)
    cnxt = np.cumsum(sm["next"], axis=1)
    hmax = max(horizons)
    out = {}
    trail = np.zeros((n_paths, hmax), dtype=int)
    for h in range(1, hmax + 1):
        dcap = np.minimum(dur, sm["dmax"])
        hz = sm["haz"][cur, dcap]
        hz = np.where(hz > 0, hz, sm["fallback"][cur])
        leaving = rng.random(n_paths) < hz
        if leaving.any():
            u = rng.random(int(leaving.sum()))
            rowc = cnxt[cur[leaving]]
            picked = (u[:, None] < rowc).argmax(1)
            cur = cur.copy()
            cur[leaving] = picked
            dur = dur + 1
            dur[leaving] = 1
        else:
            dur = dur + 1
        trail[:, h - 1] = cur
        if h in horizons:
            cnt = np.bincount(cur, minlength=k).astype(float)
            out[h] = {states[i]: round(float(cnt[i] / n_paths), 4)
                      for i in range(k) if cnt[i] > 0}
    return out, trail


# ---------------------------------------------------------- BUST-REG
def state_return_pools(seq, obs, index):
    """Per decoded state, the pool of monthly log returns of the
    observable in months decoded to that state. Registered mapping."""
    o = pd.Series(obs).reindex(pd.Index(index))
    lr = np.log(o.astype(float)).diff()
    pools = {}
    for st, r in zip(seq, lr.to_numpy()):
        if isinstance(st, str) and np.isfinite(r):
            pools.setdefault(st, []).append(float(r))
    return {k: np.asarray(v) for k, v in pools.items() if len(v)}


def envelope(trail, states, pools, last_level, rng,
             lo=ENVELOPE_LO, hi=ENVELOPE_HI):
    """The 10th to 90th percentile band of the sampled paths mapped
    onto the observable, month by month."""
    if not pools or last_level is None or not np.isfinite(last_level):
        return None
    n_paths, hmax = trail.shape
    allr = np.concatenate([v for v in pools.values()])
    cum = np.zeros(n_paths)
    band = []
    for h in range(hmax):
        draw = np.zeros(n_paths)
        for i, st in enumerate(states):
            m = trail[:, h] == i
            if not m.any():
                continue
            pool = pools.get(st)
            if pool is None or len(pool) == 0:
                pool = allr
            draw[m] = rng.choice(pool, size=int(m.sum()), replace=True)
        cum = cum + draw
        lvl = float(last_level) * np.exp(cum)
        band.append({"lo": round(float(np.percentile(lvl, lo)), 2),
                     "hi": round(float(np.percentile(lvl, hi)), 2)})
    return band


# ------------------------------------------------- forecaster C
def _runs_with_ctx(seq, ctx):
    """[(state, length, context at the run's first month), ...]"""
    out = []
    for i, s in enumerate(seq):
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1, ctx[i] if i < len(ctx) else None])
    return [(a, b, c) for a, b, c in out]


def conditioned_hazards(seq_by_node, ctx_by_node, d_max):
    """Exit counts and survivor counts keyed by (node, state, context,
    duration), plus the pooled-over-instruments table keyed by
    (context, duration). Registered in OUTLOOK-REG-2."""
    own_ex, own_sv = {}, {}
    pool_ex = {}
    pool_sv = {}
    nxt_ex = {}
    for node, seq in seq_by_node.items():
        ctx = ctx_by_node.get(node) or [None] * len(seq)
        runs = _runs_with_ctx(seq, ctx)
        for j, (st, ln, cx) in enumerate(runs):
            censored = (j == len(runs) - 1)
            for d in range(1, min(ln, d_max) + 1):
                own_sv[(node, st, cx, d)] = own_sv.get(
                    (node, st, cx, d), 0.0) + 1.0
                pool_sv[(cx, d)] = pool_sv.get((cx, d), 0.0) + 1.0
            if not censored and ln <= d_max:
                own_ex[(node, st, cx, ln)] = own_ex.get(
                    (node, st, cx, ln), 0.0) + 1.0
                pool_ex[(cx, ln)] = pool_ex.get((cx, ln), 0.0) + 1.0
                nxt = runs[j + 1][0]
                key = (node, st, cx)
                nxt_ex.setdefault(key, {})
                nxt_ex[key][nxt] = nxt_ex[key].get(nxt, 0.0) + 1.0
    return {"own_ex": own_ex, "own_sv": own_sv, "pool_ex": pool_ex,
            "pool_sv": pool_sv, "nxt_ex": nxt_ex}


def _shrunk_hazard(tab, node, state, cx, d, fallback):
    n = tab["own_sv"].get((node, state, cx, d), 0.0)
    e = tab["own_ex"].get((node, state, cx, d), 0.0)
    ps = tab["pool_sv"].get((cx, d), 0.0)
    pe = tab["pool_ex"].get((cx, d), 0.0)
    h_pool = (pe / ps) if ps > 0 else fallback
    h_own = (e / n) if n > 0 else h_pool
    h = (n * h_own + C_SHRINK_K * h_pool) / (n + C_SHRINK_K)
    return float(min(max(h, 1e-4), 1.0))


def _shrunk_next(tab, node, state, cx, states, m_row):
    """Own conditioned next-state counts shrunk toward forecaster M's
    unconditional row for the same instrument and state."""
    own = tab["nxt_ex"].get((node, state, cx), {})
    n = float(sum(own.values()))
    out = []
    for j, s2 in enumerate(states):
        o = (own.get(s2, 0.0) / n) if n > 0 else float(m_row[j])
        out.append((n * o + C_SHRINK_K * float(m_row[j]))
                   / (n + C_SHRINK_K))
    tot = sum(out)
    return np.array([v / tot for v in out]) if tot > 0 else m_row


def simulate_c(sm, seq, post_now, tab, node, syn_paths, rng,
               n_paths=N_PATHS, horizons=HORIZONS):
    """Forward simulation identical to forecaster M except that the
    exit hazard and the next-state row are conditioned on the synoptic
    state of the shared simulated weather path."""
    states = sm["states"]
    k = len(states)
    p0 = np.array([float(post_now.get(s, 0.0)) for s in states])
    if p0.sum() <= 0:
        p0 = np.zeros(k)
        p0[sm["idx"].get(seq[-1], 0)] = 1.0
    p0 = p0 / p0.sum()
    cur = rng.choice(k, size=n_paths, p=p0)
    analysis = seq[-1] if seq else None
    dur = np.where(cur == sm["idx"].get(analysis, -1),
                   _start_duration(seq, analysis), 1)
    out = {}
    hmax = max(horizons)
    for h in range(1, hmax + 1):
        cx_h = syn_paths[:, h - 1]
        u = rng.random(n_paths)
        leave = np.zeros(n_paths, bool)
        for i in range(n_paths):
            st = states[cur[i]]
            d = int(min(dur[i], sm["dmax"]))
            hz = _shrunk_hazard(tab, node, st, cx_h[i], d,
                                float(sm["fallback"][cur[i]]))
            leave[i] = u[i] < hz
        if leave.any():
            newc = cur.copy()
            for i in np.where(leave)[0]:
                st = states[cur[i]]
                row = _shrunk_next(tab, node, st, cx_h[i], states,
                                   sm["next"][cur[i]])
                newc[i] = rng.choice(k, p=row)
            cur = newc
            dur = dur + 1
            dur[leave] = 1
        else:
            dur = dur + 1
        if h in horizons:
            cnt = np.bincount(cur, minlength=k).astype(float)
            out[h] = {states[i]: round(float(cnt[i] / n_paths), 4)
                      for i in range(k) if cnt[i] > 0}
    return out


def simulate_synoptic_paths(sm, sseq, rng, n_paths=N_PATHS,
                            hmax=max(HORIZONS)):
    """One shared set of simulated weather paths, from forecaster M's
    semi-Markov structure for the synoptic series."""
    states = sm["states"]
    k = len(states)
    cur = np.full(n_paths, sm["idx"].get(sseq[-1], 0))
    dur = np.full(n_paths, _start_duration(sseq, sseq[-1]))
    cnxt = np.cumsum(sm["next"], axis=1)
    paths = np.empty((n_paths, hmax), dtype=object)
    for h in range(1, hmax + 1):
        dcap = np.minimum(dur, sm["dmax"])
        hz = sm["haz"][cur, dcap]
        hz = np.where(hz > 0, hz, sm["fallback"][cur])
        leaving = rng.random(n_paths) < hz
        if leaving.any():
            u = rng.random(int(leaving.sum()))
            picked = (u[:, None] < cnxt[cur[leaving]]).argmax(1)
            cur = cur.copy()
            cur[leaving] = picked
            dur = dur + 1
            dur[leaving] = 1
        else:
            dur = dur + 1
        paths[:, h - 1] = [states[i] for i in cur]
    return paths


def issue_weather(trails, state_lists, syn_dists, syn_trail,
                  syn_states, base, horizons=None):
    """The derived quantities WEATHER-DIALS-REG lets an issue freeze:
    visibility, the hero range and the forecast cards, all from this
    issue's own sampled paths.

    The ensemble pairs path i across instruments. Forecaster M draws
    each instrument independently, so that pairing samples the product
    of the marginals, not an estimated joint; the registration says so
    and the page says so."""
    horizons = horizons or HORIZONS
    b = pd.Period(str(base), "M")
    vis = None
    for h in horizons:
        d = (syn_dists or {}).get(str(h)) or {}
        if not d:
            break
        if max(d.values()) < VISIBILITY_P:
            vis = h - 1
            break
    if vis is None and syn_dists:
        vis = max(horizons)
    names = [n for n in trails if n in state_lists]
    if not names:
        return None
    hmax = min(trails[names[0]].shape[1], max(horizons))
    fam = np.stack([
        np.asarray([FAM_CODE.get(s2, 0) for s2 in state_lists[n]],
                   dtype=np.int16)[trails[n][:, :hmax]]
        for n in names])                       # (inst, paths, h)
    temp = 25.0 * fam.mean(axis=0)             # (paths, h)
    hot_any = (fam == HOT).any(axis=0)         # (paths, h)
    hero = {"low": int(round(float(np.percentile(temp[:, 0], HERO_LO)))),
            "high": int(round(float(np.percentile(temp[:, 0], HERO_HI))))}
    cards = []
    for i in range(min(WEATHER_CARDS, hmax)):
        h = i + 1
        d = (syn_dists or {}).get(str(h)) or {}
        if d:
            st = max(d, key=lambda k: d[k])
            f = SYN_FAM.get(st, 0)
            word = str(st).replace("_", " ")
        else:
            f, word = 0, ""
        cards.append({"month": str(b + h), "word": word, "fam": f,
                      "temp": int(round(float(temp[:, i].mean()))),
                      "storm": int(round(float(hot_any[:, i].mean()
                                               * 100)))})
    return {"visibility_months": vis, "hero": hero, "cards": cards,
            "paths": int(temp.shape[0]),
            "ensemble": "paths paired across instruments; forecaster M "
                        "draws each instrument independently, so this "
                        "samples the product of the marginals and "
                        "understates co-movement"}


def blend(dists):
    """BLEND-REG: equal weight average over the union of states. The
    inputs are distributions, so the mean is already normalized; it is
    renormalized anyway against rounding."""
    dists = [d for d in dists if d]
    if not dists:
        return {}
    states = sorted({k for d in dists for k in d})
    out = {k: sum(float(d.get(k, 0.0)) for d in dists) / len(dists)
           for k in states}
    tot = sum(out.values())
    if tot <= 0:
        return {}
    return {k: round(v / tot, 4) for k, v in out.items() if v > 0}


def climatology(seq):
    s = pd.Series(seq)
    v = s.value_counts(normalize=True)
    return {str(i): round(float(x), 4) for i, x in v.items()}


def persistence(seq):
    return {seq[-1]: 1.0} if seq else {}


def analogue_ensemble(tab, months, series, node, k=K_ANALOGUE,
                      exclude=EXCLUDE_M, horizons=HORIZONS):
    """Empirical distribution of what followed the K nearest analogues
    of the current joint state. Uses the registered analogue weights
    and exclusion window."""
    i = len(tab) - 1
    top = analogue.analogues(tab, i, k=k, exclude=exclude)
    out = {}
    for h in horizons:
        tally = {}
        n = 0
        for j, _sim in top:
            t = j + h
            if t >= len(months):
                continue
            st = series.get(months[t])
            if not isinstance(st, str):
                continue
            tally[st] = tally.get(st, 0) + 1
            n += 1
        if n:
            out[h] = {s: round(c / n, 4) for s, c in tally.items()}
        else:
            out[h] = {}
    return out, len(top)


def successor_representation(seq, discount=SR_DISCOUNT):
    """Discounted occupancy from the current state, (I - gP)^-1 row."""
    states = sorted(set(seq))
    idx = {s: i for i, s in enumerate(states)}
    k = len(states)
    P = np.zeros((k, k))
    for a, b in zip(seq[:-1], seq[1:]):
        P[idx[a], idx[b]] += 1
    rows = P.sum(1, keepdims=True)
    P = np.where(rows > 0, P / np.maximum(rows, 1e-12), 1.0 / k)
    M = np.linalg.inv(np.eye(k) - discount * P)
    row = M[idx[seq[-1]]]
    row = row / row.sum()
    return {states[i]: round(float(row[i]), 4) for i in range(k)}


def _series_list(pred):
    s = pred.dropna()
    return [x for x in s.tolist() if isinstance(x, str)], s.index


def run(preds, posts, syn_series, months, asof, issued=None,
        observables=None):
    """Issue the outlook. Scores nothing."""
    rng = np.random.default_rng(seed_for(asof))
    mlist = list(months)
    observables = observables or {}
    _trails, _state_lists = {}, {}
    tab = analogue.state_table(preds, syn_series, months)
    monthly_issue = str(asof) >= MONTHLY_FROM
    out = {"asof": str(asof), "quarter": quarter_of(asof),
           "issue": issue_key(asof), "issue_month": str(asof),
           "cadence": "monthly" if monthly_issue else "quarterly",
           "leads": list(LEADS), "lead_months": lead_months(asof),
           "envelope_band": [ENVELOPE_LO, ENVELOPE_HI],
           "bust_run_bd": BUST_RUN_BD,
           "issued": issued, "horizons": list(HORIZONS),
           "k_analogue": K_ANALOGUE, "exclusion_months": EXCLUDE_M,
           "paths": N_PATHS, "sr_discount": SR_DISCOUNT,
           "seed": seed_for(asof), "instruments": {}, "synoptic": None,
           "registration": "OUTLOOK-REG"}
    for name in sorted(preds):
        seq, _ix = _series_list(preds[name])
        if len(seq) < 24:
            continue
        sm = semi_markov(seq)
        if sm is None:
            continue
        po = posts.get(name)
        post_now = {}
        if po is not None and len(po):
            row = po.iloc[-1]
            post_now = {str(c): float(row[c]) for c in po.columns}
        m, trail = simulate(sm, seq, post_now, rng)
        _trails[name] = trail
        _state_lists[name] = list(sm["states"])
        a, nk = analogue_ensemble(tab, mlist, preds[name], name)
        out["instruments"][name] = {
            "states": sm["states"],
            "analysis": {"state": seq[-1],
                         "elapsed_months": _start_duration(seq, seq[-1])},
            "M": {str(h): m.get(h, {}) for h in HORIZONS},
            "A": {str(h): a.get(h, {}) for h in HORIZONS},
            "climatology": climatology(seq),
            "persistence": persistence(seq),
            "analogues_used": nk}
        # BUST-REG: the envelope, only for registered observables and
        # only from the first monthly issue onward.
        obs_key = OBSERVABLE.get(name)
        obs = observables.get(obs_key) if obs_key else None
        if monthly_issue and obs is not None:
            pr = preds[name].dropna()
            pr = pr[[isinstance(x, str) for x in pr]]
            o = pd.Series(obs).reindex(pr.index).astype(float)
            pools = state_return_pools(list(pr), o, pr.index)
            last = o.dropna()
            band = envelope(trail, sm["states"], pools,
                            float(last.iloc[-1]) if len(last) else None,
                            rng)
            if band:
                out["instruments"][name]["envelope"] = {
                    "series": obs_key, "band": band,
                    "months": [str(pd.Period(str(asof), "M") + i + 1)
                               for i in range(len(band))],
                    "last_observed": round(float(last.iloc[-1]), 2),
                    "percentiles": [ENVELOPE_LO, ENVELOPE_HI]}
    # forecaster C, under OUTLOOK-REG-2, from its registered first
    # quarter onward. It cannot join an earlier frozen issue.
    syn_full = pd.Series({p: syn_series.get(str(p)) for p in months})
    if out["quarter"] >= C_FIRST_QUARTER:
        sfull = [syn_series.get(str(p)) for p in months]
        sfull = [x for x in sfull if isinstance(x, str)]
        sm_syn = semi_markov(sfull) if len(sfull) >= 24 else None
        if sm_syn is not None:
            seq_by, ctx_by = {}, {}
            for name in out["instruments"]:
                pr = preds[name].dropna()
                pr = pr[[isinstance(x, str) for x in pr]]
                cx = [syn_full.get(p) for p in pr.index]
                seq_by[name] = list(pr)
                ctx_by[name] = cx
            dmax = max(len(v) for v in seq_by.values())
            tab = conditioned_hazards(seq_by, ctx_by, dmax)
            syn_paths = simulate_synoptic_paths(sm_syn, sfull, rng)
            for name in out["instruments"]:
                seq = seq_by[name]
                sm = semi_markov(seq)
                po = posts.get(name)
                post_now = {}
                if po is not None and len(po):
                    row = po.iloc[-1]
                    post_now = {str(c): float(row[c])
                                for c in po.columns}
                c = simulate_c(sm, seq, post_now, tab, name,
                               syn_paths, rng)
                out["instruments"][name]["C"] = {
                    str(h): c.get(h, {}) for h in HORIZONS}
            out["forecaster_c"] = {"first_quarter": C_FIRST_QUARTER,
                                   "shrink_k": C_SHRINK_K,
                                   "registration": "OUTLOOK-REG-2"}
    # forecaster E, under BLEND-REG, from its registered first month.
    if str(asof) >= E_FIRST_MONTH:
        members = None
        for name, v in out["instruments"].items():
            present = [f for f in ("M", "A", "C") if f in v]
            members = members or present
            v["E"] = {str(h): blend([v[f][str(h)] for f in present])
                      for h in HORIZONS}
        out["forecaster_e"] = {"first_month": E_FIRST_MONTH,
                               "members": members or [],
                               "weights": "equal",
                               "registration": "BLEND-REG"}
    sseq = [syn_series.get(str(p)) for p in months]
    sseq = [x for x in sseq if isinstance(x, str)]
    if len(sseq) >= 24:
        sm = semi_markov(sseq)
        m, _syn_trail = simulate(sm, sseq, {sseq[-1]: 1.0}, rng)
        _syn_states = list(sm["states"])
        sser = pd.Series(
            {p: syn_series.get(str(p)) for p in months})
        a, nk = analogue_ensemble(tab, mlist, sser, "synoptic")
        out["synoptic"] = {
            "states": sm["states"],
            "analysis": {"state": sseq[-1],
                         "elapsed_months": _start_duration(sseq, sseq[-1])},
            "M": {str(h): m.get(h, {}) for h in HORIZONS},
            "A": {str(h): a.get(h, {}) for h in HORIZONS},
            "climatology": climatology(sseq),
            "persistence": persistence(sseq),
            "sr_occupancy": successor_representation(sseq),
            "analogues_used": nk}
        if str(asof) >= WEATHER_FROM:
            w = issue_weather(_trails, _state_lists,
                              out["synoptic"].get("M"), _syn_trail,
                              _syn_states, asof)
            if w:
                out["weather"] = w
        if str(asof) >= E_FIRST_MONTH:
            sp = [f for f in ("M", "A", "C") if f in out["synoptic"]]
            out["synoptic"]["E"] = {
                str(h): blend([out["synoptic"][f][str(h)] for f in sp])
                for h in HORIZONS}
    return out
