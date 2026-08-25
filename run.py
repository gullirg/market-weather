"""Monthly runner. Commands:
  python run.py refresh --source local|live
  python run.py month --asof 2026-08 [--kill-feed NAME]
  python run.py publish --asof 2026-08
`month` builds everything and waits; `publish` freezes the permalink."""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from feeds.providers import refresh
from feeds import health
from instrument import (nodes, synoptic, hazards, transmission, daily,
                        analogue, outlook)
from analyst import bulletin as B

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATE = os.path.join(ROOT, "state")
BULL = os.path.join(ROOT, "bulletins")
SITE = os.path.join(ROOT, "site")


def load_scorecard():
    p = os.path.join(STATE, "scorecard.json")
    return json.load(open(p)) if os.path.exists(p) else []


def counts(entries):
    c = {"hit": 0, "miss": 0, "fail": 0, "null": 0, "ret": 0, "rev": 0,
         "un": 0, "pending": 0, "oos": 0}
    for e in entries:
        s = e.get("status")
        if s in c:
            c[s] += 1
    c["hit"] += c["oos"]
    return c


def cmd_refresh(args):
    for f, st in refresh(DATA, args.source):
        print(f"{st:12s} {f}")


def _raw_shiller(data_dir, col):
    sh = pd.read_csv(os.path.join(data_dir, "shiller.csv"))
    sh.columns = [c.strip() for c in sh.columns]
    sh["Date"] = pd.to_datetime(sh["Date"])
    s = sh.set_index(sh["Date"].dt.to_period("M"))[col].astype(float)
    return s


# STREAK-DEF-2, chained 2026-08 before the render it governs. The
# surface streak is published analyst calls only. Every other group
# with a scored status is the laboratory record, which renders in full
# on the record page: nothing is deleted, it is relabelled.
# PROPER-SCORE-REG-2 adds the slate dot to the surface. Per-claim
# scorings from bulletin 003 carry their own group and are laboratory.
STREAK_GROUPS = ("out of sample", "corrections",
                 "bulletin claim scoring", "bulletin slate scoring",
                 "outlook quarter scoring")
STREAK_N = 40
SCORED_STATUSES = ("hit", "miss", "fail", "null", "un", "oos",
                   "ret", "rev")
STREAK_DOT = {"hit": "hit", "oos": "hit",
              "miss": "miss", "fail": "miss",
              "null": "null", "un": "null",
              "ret": "amber", "rev": "amber", "pending": "pending"}


from instrument.families import FAM_CODE, SYN_FAM, FAM_WORD


def _streak(entries):
    """The public streak, derived from the chain at build time under
    STREAK-DEF. Nothing here is hand-kept."""
    sel = [e for e in entries if e.get("group") in STREAK_GROUPS]
    tot = {"hits": 0, "misses": 0, "nulls": 0, "amber": 0,
           "pending": 0}
    key = {"hit": "hits", "miss": "misses", "null": "nulls",
           "amber": "amber", "pending": "pending"}
    for e in sel:
        d = STREAK_DOT.get(e.get("status"))
        if d:
            tot[key[d]] += 1
    def _plural(n, one, many):
        return f"{n} {one if n == 1 else many}"
    rows = []
    for e in sel[-STREAK_N:]:
        rows.append({"id": e.get("id"), "status": e.get("status"),
                     "dot": STREAK_DOT.get(e.get("status"), "null"),
                     "window": e.get("window"), "group": e.get("group"),
                     "claim": e.get("claim", ""), "note": e.get("note", ""),
                     "hash": e.get("hash")})
    return {"entries": rows, "totals": tot, "matched": len(sel),
            "window_size": STREAK_N,
            # v5 bindings: the dot row carries the STREAK-DEF dot class
            # rather than the raw chain status, so the registered
            # colours survive; the totals sentence is built here so its
            # numerals come from the same totals build_payload admits.
            "row": [{"status": r["dot"], "id": r["id"]} for r in rows],
            "definition": "STREAK-DEF-2",
            "previous_totals_words": "1 hit, 3 misses, 4 null or "
                                     "corrected under STREAK-DEF",
            "totals_words": (
                _plural(tot["hits"], "hit", "hits") + ", "
                + _plural(tot["misses"], "miss", "misses")
                + (", " + _plural(tot["amber"], "corrected", "corrected")
                   if tot["amber"] else ""))}


def _laboratory(entries):
    """Every scored entry the surface does not carry, most recent
    first. Development and qualification: instrument checks,
    membership, upgrade gates and falsified diagnoses."""
    sel = [e for e in entries
           if e.get("group") not in STREAK_GROUPS
           and e.get("status") in SCORED_STATUSES]
    tot = {"hits": 0, "misses": 0, "nulls": 0, "amber": 0}
    key = {"hit": "hits", "miss": "misses", "null": "nulls",
           "amber": "amber"}
    rows = []
    for e in reversed(sel):
        d = STREAK_DOT.get(e.get("status"), "null")
        rows.append({"id": e.get("id"), "status": e.get("status"),
                     "dot": d, "group": e.get("group"),
                     "window": e.get("window"),
                     "claim": e.get("claim", ""),
                     "note": e.get("note", ""), "hash": e.get("hash")})
    for e in sel:
        d = STREAK_DOT.get(e.get("status"))
        if d in key:
            tot[key[d]] += 1
    return {"entries": rows, "totals": tot, "matched": len(sel)}


