"""Scorecard engine and bulletin generator.

Scorecard: append-only, hash-chained. Every entry carries the sha of the
previous entry; any retro-edit breaks the chain and verify() raises.
Bulletin: fixed skeleton, slot-filled with verified numbers. A prose
writer may decorate around the slots; the numeral lint then rejects any
draft containing a numeral absent from the data payload. On failure the
deterministic template text ships instead. The system cannot publish a
number it did not compute.
"""

import hashlib
import json
import re

STATE_WORD = {"calm": "calm", "boom": "demand boom", "rally": "rally",
              "collapse": "demand collapse", "stress": "stress",
              "easing": "easing", "squeeze": "supply squeeze",
              "surge": "surge", "glut": "glut",
              "precautionary": "hoarding", "fear_bid": "fear bid",
              "real_rate_bid": "real-rate bid", "selloff": "selloff",
              "usd_up": "dollar up", "usd_down": "dollar down",
              "correction": "correction", "no_data": "no data"}


# ------------------------------------------------------------- scorecard
def _entry_hash(entry, prev_hash):
    body = json.dumps({k: v for k, v in entry.items() if k != "hash"},
                      sort_keys=True)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()[:16]


def verify(entries):
    prev = "genesis"
    for e in entries:
        if e["hash"] != _entry_hash(e, prev):
            raise ValueError(f"scorecard chain broken at {e.get('id')}")
        prev = e["hash"]
    return True


def append(entries, new):
    verify(entries)
    prev = entries[-1]["hash"] if entries else "genesis"
    new = dict(new)
    new["hash"] = _entry_hash(new, prev)
    return entries + [new]


# ------------------------------------------------ forward claim wiring
# From bulletin 002 onward every scoreable forward claim the bulletin
# makes is appended at publish as a pending auto entry carrying its own
# resolution rule. score_pending resolves exactly the matured ones.
# Bulletin 001 was written without this wiring and is not backfilled.
CLAIM_GROUP = "bulletin claim, registered at publish"
CLAIM_SCORE_GROUP = "bulletin claim scoring"
# PROPER-SCORE-REG-2: from bulletin 003 a per-claim scoring is
# laboratory and the surface carries one dot for the whole slate.
CLAIM_SCORE_PERCLAIM_GROUP = "bulletin claim scoring, per claim"
SLATE_SCORE_GROUP = "bulletin slate scoring"
FIRST_WIRED_BULLETIN = 2
LAMP_THRESHOLD_PCT = -15.0
LAMP_HORIZON_M = 3
# B-CLAIMS-REG: the slate every bulletin registers from 002 onward.
CONT_HORIZON_M = 3
CONT_BAND = 0.15
# PROPER-SCORE-REG: from this bulletin onward a claim is scored by its
# Brier against the persistence baseline's Brier for the same event.
FIRST_BRIER_BULLETIN = 3


def _scoring_mode(no):
    return "brier" if int(no) >= FIRST_BRIER_BULLETIN else "binary"


def _persistence_p(rule, series):
    """The persistence baseline probability for this event, defined in
    PROPER-SCORE-REG and nowhere else. Returns None if it cannot be
    evaluated yet."""
    import numpy as np
    import pandas as pd
    if rule["kind"] == "state":
        # persistence says the analysis state continues, and the claim's
        # target is that state
        return 1.0
    if rule["kind"] == "drawdown":
        s = (series or {}).get(rule["series"])
        if s is None:
            return None
        base = pd.Period(rule["base"], "M")
        ref = base - LAMP_HORIZON_M
        if ref not in s.index or base not in s.index:
            return None
        w = s.loc[ref + 1:base].dropna()
        if len(w) == 0:
            return None
        worst = float(np.log(w / float(s.loc[ref])).min())
        thr = float(np.log(1 + rule["threshold_pct"] / 100.0))
        return 1.0 if worst <= thr else 0.0
    return None


