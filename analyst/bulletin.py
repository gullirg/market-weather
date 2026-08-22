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


def score_pending(entries, preds, asof):
    """Score any pending auto-scorable claim whose window closed by asof.
    Claims carry node, window (a..b), target, mode (dominant|present)."""
    import pandas as pd
    out = list(entries)
    A = pd.Period(asof, "M")
    for e in [e for e in entries if e.get("status") == "pending"
              and e.get("auto")]:
        b = pd.Period(e["window"].split("..")[1], "M")
        if b > A:
            continue
        a = pd.Period(e["window"].split("..")[0], "M")
        w = preds[e["node"]].loc[a:b].dropna()
        if len(w) == 0:
            status, note = "unscoreable", "window has no data"
        else:
            dom = w.value_counts().index[0]
            hit = (dom == e["target"] if e["mode"] == "dominant"
                   else (w == e["target"]).any())
            status = "hit" if hit else "miss"
            note = f"dominant {dom}, share {float((w == e['target']).mean()):.2f}"
        out = append(out, {"id": e["id"] + "-scored", "claim": e["claim"],
                           "window": e["window"], "status": status,
                           "note": note})
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
