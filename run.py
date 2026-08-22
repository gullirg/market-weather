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


# STREAK-DEF, chained 2026-08 before the first render. A chain entry is
# a streak dot if and only if its group is one of these. The excluded
# group strings are enumerated in the chain entry's note.
STREAK_GROUPS = ("out of sample", "prediction upgrades", "corrections",
                 "bulletin claim scoring", "outlook quarter scoring")
STREAK_N = 40
STREAK_DOT = {"hit": "hit", "oos": "hit",
              "miss": "miss", "fail": "miss",
              "null": "null", "un": "null", "ret": "null",
              "rev": "null", "pending": "pending"}


# state to family code, the same map the v3 strip uses. Carried into
# the outlook payload so the page colours forecast bands from the
# pipeline rather than from a second hand-written table.
FAM_CODE = {"calm": 0, "easing": 1, "real_easing": 1,
            "boom": 2, "rally": 2, "steepening": 2,
            "reflation": 2, "expansion": 2, "em_bid": 2,
            "supply_glut": 3, "precautionary": 3, "inversion": 3,
            "real_tightening": 3, "em_stress": 3, "correction": 3,
            "fear_bid": 3,
            "demand_collapse": 4, "bust": 4, "stress": 4,
            "supply_squeeze": 4, "deflation_scare": 4,
            "contraction": 4, "selloff": 4, "surge": 4}
SYN_FAM = {"risk_on_calm": 0, "post_shock_glut": 3,
           "commodity_shock": 3, "inflation_shock": 4,
           "financial_stress": 4, "demand_collapse": 4}


def _streak(entries):
    """The public streak, derived from the chain at build time under
    STREAK-DEF. Nothing here is hand-kept."""
    sel = [e for e in entries if e.get("group") in STREAK_GROUPS]
    tot = {"hits": 0, "misses": 0, "nulls": 0, "pending": 0}
    key = {"hit": "hits", "miss": "misses", "null": "nulls",
           "pending": "pending"}
    for e in sel:
        d = STREAK_DOT.get(e.get("status"))
        if d:
            tot[key[d]] += 1
    rows = []
    for e in sel[-STREAK_N:]:
        rows.append({"id": e.get("id"), "status": e.get("status"),
                     "dot": STREAK_DOT.get(e.get("status"), "null"),
                     "window": e.get("window"), "group": e.get("group"),
                     "claim": e.get("claim", ""), "note": e.get("note", ""),
                     "hash": e.get("hash")})
    return {"entries": rows, "totals": tot, "matched": len(sel),
            "window_size": STREAK_N}


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
    sc = load_scorecard()
    sc = B.score_pending(sc, diag["preds"], args.asof)
    json.dump(sc, open(os.path.join(STATE, "scorecard.json"), "w"),
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
        q = outlook.quarter_of(args.asof)
        qpath = os.path.join(STATE, f"outlook_{q}.json")
        if os.path.exists(qpath):
            ol = json.load(open(qpath))
            print(f"outlook {q} already issued, reused as issued")
        else:
            ol = outlook.run(diag["preds"], allposts, synj2["series"],
                             months, args.asof,
                             issued=args.issued or f"{args.asof}-05")
        ol["family_map"] = FAM_CODE
        ol["synoptic_family_map"] = SYN_FAM
        site["outlook"] = ol
        json.dump({k: v for k, v in ol.items()
                   if k not in ("family_map", "synoptic_family_map")},
                  open(qpath, "w"), indent=1)
    except Exception as e:
        site["outlook"] = None
        print("outlook layer degraded:", e)
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
    site["streak"] = _streak(load_scorecard())
    site["health"] = [{"feed": r_["feed"], "ok": not r_["FLAG"]}
                      for r_ in report]
    site["issued"] = args.issued or f"{args.asof}-05"
    site["score"] = counts(load_scorecard())
    assert "spill" in site and "net" in site
    json.dump(site, open(os.path.join(STATE, "site_data.json"), "w"),
              sort_keys=True)
    # site build: minimal animated graph as index, full record alongside
    payload = json.dumps(site, sort_keys=True)
    # Page-only injections. Neither touches site_data.json, the decoders
    # or the bulletin: they are strings substituted into the templates
    # at build time so crawlers and the resting view see words rather
    # than script output.
    changes_line = _since_last_bulletin(site)
    og_desc = _og_description(site)
    import html as _html
    for src, dst in [("graph_v3.html", "index.html"),
                     ("template.html", "report.html")]:
        tpl = open(os.path.join(SITE, src)).read()
        page = tpl.replace("__DATA__", payload)
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