def _side(p):
    """The side a stated probability commits the bulletin to. Above one
    half the bulletin's side is that the event occurs, below it that it
    does not, and exactly one half commits to nothing."""
    if p is None:
        return None
    if p > 0.5:
        return True
    if p < 0.5:
        return False
    return None


def forward_claims(site, bulletin_no, asof):
    """The scoreable forward claims of one bulletin, as pending auto
    entries. Empty before the first wired bulletin."""
    import pandas as pd
    try:
        no = int(str(bulletin_no))
    except (TypeError, ValueError):
        return []
    if no < FIRST_WIRED_BULLETIN:
        return []
    hz = (site or {}).get("hazard")
    if not hz or not hz.get("current"):
        return []
    base = pd.Period(site["months"][-1], "M")
    state = hz["current"]["state"]
    word = STATE_WORD.get(state, state)
    out = []

    lp = (hz.get("lamp") or {}).get(state, {})
    tail = lp.get("tail_freq")
    unc = (hz.get("lamp") or {}).get("unconditional")
    side = _side(tail)
    if tail is not None and side is not None:
        a, b = base + 1, base + LAMP_HORIZON_M
        out.append({
            "id": f"B{no:03d}-LAMP",
            "group": CLAIM_GROUP,
            "status": "pending",
            "auto": True,
            "claim": (f"risk lamp, bulletin {no:03d}: from the {word} "
                      f"regime the stated chance of a real Brent "
                      f"drawdown of fifteen percent or worse within "
                      f"three months is {tail}, against {unc} "
                      f"unconditionally"),
            "window": f"{a}..{b}",
            "matures": str(b),
            "rule": {"kind": "drawdown", "series": "real_brent", "scoring": _scoring_mode(no),
                     "base": str(base),
                     "threshold_pct": LAMP_THRESHOLD_PCT,
                     "p": tail, "side": side,
                     "source": f"hazard.lamp['{state}'].tail_freq"},
            "note": ("resolution rule, registered at publish: at "
                     "maturity the pipeline takes real Brent from "
                     "instrument.nodes.real_brent, the same series the "
                     "lamp is estimated on, and computes the minimum "
                     "log return of the window months against the base "
                     "month. The event is a drawdown of fifteen "
                     "percent or worse. The stated probability is "
                     f"{tail}, so the bulletin's side is that the "
                     f"event does {'occur' if side else 'not occur'}; "
                     "hit if the realization falls on that side, miss "
                     "if it falls on the other. A stated probability "
                     "of exactly one half resolves unscoreable and no "
                     "claim is registered. The probability is recorded "
                     "here because one realization cannot score a "
                     "frequency: this binary resolution is deliberately "
                     "coarse and the accumulated set is what a Brier "
                     "score will later be computed over.")})

    # Continuation and synoptic persistence, per B-CLAIMS-REG. Both
    # read the current outlook issue's forecaster M at horizon three,
    # so the stated probability and the resolution window share a base
    # month. This supersedes the earlier one-month hazard continuation
    # claim, which never fired.
    ol = (site or {}).get("outlook") or {}
    inst = ol.get("instruments") or {}
    if inst and ol.get("asof"):
        ob = pd.Period(ol["asof"], "M")
        tgt = ob + CONT_HORIZON_M
        q = ol.get("quarter")
        for name in sorted(inst):
            v = inst[name]
            st = (v.get("analysis") or {}).get("state")
            row = (v.get("M") or {}).get(str(CONT_HORIZON_M)) or {}
            if not st:
                continue
            p = float(row.get(st, 0.0))
            if abs(p - 0.5) < CONT_BAND:
                continue
            sd = _side(p)
            if sd is None:
                continue
            out.append({
                "id": f"B{no:03d}-CONT-{name}",
                "group": CLAIM_GROUP,
                "status": "pending",
                "auto": True,
                "claim": (f"continuation, bulletin {no:03d}: the "
                          f"outlook issued for {ol['asof']} puts the "
                          f"chance that {name} is still {st} three "
                          f"months later at {p}"),
                "window": f"{tgt}..{tgt}",
                "matures": str(tgt),
                "rule": {"kind": "state", "node": name, "target": st, "scoring": _scoring_mode(no),
                         "mode": "present", "p": p, "side": sd,
                         "claim_kind": "continuation",
                         "outlook_quarter": q,
                         "source": (f"outlook.instruments['{name}']"
                                    f".M['{CONT_HORIZON_M}']['{st}']")},
                "note": ("resolution rule, registered at publish: at "
                         "maturity the pipeline reads the decoded "
                         f"state of {name} for the window month from "
                         "the monthly decoder. The event is that the "
                         f"state is still {st}. The stated "
                         f"probability is {p}, so the bulletin's side "
                         f"is that it does "
                         f"{'continue' if sd else 'not continue'}; "
                         "hit if the realization falls on that side, "
                         "miss if it falls on the other. Claims "
                         "within 0.15 of one half are not registered "
                         "at all, and a forecast already registered "
                         "for this outlook quarter is not registered "
                         "again.")})
        syn_o = ol.get("synoptic") or {}
        gate = ((site.get("synoptic") or {}).get("gate"))
        st = (syn_o.get("analysis") or {}).get("state")
        if syn_o and st and gate == "open":
            row = (syn_o.get("M") or {}).get(str(CONT_HORIZON_M)) or {}
            p = float(row.get(st, 0.0))
            sd = _side(p)
            if sd is not None:
                out.append({
                    "id": f"B{no:03d}-SYN",
                    "group": CLAIM_GROUP,
                    "status": "pending",
                    "auto": True,
                    "claim": (f"synoptic persistence, bulletin "
                              f"{no:03d}: the outlook issued for "
                              f"{ol['asof']} puts the chance that the "
                              f"weather system is still {st} three "
                              f"months later at {p}"),
                    "window": f"{tgt}..{tgt}",
                    "matures": str(tgt),
                    "rule": {"kind": "state", "node": "synoptic", "scoring": _scoring_mode(no),
                             "target": st, "mode": "present", "p": p,
                             "side": sd, "claim_kind": "synoptic",
                             "outlook_quarter": q,
                             "source": (f"outlook.synoptic"
                                        f".M['{CONT_HORIZON_M}']"
                                        f"['{st}']")},
                    "note": ("resolution rule, registered at publish: "
                             "at maturity the pipeline reads the "
                             "decoded synoptic series for the window "
                             "month. The event is that the weather "
                             f"system is still {st}. The stated "
                             f"probability is {p}, so the bulletin's "
                             f"side is that it does "
                             f"{'persist' if sd else 'not persist'}. "
                             "Registered only while the banner gate "
                             "is open, and not registered again for "
                             "an outlook quarter the chain already "
                             "holds.")})
    return out


