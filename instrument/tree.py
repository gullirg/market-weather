"""The composition tree (digital twin, hierarchy v1).

Part-of structure, distinct from the statistical blocks: children here
are what a thing is MADE OF, with measured, slowly-moving shares, not
what it co-moves with. Two epistemic types, kept separate on the page:
leaf states are estimated by decoders through registered gates;
internal-node states are aggregations computed by the roll-up algebra
below, and are labelled as such.

Registered shares (cited constants, v1; upgrade path is time-varying
share files on the host):
- energy: world primary energy consumption mix, Energy Institute
  Statistical Review of World Energy 2025 (2024 data, approximate):
  petroleum about 0.32, coal about 0.26, gas about 0.23, renewables
  (hydro plus wind, solar and other non-fossil ex nuclear) about
  0.15, nuclear about 0.04. Renewables carry no honest monthly world
  price, so they enter as a share-only child by design. Uranium
  prices the nuclear fuel cycle and stands for the nuclear child.
- currencies: BIS Triennial Survey 2022 OTC turnover shares (out of
  200 percent), normalized among the non-dollar majors: euro 0.456,
  yen 0.250, sterling 0.191, yuan 0.103. The dollar is the numeraire
  side of nearly every pair: the trade-weighted dollar instrument
  represents it BESIDE the majors, not inside their shares, and every
  majors leaf is priced against the dollar. Stated on the page.

Registered roll-up algebra (v1): with famcode 0 calm, 1 easing,
2 up, 3 strained, 4 hot per child, and shares renormalized over
children that have data at the month:
  heat(parent) = sum share_i * famcode(child_i)   (a number 0 to 4)
  state(parent) = the family with the largest summed share among
  non-calm children if that renormalized summed share is at least
  0.25, else calm.

Discrepancy instruments: where a parent has BOTH a direct decoded
instrument and a composed reading, the gap between them is signal
(a change in the mix), tracked as its own series. No such pair
exists yet in v1; the machinery reports not-applicable until one
does.

Registered structural check S1 (before computation): on the sparse
stability map over the enlarged live panel, the mean pairwise
spillover within composition siblings is at least 1.5 times the mean
between siblings (Simon near-decomposability). Sibling sets from
this tree and the existing areas: energy {oil, gas, coal, uranium},
currencies {dollar, euro}, rates {curve, real_yield, breakevens,
inflation}, metals {gold, copper}. One run, published either way.
"""

TREE = {
    "energy": {
        "children": {
            "petroleum": {"share": 0.32, "leaf": "oil"},
            "coal": {"share": 0.26, "leaf": "coal"},
            "gas": {"share": 0.23, "leaf": "gas"},
            "renewables": {"share": 0.15, "leaf": None,
                           "note": "share-only: no honest monthly "
                                   "world price exists"},
            "nuclear": {"share": 0.04, "leaf": "uranium"},
        },
        "source": "Energy Institute Statistical Review 2025 "
                  "(2024 mix, approximate)"},
    "currencies": {
        "children": {
            "euro": {"share": 0.456, "leaf": "euro"},
            "yen": {"share": 0.250, "leaf": "yen"},
            "sterling": {"share": 0.191, "leaf": "sterling"},
            "yuan": {"share": 0.103, "leaf": "yuan"},
        },
        "numeraire": "dollar",
        "source": "BIS Triennial 2022 turnover, normalized among "
                  "non-dollar majors; all priced against the dollar"},
}

FAMWORD = {0: "calm", 1: "easing", 2: "up", 3: "strained", 4: "hot"}


def rollup(tree_node, fam_of_leaf):
    """fam_of_leaf: dict leaf-name -> famcode (or None if no data).
    Returns heat, state famcode, availability, per-child detail."""
    detail, avail_share = [], 0.0
    fam_share = {}
    for cname, c in tree_node["children"].items():
        leaf = c.get("leaf")
        fam = fam_of_leaf.get(leaf) if leaf else None
        detail.append({"child": cname, "share": c["share"],
                       "leaf": leaf, "fam": fam,
                       "note": c.get("note")})
        if fam is not None and fam >= 0:
            avail_share += c["share"]
            fam_share[fam] = fam_share.get(fam, 0.0) + c["share"]
    if avail_share == 0:
        return {"heat": None, "state": None, "detail": detail,
                "coverage": 0.0}
    heat = sum(f * s for f, s in fam_share.items()) / avail_share
    noncalm = {f: s / avail_share for f, s in fam_share.items()
               if f != 0}
    state = 0
    if noncalm:
        best = max(noncalm, key=noncalm.get)
        if noncalm[best] >= 0.25:
            state = best
    return {"heat": round(heat, 2), "state": state,
            "state_word": FAMWORD[state], "detail": detail,
            "coverage": round(avail_share, 2)}


def discrepancy(direct_fam, composed_state):
    """Signal when a direct parent instrument and the composition
    disagree. Not applicable until a direct parent instrument
    exists."""
    if direct_fam is None or composed_state is None:
        return {"applicable": False}
    return {"applicable": True,
            "gap": int(direct_fam) - int(composed_state)}