OUTLOOK_DISPLAY_FORECASTER = "M"
# WEATHER-DIALS-REG. Display only: every number here is a formula over
# an object the pipeline already computed.
PRESSURE_SET = ("credit", "equities", "dollar", "em_dollar")
HUMIDITY_SET = ("inflation", "breakevens", "money")
# WEATHER-DIALS-REG-2: the scales the existing numbers are drawn on.
# Zone words only; the boundaries live in the registration.
TEMP_ZONES = ["calm", "unsettled", "strained", "storm"]
PRESSURE_ZONES = ["stormy", "changeable", "fair"]
HUMIDITY_ZONES = ["dry", "damp", "saturated"]
WIND_ZONES = ["still", "typical", "gale"]
STORM_MAX = 60
VISIBILITY_MAX = 12


def _fam_now_prev(site):
    """Each live instrument's latest decoded family and its reading one
    month earlier. Instruments report at different lags, so this is a
    cross-section of latest readings, not of one calendar month, which
    is what WEATHER-DIALS-REG pins."""
    strip = ((site.get("v3") or {}).get("fam_strip")) or {}
    out = {}
    for name, row in strip.items():
        last = None
        for k in range(len(row) - 1, -1, -1):
            if isinstance(row[k], int) and row[k] >= 0:
                last = k
                break
        if last is None:
            continue
        prev = row[last - 1] if last > 0 and isinstance(row[last - 1], int) \
            and row[last - 1] >= 0 else None
        out[name] = (row[last], prev)
    return out


def _mean_fam(fp, names=None, which=0):
    vals = [v[which] for n, v in fp.items()
            if (names is None or n in names) and v[which] is not None]
    return (sum(vals) / len(vals)) if vals else None


def _weather(site):
    """The meteorology layer, registered as WEATHER-DIALS-REG."""
    fp = _fam_now_prev(site)
    if not fp:
        return None
    m_now = _mean_fam(fp)
    if m_now is None:
        return None
    temp = int(round(25.0 * m_now))
    dials = []

    def pair(names, f):
        """Now and prior over the same instruments, so the arrow
        compares like with like rather than two different panels."""
        both = {n: v for n, v in fp.items() if v[1] is not None}
        a = _mean_fam(fp, names, 0)
        b = _mean_fam(both, names, 1)
        a_same = _mean_fam(both, names, 0)
        if a_same is None or b is None:
            return (None if a is None else f(a), None)
        return (f(a), f(b), f(a_same))

    pr = pair(PRESSURE_SET, lambda x: 100.0 - 25.0 * x)
    p_now, p_prev = pr[0], pr[1]
    p_cmp = pr[2] if len(pr) > 2 else None
    if p_now is not None:
        d = 0 if p_prev is None else (1 if p_cmp > p_prev
                                      else (-1 if p_cmp < p_prev else 0))
        dials.append({"name": "FINANCIAL PRESSURE", "value": str(int(round(p_now))),
                      "dir": d,
                      "scale": {"v": int(round(p_now)), "max": 100,
                                "zones": PRESSURE_ZONES},
                      "detail": "falling is storm-side; credit, equities "
                                "and the dollar"})
    hr = pair(HUMIDITY_SET, lambda x: 25.0 * x)
    h_now, h_prev = hr[0], hr[1]
    h_cmp = hr[2] if len(hr) > 2 else None
    if h_now is not None:
        d = 0 if h_prev is None else (1 if h_cmp > h_prev
                                      else (-1 if h_cmp < h_prev else 0))
        dials.append({"name": "INFLATION HUMIDITY", "value": str(int(round(h_now))),
                      "dir": d,
                      "scale": {"v": int(round(h_now)), "max": 100,
                                "zones": HUMIDITY_ZONES},
                      "detail": "inflation, breakevens and money"})

    bf = ((site.get("v3") or {}).get("block_frames")) or {}
    frames = bf.get("frames") or []
    if frames:
        tot = [sum(e["pct"] for e in f.get("edges", [])) for f in frames]
        cur = tot[-1]
        pctl = int(round(100.0 * sum(1 for t in tot if t <= cur)
                         / len(tot)))
        edges = frames[-1].get("edges") or []
        gust = max(edges, key=lambda e: e["pct"]) if edges else None
        detail = "percentile of history"
        if gust:
            detail += (f"; gust {gust['src'].replace('_', ' ')} to "
                       f"{gust['dst'].replace('_', ' ')} at "
                       f"{gust['pct']} percent")
        dials.append({"name": "TRANSMISSION WIND", "value": str(pctl), "dir": 0,
                      "scale": {"v": pctl, "max": 100,
                                "zones": WIND_ZONES},
                      "detail": detail})

    ol = site.get("outlook") or {}
    iw = ol.get("weather") or {}
    vis = iw.get("visibility_months")
    vdial = {"name": "FORECAST VISIBILITY",
             "value": (f"~{vis} mo" if vis is not None else "not yet"),
             "dir": 0,
             "detail": ("months before the leading weather system "
                        "falls below an even chance"
                        if vis is not None else
                        "arrives with the first monthly issue")}
    if vis is not None:
        vdial["scale"] = {"v": vis, "max": VISIBILITY_MAX, "flat": True}
    dials.append(vdial)

    hz = site.get("hazard") or {}
    st = (hz.get("current") or {}).get("state")
    tf = ((hz.get("lamp") or {}).get(st) or {}).get("tail_freq")
    if tf is not None:
        base = (hz.get("lamp") or {}).get("unconditional")
        sdial = {"name": "OIL STORM RISK",
                 "value": f"{int(round(tf * 100))}%", "dir": 0,
                 "detail": hz.get("lampline") or ""}
        sc = {"v": int(round(tf * 100)), "max": STORM_MAX, "flat": True}
        if base is not None:
            sc["ticks"] = [{"v": int(round(base * 100)), "l": "base rate"}]
            sc["tickcap"] = ("tick: the unconditional base rate, "
                             f"{int(round(base * 100))} percent")
        sdial["scale"] = sc
        dials.append(sdial)

    out = {"temp": temp, "dials": dials,
           "instruments": len(fp),
           "note": (f"issued {ol.get('issued') or ol.get('issue_month')}"
                    f", revised monthly"
                    if iw else
                    "readings are each instrument's latest, not one "
                    "calendar month")}
    if iw.get("hero"):
        out["next_low"] = iw["hero"]["low"]
        out["next_high"] = iw["hero"]["high"]
    cards = iw.get("cards")
    if cards:
        # WEATHER-DIALS-REG-2: a card whose issue did not freeze its band
        # is not shown at all. The template has a guarded plus or minus
        # six fallback for previews; it must never reach a reader.
        if all(c.get("lo") is not None and c.get("hi") is not None
               for c in cards):
            out["forecast"] = cards
        else:
            out["forecast_withheld"] = ("this issue froze no forecast "
                                        "band, so no band is drawn")
    return out