def _resolve(rule, a, b, preds, series):
    """(status, note) for a matured rule, or None while the realization
    is not yet in the pipeline."""
    import numpy as np
    import pandas as pd
    if rule["kind"] == "campaign":
        # judged at maturity against named chain artifacts, never
        # auto-resolved: the entry stays pending until it is scored
        # deliberately.
        return None
    side = rule.get("side")
    if side is None:
        return ("un", "no side: the stated probability was exactly one half",
                {})
    if rule["kind"] == "drawdown":
        s = (series or {}).get(rule["series"])
        if s is None:
            return None
        base = pd.Period(rule["base"], "M")
        if base not in s.index or b not in s.index:
            return None
        w = s.loc[a:b].dropna()
        if len(w) == 0:
            return None
        lp = np.log(w / float(s.loc[base]))
        worst = float(lp.min())
        occurred = bool(worst <= np.log(1 + rule["threshold_pct"] / 100.0))
        measured = round(float(np.expm1(worst) * 100), 1)
        detail = (f"worst real Brent move over the window {measured} "
                  f"percent against a threshold of "
                  f"{rule['threshold_pct']} percent")
    elif rule["kind"] == "state":
        pr = (preds or {}).get(rule["node"])
        if pr is None:
            return None
        w = pr.loc[a:b].dropna()
        if len(w) == 0:
            return None
        occurred = bool((w == rule["target"]).any())
        detail = (f"decoded {rule['node']} state over the window "
                  f"{', '.join(map(str, w.tolist()))} against a target "
                  f"of {rule['target']}")
    else:
        return ("un", f"unknown resolution kind {rule['kind']}", {})
    y = 1.0 if occurred else 0.0
    p = float(rule["p"])
    pb = _persistence_p(rule, series)
    bc = round((p - y) ** 2, 5)
    bb = round((pb - y) ** 2, 5) if pb is not None else None
    mode = rule.get("scoring", "binary")
    if mode == "brier":
        if bb is None:
            return None
        hit = bc < bb
        verdict = (f"scored by Brier under PROPER-SCORE-REG: claim "
                   f"{bc} against persistence baseline {bb} at "
                   f"probability {pb}; "
                   f"{'beats' if hit else 'does not beat'} the baseline")
    else:
        hit = (occurred == side)
        verdict = (f"scored by the registered side rule: side "
                   f"{'event occurs' if side else 'event does not occur'}"
                   f", realization "
                   f"{'event occurred' if occurred else 'event did not occur'}"
                   f". Reported informationally and changing nothing: "
                   f"Brier claim {bc}, persistence baseline "
                   f"{bb if bb is not None else 'not evaluable'}")
    note = (f"stated probability {rule['p']}. {verdict}. " + detail)
    return ("hit" if hit else "miss", note,
            {"brier": bc, "brier_baseline": bb, "mode": mode})


