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
FIRST_WIRED_BULLETIN = 2
LAMP_THRESHOLD_PCT = -15.0
LAMP_HORIZON_M = 3


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
            "rule": {"kind": "drawdown", "series": "real_brent",
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

    dr = (hz.get("durations") or {}).get(state, {})
    cont = dr.get("continuation_at_current")
    cside = _side(cont)
    if cont is not None and cside is not None:
        a = base + 1
        out.append({
            "id": f"B{no:03d}-CONT",
            "group": CLAIM_GROUP,
            "status": "pending",
            "auto": True,
            "claim": (f"continuation, bulletin {no:03d}: the stated "
                      f"share of past {word} episodes that ran longer "
                      f"than the current one is {cont}, which is the "
                      f"chance the regime is still {word} next month"),
            "window": f"{a}..{a}",
            "matures": str(a),
            "rule": {"kind": "state", "node": "oil", "target": state,
                     "mode": "present", "p": cont, "side": cside,
                     "source": (f"hazard.durations['{state}']"
                                ".continuation_at_current")},
            "note": ("resolution rule, registered at publish: at "
                     "maturity the pipeline reads the decoded oil state "
                     "for the window month from the monthly decoder. "
                     f"The event is that the state is still {state}. "
                     f"The stated probability is {cont}, so the "
                     f"bulletin's side is that the regime does "
                     f"{'continue' if cside else 'not continue'}; hit "
                     "if the realization falls on that side, miss if it "
                     "falls on the other. A stated probability of "
                     "exactly one half resolves unscoreable and no "
                     "claim is registered.")})
    return out


def _resolve(rule, a, b, preds, series):
    """(status, note) for a matured rule, or None while the realization
    is not yet in the pipeline."""
    import numpy as np
    import pandas as pd
    side = rule.get("side")
    if side is None:
        return ("un", "no side: the stated probability was exactly one half")
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
        return ("un", f"unknown resolution kind {rule['kind']}")
    hit = (occurred == side)
    note = (f"stated probability {rule['p']}, registered side "
            f"{'event occurs' if side else 'event does not occur'}, "
            f"realization {'event occurred' if occurred else 'event did not occur'}; "
            + detail)
    return ("hit" if hit else "miss", note)


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
        if rule:
            res = _resolve(rule, a, b, preds, series or {})
            if res is None:
                continue
            status, note = res
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
        out = append(out, {"id": e["id"] + "-scored",
                           "group": CLAIM_SCORE_GROUP,
                           "claim": e["claim"],
                           "window": e["window"], "status": status,
                           "note": note})
        seen.add(e["id"] + "-scored")
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