def _lead_instrument(block, site):
    """The block's lead instrument by the same strongest-non-calm rule
    the tiles use: the non-calm member with the highest confidence, or
    failing that the most confident member."""
    members = ((site.get("v3") or {}).get("members") or {}).get(block) or []
    cur = dict(site.get("current") or {})
    cur.update(((site.get("network") or {}).get("current")) or {})
    best, best_p = None, -1.0
    for m in members:
        c = cur.get(m)
        if not c:
            continue
        p = float(c.get("prob", 0.0))
        score = p if c.get("state") != "calm" else p * 0.55
        if score > best_p:
            best, best_p = m, score
    return best


def _outlook_display(site):
    """The read layer's forecast rows, from the current frozen issue.
    Absent until the first monthly issue exists, which is what the
    page's registered empty state is for."""
    ol = site.get("outlook") or {}
    if ol.get("cadence") != "monthly":
        return None
    inst = ol.get("instruments") or {}
    lm = ol.get("lead_months") or {}
    leads = [str(L) for L in (ol.get("leads") or [])][:3]
    if not inst or not leads:
        return None
    fc = OUTLOOK_DISPLAY_FORECASTER

    def chips(dist_by_h, fam_map):
        out = []
        for L in leads:
            d = (dist_by_h or {}).get(L) or {}
            if not d:
                continue
            st = max(d, key=lambda k: d[k])
            fam = fam_map.get(st, 0)
            out.append({"month": lm.get(L, L),
                        "word": {0: "calm", 1: "easing", 2: "up",
                                 3: "strained", 4: "hot"}.get(fam, "calm"),
                        "fam": fam,
                        "prob": int(round(float(d[st]) * 100))})
        return out

    rows = []
    for b in ("energy", "rates_expectations", "credit", "fx", "equities",
              "metals", "activity", "liquidity"):
        lead_i = _lead_instrument(b, site)
        if not lead_i or lead_i not in inst:
            continue
        c = chips((inst[lead_i] or {}).get(fc), FAM_CODE)
        if c:
            rows.append({"block": b, "lead_instrument": lead_i,
                         "months": c})
    syn = None
    if ((site.get("synoptic") or {}).get("gate") == "open"
            and ol.get("synoptic")):
        syn = chips(ol["synoptic"].get(fc), SYN_FAM) or None
    if not rows and not syn:
        return None
    return {"rows": rows, "synoptic": syn,
            "forecaster": fc, "issue": ol.get("issue"),
            "note": f"issued {ol.get('issued') or ol.get('issue_month')}, "
                    f"revised monthly"}