def score_pending(entries, preds, asof, series=None):
    """Score any pending auto-scorable claim whose window closed by asof.
    Rule-carrying claims resolve through their registered rule. Legacy
    claims carry node, window (a..b), target, mode (dominant|present).
    An entry that already has a scored record on the chain is never
    scored twice."""
    import pandas as pd
    out = list(entries)
    A = pd.Period(asof, "M")
    seen = {e["id"] for e in entries}
    for e in [e for e in entries if e.get("status") == "pending"
              and e.get("auto")]:
        if e["id"] + "-scored" in seen:
            continue
        b = pd.Period(e["window"].split("..")[1], "M")
        if b > A:
            continue
        a = pd.Period(e["window"].split("..")[0], "M")
        rule = e.get("rule")
        metrics = {}
        if rule:
            res = _resolve(rule, a, b, preds, series or {})
            if res is None:
                continue
            status, note, metrics = res
        else:
            w = preds[e["node"]].loc[a:b].dropna()
            if len(w) == 0:
                status, note = "unscoreable", "window has no data"
            else:
                dom = w.value_counts().index[0]
                hit = (dom == e["target"] if e["mode"] == "dominant"
                       else (w == e["target"]).any())
                status = "hit" if hit else "miss"
                note = (f"dominant {dom}, share "
                        f"{float((w == e['target']).mean()):.2f}")
        entry = {"id": e["id"] + "-scored",
                 "group": (CLAIM_SCORE_PERCLAIM_GROUP
                           if metrics.get("mode") == "brier"
                           else CLAIM_SCORE_GROUP),
                 "claim": e["claim"],
                 "window": e["window"], "status": status,
                 "note": note}
        for k in ("brier", "brier_baseline"):
            if metrics.get(k) is not None:
                entry[k] = metrics[k]
        out = append(out, entry)
        seen.add(e["id"] + "-scored")
    return _close_slates(out)


def _bulletin_of(cid):
    m = re.match(r"^B(\d{3})-", str(cid))
    return int(m.group(1)) if m else None