def _bust_lamp(ol, F, asof):
    """BUST-REG. Compares daily observations to the issue's envelope
    and reports one amber lamp after a registered run of breaches.
    Words only: this mechanism revises no probability and re-issues
    nothing."""
    if not ol:
        return {"state": "none", "reason": "no outlook issue"}
    band_of = {}
    for name, v in (ol.get("instruments") or {}).items():
        env = v.get("envelope")
        if env:
            band_of[name] = env
    if not band_of:
        return {"state": "dark",
                "reason": "this issue carries no envelope",
                "next_revision": _next_revision(asof)}
    out = {"state": "dark", "next_revision": _next_revision(asof),
           "checked": sorted(band_of)}
    for name, env in sorted(band_of.items()):
        daily = {"real_brent": "brent_d"}.get(env["series"])
        if daily is None or daily not in F:
            continue
        px = F[daily].dropna()
        defl = nodes._splice_deflator(F)
        per = pd.PeriodIndex(px.index, freq="M")
        real = px / defl.reindex(per).ffill().to_numpy()
        run_len, breached_from = 0, None
        for d, lvl, p in zip(px.index, real.to_numpy(), per):
            key = str(p)
            if key not in env["months"]:
                continue
            b = env["band"][env["months"].index(key)]
            if lvl < b["lo"] or lvl > b["hi"]:
                run_len += 1
                if breached_from is None:
                    breached_from = str(d.date())
            else:
                run_len, breached_from = 0, None
        if run_len >= outlook.BUST_RUN_BD:
            out.update({"state": "amber", "instrument": name,
                        "words": "outside this outlook's expected range",
                        "since": breached_from})
            break
    return out


def _outlook_issues():
    """Every frozen issue, newest first, with its own leads. A
    superseded issue is never withdrawn: it stays reachable and keeps
    the leads it was issued under."""
    import glob as _g
    out = []
    for pth in _g.glob(os.path.join(BULL, "outlook_*.json")):
        try:
            d = json.load(open(pth))
        except Exception:
            continue
        asof = d.get("asof")
        if not asof:
            continue
        out.append({
            "issue": d.get("issue") or outlook.issue_key(asof),
            "asof": asof,
            "issued": d.get("issued"),
            "cadence": d.get("cadence")
                       or ("monthly" if str(asof) >= outlook.MONTHLY_FROM
                           else "quarterly"),
            "leads": d.get("leads") or list(outlook.LEADS),
            "lead_months": d.get("lead_months")
                           or outlook.lead_months(asof),
            "instruments": len(d.get("instruments") or {}),
            "has_envelope": any("envelope" in v for v in
                                (d.get("instruments") or {}).values()),
            "file": "bulletins/" + os.path.basename(pth)})
    return sorted(out, key=lambda r: r["asof"], reverse=True)


def _next_revision(asof):
    """Monthly adjudication under OUTLOOK-REG-3."""
    return str(pd.Period(str(asof), "M") + 1)


def _pendings(entries):
    """Open versus closed pendings, for display only. A pending is
    closed when the chain carries a closure record for it, either the
    G2-CLOSED pattern or a score_pending resolution. The chain itself is
    append-only and is never edited to make this count move."""
    ids = {e["id"] for e in entries}
    op, cl = [], []
    for e in entries:
        if e.get("status") != "pending":
            continue
        if e["id"] + "-CLOSED" in ids or e["id"] + "-scored" in ids:
            cl.append(e["id"])
        else:
            op.append(e["id"])
    return {"open": op, "closed": cl,
            "n_open": len(op), "n_closed": len(cl)}


def _since_last_bulletin(site):
    """One line, in words and with no numerals, naming the instruments
    whose state moved since the last published bulletin. Page only: it
    is never written into site_data.json or the bulletin."""
    p = os.path.join(STATE, "prev_states.json")
    if not os.path.exists(p):
        return ""
    prev = json.load(open(p))
    cur = {n: c["state"] for n, c in site["current"].items()}
    for n, c in (site.get("network") or {}).get("current", {}).items():
        cur[n] = c["state"]
    moved = []
    for n in sorted(cur):
        if n in prev and prev[n] != cur[n]:
            moved.append(f"{n} moved {B.STATE_WORD.get(prev[n], prev[n])}"
                         f" to {B.STATE_WORD.get(cur[n], cur[n])}")
    return ("Since last bulletin: "
            + (", ".join(moved) if moved else "no state changes"))


def _og_description(site):
    """The live banner sentence, worded without numerals."""
    tail = ("Regime instruments decoded from public data, every "
            "registered check scored in public.")
    syn = site.get("synoptic")
    if syn and syn.get("gate") == "open":
        return f"Weather system: {syn['current']['word']}. {tail}"
    return tail