def _close_slates(entries):
    """PROPER-SCORE-REG-2. Once every claim of a slate has resolved,
    append the single surface entry for that bulletin: a hit if and
    only if the slate's mean Brier beats the persistence baseline's
    mean Brier over the same events. Ties are a miss."""
    have = {e["id"] for e in entries}
    by = {}
    for e in entries:
        if e.get("group") != CLAIM_GROUP or not e.get("auto"):
            continue
        n = _bulletin_of(e["id"])
        if n is None or (e.get("rule") or {}).get("scoring") != "brier":
            continue
        by.setdefault(n, []).append(e)
    out = entries
    for n in sorted(by):
        sid = f"B{n:03d}-SLATE"
        if sid in have:
            continue
        scored = [next((x for x in out if x["id"] == c["id"] + "-scored"),
                       None) for c in by[n]]
        if any(x is None for x in scored):
            continue
        pairs = [(x.get("brier"), x.get("brier_baseline")) for x in scored]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if not pairs or len(pairs) != len(scored):
            continue
        mc = round(sum(a for a, _ in pairs) / len(pairs), 5)
        mb = round(sum(b for _, b in pairs) / len(pairs), 5)
        wins = sum(1 for a, b in pairs if a < b)
        matures = sorted(c.get("matures", "") for c in by[n])
        out = append(out, {
            "id": sid, "group": SLATE_SCORE_GROUP,
            "status": "hit" if mc < mb else "miss",
            "claim": (f"bulletin {n:03d} slate: mean Brier {mc} against "
                      f"the persistence baseline's {mb} over "
                      f"{len(pairs)} claims"),
            "window": f"{matures[0]}..{matures[-1]}" if matures else "",
            "brier": mc, "brier_baseline": mb, "claims": len(pairs),
            "note": (f"one dot for the whole slate under "
                     f"PROPER-SCORE-REG-2. {wins} of {len(pairs)} "
                     f"individual claims beat their own baseline; the "
                     f"dot follows the slate mean, not the count. "
                     f"Every per-claim score stays on the chain under "
                     f"the group '{CLAIM_SCORE_PERCLAIM_GROUP}' and is "
                     f"expandable on the record page. A tie scores a "
                     f"miss.")})
        have.add(sid)
    return out


# -------------------------------------------------------------- payload
def build_payload(site, scorecard_counts, bulletin_no, issued,
                  chain=None):
    """Every number the bulletin is allowed to contain, as strings at
    display precision.

    `chain`, when given, is the pipeline-computed chain anchor
    {"entries": int, "head": str}. Its entry count and the numeral
    runs inside its head hash are admitted as literals. Both are
    produced by analyst.bulletin itself, so rule 1 holds: still no
    number the pipeline did not compute."""
    nums = set()

    def add(x):
        nums.add(str(x))
    add(bulletin_no)
    for tok in re.findall(r"\d+(?:\.\d+)?", issued):
        add(tok)
    for m in site["months"]:
        y, mm = m.split("-")
        add(y)
        add(mm)
        add(str(int(mm)))
    for n, c in site["current"].items():
        add(int(round(c["prob"] * 100)))
        add(f"{c['prob']:.2f}")
        for tok in re.findall(r"\d+", c["asof"]):
            add(tok)
    for k, v in scorecard_counts.items():
        add(v)
    add(len(site["current"]))
    hz = site.get("hazard")
    if hz and hz.get("current"):
        add(hz["current"]["elapsed"])
        lp = hz["lamp"].get(hz["current"]["state"], {})
        if lp.get("tail_freq") is not None:
            add(int(round(lp["tail_freq"] * 100)))
        if hz["lamp"].get("unconditional") is not None:
            add(int(round(hz["lamp"]["unconditional"] * 100)))
        dr = hz["durations"].get(hz["current"]["state"], {})
        if dr.get("continuation_at_current") is not None:
            add(int(round(dr["continuation_at_current"] * 100)))
    nw = site.get("network")
    if nw:
        for c in (nw.get("current") or {}).values():
            add(f"{c['prob']:.2f}")
        add(len(nw.get("awaiting") or []))
        add(len([m for m in (nw.get("membership") or [])
                 if m.get("member")]))
    od = site.get("outlook_display")
    if od:
        for r in od.get("rows", []):
            for c in r.get("months", []):
                add(c["prob"])
                add(c["fam"])
        for c in (od.get("synoptic") or []):
            add(c["prob"])
            add(c["fam"])
    hz = site.get("horizon")
    if hz:
        for r in hz.get("curve", []):
            for k in ("lead", "rpss", "worst", "rpss_persistence",
                      "worst_persistence"):
                if r.get(k) is not None:
                    add(r[k])
        for k in ("edge_ends_at_lead", "instruments", "issues"):
            if hz.get(k) is not None:
                add(hz[k])
    cb = site.get("calibration")
    if cb:
        for k, v in cb.items():
            if isinstance(v, (int, float)):
                add(v)
        for b in cb.get("curve", []):
            for k in ("lo", "hi", "n", "mean_p", "agreement"):
                if b.get(k) is not None:
                    add(b[k])
    s2 = site.get("s2")
    if s2:
        for v in s2.values():
            add(v)
    st = site.get("streak")
    if st:
        for v in st["totals"].values():
            add(v)
        add(st["matched"])
    if chain:
        add(chain["entries"])
        for tok in re.findall(r"\d+", chain["head"]):
            add(tok)
    return nums


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def lint(text, payload):
    """Return list of numerals in text not present in the payload."""
    bad = []
    for tok in NUM_RE.findall(text):
        if tok in payload:
            continue
        if tok.rstrip("0").rstrip(".") in payload:
            continue
        bad.append(tok)
    return bad