def cmd_month(args):
    masked = [args.kill_feed] if args.kill_feed else []
    site, diag = nodes.decode_all(DATA, args.asof, masked=tuple(
        {"gold": ("gold_m",), "vix": ("vix_m",)}.get(m, (m,))[0]
        for m in masked))
    # health report on the monthly inputs
    F = nodes.load_feeds(DATA)
    monthly = {"brent": nodes._monthly(F["brent_d"]),
               "wti": nodes._monthly(F["wti_d"]),
               "henry hub": nodes._monthly(F["gas_d"]),
               "gold": F["gold_m"], "vix": F["vix_m"],
               "shiller CPI": _raw_shiller(DATA, "Consumer Price Index"),
               "shiller GS10": _raw_shiller(DATA, "Long Interest Rate"),
               "CPIAUCSL": F["cpi"], "CPILFESL": F["core"],
               "GS10": F["gs10"], "Baa": F["baa"], "dollar": F["usd"],
               "stocks": F["stocks"], "futures C1": F["c1"],
               "futures C4": F["c4"]}
    monitored = health.load_monitored(DATA)
    monthly.update(monitored)
    report, flagged = health.run_all(F, monthly)
    degraded = sorted(set(flagged) - {"shiller CPI", "shiller GS10"})
    if args.kill_feed:
        degraded = sorted(set(degraded) | {args.kill_feed})
        site["current"][args.kill_feed]["stale"] = True
    json.dump(report, open(os.path.join(STATE, "feed_health.json"), "w"),
              indent=1)
    sp = json.load(open(os.path.join(STATE, "spillovers.json")))
    site.update(sp)
    months = pd.PeriodIndex(site["months"], freq="M")
    try:
        from instrument import network as net
        nw = net.decode_network(DATA, args.asof)
    except Exception as e:
        nw = None
        print("network layer degraded:", e)
    if nw is not None:
        try:
            allprim = dict(nw["primary"])
            allprim.update(transmission.legacy_primaries(
                DATA, args.asof))
            blk = transmission.block_estimate(
                allprim, net.BLOCKS, months)
            sp = transmission.sparse_map(allprim, months)
        except Exception as e:
            blk, sp = None, None
            print("block map degraded:", e)
        site["network"] = {
            "current": nw["current"], "strip": nw["strip"],
            "membership": nw["active"], "awaiting": nw["awaiting"],
            "checks": nw["checks"], "blocks": blk, "sparse": sp}
        json.dump(site["network"], open(os.path.join(
            STATE, "network.json"), "w"), default=str)
        for k, p in nw["preds"].items():
            diag["preds"][k] = p
    else:
        site["network"] = None
    try:
        syn = synoptic.run(diag["preds"], months)
        gate = "open" if all(c["hit"] for c in syn["checks"]) \
            else "closed"
        site["synoptic"] = {"strip": syn["strip"],
                            "current": syn["current"],
                            "gate": gate,
                            "experimental": gate == "closed"}
        json.dump(syn, open(os.path.join(STATE, "synoptic.json"), "w"))
    except Exception:
        site["synoptic"] = None
    # scoring runs here, after the network preds are merged and the
    # synoptic series exists, so a matured claim on any instrument or
    # on the weather itself can resolve.
    scoring_preds = dict(diag["preds"])
    try:
        _sj = json.load(open(os.path.join(STATE, "synoptic.json")))
        _ss = pd.Series({pd.Period(k, "M"): v
                         for k, v in _sj["series"].items()})
        scoring_preds["synoptic"] = _ss.sort_index()
    except Exception:
        pass
    sc = load_scorecard()
    sc = B.score_pending(sc, scoring_preds, args.asof,
                         series={"real_brent": nodes.real_brent(F)})
    json.dump(sc, open(os.path.join(STATE, "scorecard.json"), "w"),
              indent=1)
    try:
        hz = hazards.run(diag["preds"]["oil"], nodes.real_brent(F))
        site["hazard"] = {"current": hz["current"],
                          "lamp": hz["lamp"],
                          "durations": hz["durations"]}
        json.dump(hz, open(os.path.join(STATE, "hazards.json"), "w"))
    except Exception:
        site["hazard"] = None
    try:
        dy = daily.run(DATA, args.asof, diag["preds"]["oil"])
        json.dump(dy, open(os.path.join(STATE, "daily_shadow.json"), "w"))
        pa1, pa2 = dy["checks"][:2]
        site["daily_shadow"] = {
            "gate": "open" if pa1["hit"] else "closed",
            "agreement": pa1["value"],
            "median_lead_bd": pa2["value"]["median"],
            "family_agreement": dy["checks"][2]["value"]
            if len(dy["checks"]) > 2 else None,
            "current": dy["current"]}
    except Exception:
        site["daily_shadow"] = None
    try:
        synj = json.load(open(os.path.join(STATE, "synoptic.json")))
        an = analogue.run(diag["preds"], synj["series"], months,
                          nodes.real_brent(F))
        json.dump(an, open(os.path.join(STATE, "analogues.json"), "w"))
        site["analogues"] = an["current_analogues"]
    except Exception:
        site["analogues"] = None
    # OUTLOOK v1, issued under OUTLOOK-REG. Issues, never scores.
    try:
        synj2 = json.load(open(os.path.join(STATE, "synoptic.json")))
        allposts = dict(diag["posts"])
        if nw is not None:
            allposts.update(nw["posts"])
        # OUTLOOK-REG fixes forecaster M at one estimation per quarter.
        # If this quarter's outlook has already been issued, the build
        # reuses it rather than re-estimating inside the quarter: a
        # forecast is scored as issued, not as later revised.
        q = outlook.issue_key(args.asof)
        qpath = os.path.join(STATE, f"outlook_{q}.json")
        fresh = not os.path.exists(qpath)
        if not fresh:
            ol = json.load(open(qpath))
            print(f"outlook {q} already issued, reused as issued")
        else:
            ol = outlook.run(diag["preds"], allposts, synj2["series"],
                             months, args.asof,
                             issued=args.issued or f"{args.asof}-05",
                             observables={
                                 "real_brent": nodes.real_brent(F)})
        # display-only labelling for an issue frozen before
        # OUTLOOK-REG-3. The frozen file is not rewritten and the issue
        # is not revised: only the page's labels are derived here, from
        # the issue's own asof.
        if not ol.get("issue"):
            ol["issue"] = outlook.issue_key(ol["asof"])
            ol["issue_month"] = ol["asof"]
            ol["cadence"] = "quarterly"
            ol["leads"] = list(outlook.LEADS)
            ol["lead_months"] = outlook.lead_months(ol["asof"])
            ol["labels_derived"] = True
        ol["family_map"] = FAM_CODE
        ol["synoptic_family_map"] = SYN_FAM
        site["outlook"] = ol
        if fresh:
            # an issue is written once. A reused issue is never
            # rewritten, so display-only labelling cannot leak back
            # into a frozen artifact.
            json.dump({k: v for k, v in ol.items()
                       if k not in ("family_map",
                                    "synoptic_family_map")},
                      open(qpath, "w"), indent=1)
    except Exception as e:
        site["outlook"] = None
        print("outlook layer degraded:", e)
    site["outlook_issues"] = _outlook_issues()
    frames = transmission.frames(DATA, args.asof)
    json.dump(frames, open(os.path.join(STATE, "spill_frames.json"), "w"))
    site["frames"] = frames
    try:
        FAM = FAM_CODE
        fam = {}
        for n, p in diag["preds"].items():
            fam[n] = [FAM.get(p.get(m), -1)
                      if isinstance(p.get(m), str) else -1
                      for m in months]
        allprim2 = dict(nw["primary"]) if nw else {}
        allprim2.update(transmission.legacy_primaries(DATA, args.asof))
        from instrument import network as net2
        bf = transmission.block_frames(allprim2, net2.BLOCKS)
        pins = [["2001-09", "dot-com"], ["2003-03", "Iraq"],
                ["2008-10", "Lehman"], ["2011-09", "EU crisis"],
                ["2014-11", "shale glut"], ["2018-12", "Q4 stress"],
                ["2020-03", "Covid"], ["2022-03", "invasion"],
                ["2026-03", "strait war"], [args.asof, "LIVE"]]
        joined = {n: "founding" for n in diag["preds"]
                  if n in ("oil", "gas", "dollar", "credit",
                           "inflation", "equities", "gold")}
        for m in (nw["active"] if nw else []):
            if m["member"]:
                joined[m["name"]] = "2026-08"
        hz2 = site.get("hazard")
        if hz2 and hz2.get("current"):
            st2 = hz2["current"]["state"]
            lp2 = hz2["lamp"].get(st2, {})
            if lp2.get("tail_freq") is not None:
                hz2["lampline"] = (
                    "risk lamp: tail move in 3 months "
                    f"{int(round(lp2['tail_freq']*100))} percent vs "
                    f"{int(round(hz2['lamp']['unconditional']*100))} "
                    "percent base")
        from instrument import tree as tr
        heat = {}
        live_roll = {}
        for dom, node in tr.TREE.items():
            hh = []
            for k in range(len(months)):
                fol = {}
                for c in node["children"].values():
                    lf = c.get("leaf")
                    if lf and lf in fam:
                        fol[lf] = fam[lf][k]
                ru = tr.rollup(node, fol)
                hh.append(ru["heat"])
            heat[dom] = hh
            fol_live = {}
            for c in node["children"].values():
                lf = c.get("leaf")
                if lf and lf in fam:
                    fol_live[lf] = fam[lf][-1]
            live_roll[dom] = tr.rollup(node, fol_live)
        site["v3"] = {"fam_strip": fam, "block_frames": bf,
                      "pins": pins, "joined": joined,
                      "members": net2.BLOCKS,
                      "tree": {"structure": tr.TREE, "heat": heat,
                               "live": live_roll}}
    except Exception as e:
        site["v3"] = None
        print("v3 layer degraded:", e)
    hzp = os.path.join(STATE, "horizon1.json")
    if os.path.exists(hzp):
        hz1 = json.load(open(hzp))
        site["horizon"] = {
            "curve": [{"lead": r["lead"], "rpss": r["rpss"],
                       "worst": r.get("rpss_worst_instrument")}
                      for r in hz1["curve"] if r.get("rpss") is not None],
            "edge_ends_at_lead": hz1["edge_ends_at_lead"],
            "estimated_at": hz1["estimated_at"],
            "instruments": hz1["instruments"],
            "issues": hz1["issues"], "refresh": hz1["refresh"]}
    hz2p = os.path.join(STATE, "horizon2.json")
    if os.path.exists(hz2p) and site.get("horizon"):
        hz2 = json.load(open(hz2p))
        by = {r["lead"]: r for r in hz2["curve"]}
        for row in site["horizon"]["curve"]:
            r2 = by.get(row["lead"])
            if r2:
                row["rpss_persistence"] = r2["rpss"]
                row["worst_persistence"] = r2.get("rpss_worst_instrument")
        site["horizon"]["edge_ends_vs_persistence"] = \
            hz2["edge_ends_at_lead"]
        site["horizon"]["persistence_crossings_differ"] = \
            hz2["crossing_materially_different"]
        site["horizon"]["persistence_crossing"] = \
            hz2["per_instrument_crossing"]
    # BACKTEST-1, the replayed record. Record page only and laboratory
    # only: it is a note on the chain, not a scored status, so it moves
    # neither the surface streak totals nor the laboratory record
    # totals. A hindsight replay must not move a number published as an
    # uncontaminated test.
    btp = os.path.join(STATE, "backtest1.json")
    if os.path.exists(btp):
        bt = json.load(open(btp))
        site["backtest"] = {
            "label": bt["label"], "caveat": bt["caveat"],
            "window": bt["window"], "estimated_at": bt["estimated_at"],
            "dur1_cut": bt["dur1_cut"],
            "aggregate": bt["aggregate"], "pre_2016": bt["pre_2016"],
            "post_2016": bt["post_2016"], "by_kind": bt["by_kind"],
            "gate_open_origins": bt["gate_open_origins"],
            "row": [{"month": r["month"], "status": r["status"],
                     "claims": r["claims"]} for r in bt["row"]]}
    calp = os.path.join(STATE, "cal_result.json")
    if os.path.exists(calp):
        c = json.load(open(calp))
        site["calibration"] = {
            "n": c["n_total"], "n_valid": c["n_valid"],
            "mean_p": c["raw_mean_p"], "agreement": c["raw_agreement"],
            "brier_raw": c["brier_raw"],
            "brier_calibrated": c["brier_calibrated"],
            "improvement": c["relative_improvement"],
            "threshold": c["threshold"], "adopted": c["adopted"],
            "curve": [b for b in c["reliability"] if b["n"]]}
    s2p = os.path.join(STATE, "s2_result.json")
    if os.path.exists(s2p):
        s2 = json.load(open(s2p))
        site["s2"] = {"baseline": s2["baseline_no_removal"]["ratio"],
                      "pc1_removed": s2["s2a"]["ratio"],
                      "fast": s2["s2b_fast"]["ratio"],
                      "slow": s2["s2b_slow"]["ratio"],
                      "bar": s2["bar"], "nodes": s2["n_nodes"],
                      "windows": s2["s2a"]["windows"]}
    # the read layer reads v3 and the outlook, so it is assembled here,
    # after both exist.
    site["bust"] = _bust_lamp(site.get("outlook"), F, args.asof)
    site["bust"]["on"] = (site["bust"].get("state") == "amber")
    site["changed_line"] = _since_last_bulletin(site)
    od = _outlook_display(site)
    if od:
        site["outlook_display"] = od
    wx = _weather(site)
    if wx:
        site["weather"] = wx
    site["streak"] = _streak(load_scorecard())
    site["laboratory"] = _laboratory(load_scorecard())
    site["pendings"] = _pendings(load_scorecard())
    site["health"] = [{"feed": r_["feed"], "ok": not r_["FLAG"]}
                      for r_ in report]
    site["issued"] = args.issued or f"{args.asof}-05"
    site["score"] = counts(load_scorecard())
    assert "spill" in site and "net" in site
    json.dump(site, open(os.path.join(STATE, "site_data.json"), "w"),
              sort_keys=True)
    # site build: minimal animated graph as index, full record alongside
    payload = json.dumps(site, sort_keys=True)
    # BACKTEST-1 publishes on the record page only, so the index does
    # not carry it: sixteen kilobytes of laboratory replay on the front
    # page that nothing there renders.
    index_payload = json.dumps({k: v for k, v in site.items()
                                if k != "backtest"}, sort_keys=True)
    # Page-only injections. Neither touches site_data.json, the decoders
    # or the bulletin: they are strings substituted into the templates
    # at build time so crawlers and the resting view see words rather
    # than script output.
    changes_line = _since_last_bulletin(site)
    og_desc = _og_description(site)
    import html as _html
    for src, dst in [("graph_v8.html", "index.html"),
                     ("template.html", "report.html")]:
        tpl = open(os.path.join(SITE, src)).read()
        page = tpl.replace("__DATA__", index_payload
                            if dst == "index.html" else payload)
        page = page.replace("__CHANGES__", json.dumps(changes_line))
        page = page.replace("__OGDESC__", _html.escape(og_desc,
                                                       quote=True))
        for tok in ("__DATA__", "__CHANGES__", "__OGDESC__"):
            assert tok not in page, tok
        open(os.path.join(ROOT, dst), "w").write(page)
    # bulletin
    import re as _re
    published = sorted(f[:-5] for f in os.listdir(BULL)
                       if _re.fullmatch(r"\d{4}-\d{2}\.html", f))
    no = (f"{published.index(args.asof) + 1:03d}"
          if args.asof in published else f"{len(published) + 1:03d}")
    issued = args.issued or f"{args.asof}-05"
    chain = {"entries": len(sc),
             "head": sc[-1]["hash"] if sc else "genesis"}
    draft, bad = B.generate(site, counts(sc), no, issued, degraded,
                            chain=chain)
    open(os.path.join(STATE, f"draft_{args.asof}.md"), "w").write(draft)
    # monthly diff
    prevp = os.path.join(STATE, "last_states.json")
    prev = json.load(open(prevp)) if os.path.exists(prevp) else {}
    cur = {n: c["state"] for n, c in site["current"].items()}
    changes = [f"{n}: {prev.get(n, 'none')} -> {s}"
               for n, s in cur.items() if prev.get(n) != s]
    open(os.path.join(STATE, "monthly_diff.md"), "w").write(
        "\n".join(changes) or "no state changes")
    print(f"month {args.asof} built: bulletin {no} draft, lint clean "
          f"({len(bad)} violations), degraded={degraded or 'none'}")
    print("changes:", "; ".join(changes) or "none")
    print("awaiting `publish`")