# ------------------------------------------------------------- skeleton
def template_bulletin(site, counts, bulletin_no, issued, degraded,
                      chain=None):
    cur = site["current"]
    live = sum(1 for c in cur.values() if not c.get("stale"))
    lines = []
    lines.append(f"# The Market Weather Report, bulletin {bulletin_no}")
    lines.append(f"Issued {issued}. Data to {site['months'][-1]}. "
                 f"{live} of {len(cur)} instruments live.")
    syn = site.get("synoptic")
    if syn and syn.get("gate") == "open":
        lines.append(f"Weather system: {syn['current']['word']}.")
    nw = site.get("network")
    if nw and nw.get("membership"):
        lines.append("")
        lines.append("## Network")
        joined = [m["name"] for m in nw["membership"] if m["member"]]
        lines.append("Capillary instruments live this month: "
                     + ", ".join(joined) + ".")
        for name in joined:
            c = nw["current"].get(name)
            if c:
                lines.append(f"- {name}: {c['word']} ({c['prob']:.2f})")
        v3t = (site.get("v3") or {}).get("tree") or {}
        er = (v3t.get("live") or {}).get("energy")
        if er and er.get("state_word"):
            lines.append("Energy composition reads "
                         + er["state_word"]
                         + ": the disturbance sits in petroleum; "
                           "gas, coal and nuclear sit calm.")
        if nw.get("awaiting"):
            lines.append("Awaiting data: "
                         + ", ".join(nw["awaiting"]) + ".")
    lines.append("")
    lines.append("## Conditions")
    for n in ["oil", "gas", "dollar", "credit", "inflation",
              "equities", "gold"]:
        c = cur[n]
        pct = int(round(c["prob"] * 100))
        stale = " FEED DEGRADED, masked this month." if c.get("stale") else ""
        lines.append(f"- {n}: {STATE_WORD.get(c['state'], c['state'])} "
                     f"at {pct} percent, as of {c['asof']}.{stale}")
    if degraded:
        lines.append("")
        lines.append("## Degraded instruments")
        for d in degraded:
            lines.append(f"- {d}: feed failed its health check and is "
                         f"masked. The instrument reports its own outage.")
    hz = site.get("hazard")
    if hz and hz.get("current"):
        st = hz["current"]["state"].replace("supply_", "").replace(
            "demand_", "")
        el = hz["current"]["elapsed"]
        lp = hz["lamp"].get(hz["current"]["state"], {})
        tf = lp.get("tail_freq")
        un = hz["lamp"].get("unconditional")
        dr = hz["durations"].get(hz["current"]["state"], {})
        cont = dr.get("continuation_at_current")
        if tf is not None and un is not None:
            lines.append("")
            lines.append("## Risk lamp")
            seg = (f"The oil regime is {st}, {el} months in. From past "
                   f"months in this regime, a drawdown of fifteen "
                   f"percent or worse within three months followed "
                   f"{int(round(tf * 100))} percent of the time, "
                   f"against {int(round(un * 100))} percent "
                   f"unconditionally.")
            if cont is not None:
                seg += (f" {int(round(cont * 100))} percent of past "
                        f"episodes of this regime lasted longer than "
                        f"the current one. History, not a forecast.")
            lines.append(seg)
    lines.append("")
    lines.append("## Scorecard")
    lines.append(f"{counts['hit']} hits, {counts['miss']} misses, "
                 f"{counts['fail']} failed upgrades, "
                 f"{counts['pending']} registered and pending. "
                 f"Failures publish at the same prominence as hits.")
    if chain:
        lines.append("")
        lines.append("## Chain anchor")
        lines.append(f"Scorecard entries: {chain['entries']}. "
                     f"Chain head hash: {chain['head']}. "
                     "Every entry carries the hash of the entry before "
                     "it, so any retro-edit breaks the chain and "
                     "verification fails.")
    lines.append("")
    lines.append("## Limits")
    lines.append("No price forecasts, tested and none claimed. "
                 "No investment advice. History with intervals is "
                 "history, not a recommendation.")
    return "\n".join(lines)


class TemplateWriter:
    def write(self, site, counts, bulletin_no, issued, degraded,
              chain=None):
        return template_bulletin(site, counts, bulletin_no, issued,
                                 degraded, chain)


class ClaudeWriter:
    """Prose around verified slots via the Anthropic API. Requires
    ANTHROPIC_API_KEY on the host; unavailable in offline tests. Falls
    back to TemplateWriter on any failure or lint rejection."""

    SYSTEM = ("You are the analyst layer of a scored economic "
              "instrument. Rewrite the bulletin with connective prose. "
              "Hard rules: use ONLY numerals already present in the "
              "draft; never add a number, a forecast, or advice; keep "
              "every section.")

    def write(self, site, counts, bulletin_no, issued, degraded,
              chain=None):
        import os
        base = template_bulletin(site, counts, bulletin_no, issued,
                                 degraded, chain)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return base
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=1500,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": base}])
            return msg.content[0].text
        except Exception:
            return base


def generate(site, counts, bulletin_no, issued, degraded, writer=None,
             retries=1, chain=None):
    writer = writer or TemplateWriter()
    payload = build_payload(site, counts, bulletin_no, issued, chain)
    draft = writer.write(site, counts, bulletin_no, issued, degraded,
                         chain)
    bad = lint(draft, payload)
    tries = 0
    while bad and tries < retries:
        draft = writer.write(site, counts, bulletin_no, issued, degraded,
                             chain)
        bad = lint(draft, payload)
        tries += 1
    if bad:
        draft = template_bulletin(site, counts, bulletin_no, issued,
                                  degraded, chain)
        bad2 = lint(draft, payload)
        if bad2:
            raise RuntimeError(f"template itself failed lint: {bad2}")
    return draft, lint(draft, payload)