def cmd_publish(args):
    draft = os.path.join(STATE, f"draft_{args.asof}.md")
    if not os.path.exists(draft):
        sys.exit("no draft for that month; run `month` first")
    import re as _re
    published = sorted(f[:-5] for f in os.listdir(BULL)
                       if _re.fullmatch(r"\d{4}-\d{2}\.html", f))
    no = (f"{published.index(args.asof) + 1:03d}"
          if args.asof in published else f"{len(published) + 1:03d}")
    shutil.copy(os.path.join(ROOT, "index.html"),
                os.path.join(BULL, f"{args.asof}.html"))
    if os.path.exists(os.path.join(ROOT, "report.html")):
        shutil.copy(os.path.join(ROOT, "report.html"),
                    os.path.join(BULL, f"{args.asof}_record.html"))
    shutil.copy(draft, os.path.join(BULL, f"{args.asof}.md"))
    import glob as _glob
    for src in sorted(_glob.glob(os.path.join(STATE, "outlook_*.json"))):
        shutil.copy(src, os.path.join(BULL, os.path.basename(src)))
        print(f"froze {os.path.basename(src)}")
    site = json.load(open(os.path.join(STATE, "site_data.json")))
    # From bulletin 002 onward, register this bulletin's scoreable
    # forward claims as pending auto entries carrying their resolution
    # rules. score_pending resolves them once matured.
    claims = B.forward_claims(site, no, args.asof)
    if claims:
        sc = load_scorecard()
        B.verify(sc)
        have = {e["id"] for e in sc}
        seen_fc = set()
        for e in sc:
            r = e.get("rule") or {}
            if r.get("outlook_quarter"):
                seen_fc.add((r.get("claim_kind"), r.get("node"),
                             r["outlook_quarter"]))
        added = []
        for c in claims:
            if c["id"] in have:
                continue
            r = c.get("rule") or {}
            if r.get("outlook_quarter"):
                k = (r.get("claim_kind"), r.get("node"),
                     r["outlook_quarter"])
                if k in seen_fc:
                    continue
                seen_fc.add(k)
            sc = B.append(sc, c)
            added.append(c["id"])
        if added:
            B.verify(sc)
            json.dump(sc, open(os.path.join(STATE, "scorecard.json"), "w"),
                      indent=1)
            print("registered forward claims: " + ", ".join(added))
    states = {n: c["state"] for n, c in site["current"].items()}
    for n, c in (site.get("network") or {}).get("current", {}).items():
        states[n] = c["state"]
    json.dump({n: c["state"] for n, c in site["current"].items()},
              open(os.path.join(STATE, "last_states.json"), "w"))
    # the published month's state map, read by the next month's build
    # to render the page-only "since last bulletin" line
    json.dump(states, open(os.path.join(STATE, "prev_states.json"), "w"))
    print(f"published bulletin {no} for {args.asof}: "
          f"bulletins/{args.asof}.html and .md frozen")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh")
    r.add_argument("--source", default="local")
    m = sub.add_parser("month")
    m.add_argument("--asof", required=True)
    m.add_argument("--kill-feed", default=None)
    m.add_argument("--issued", default=None)
    p = sub.add_parser("publish")
    p.add_argument("--asof", required=True)
    args = ap.parse_args()
    {"refresh": cmd_refresh, "month": cmd_month,
     "publish": cmd_publish}[args.cmd](args)
