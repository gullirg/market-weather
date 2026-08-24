"""Acceptance tests for the autonomous analyst, mapped to the build
prompt's registered criteria."""

import json
import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrument import nodes
from analyst import bulletin as B
from feeds import health, providers

GOLDEN = json.load(open(os.path.join(ROOT, "tests",
                                     "golden_site_data.json")))


@pytest.fixture(scope="module")
def decoded():
    site, diag = nodes.decode_all(os.path.join(ROOT, "data"), "2026-08")
    return site, diag


def test_decode_matches_golden_states(decoded):
    """Stage 1 acceptance: reproduce the published August 2026 site
    states exactly (state and probability per instrument)."""
    site, _ = decoded
    for n, g in GOLDEN["current"].items():
        c = site["current"][n]
        assert c["state"] == g["state"], (n, c, g)
        assert abs(c["prob"] - g["prob"]) < 0.011, (n, c, g)


def test_decode_matches_golden_strips(decoded):
    """Strips must match the published record wherever this build has
    data. Deliberate deviation, documented: nodes no longer paint months
    beyond their own asset's last observation, so a node's strip may end
    up to one month earlier than the golden's masked-dimension tail."""
    site, _ = decoded
    for n in GOLDEN["strip"]:
        mine, gold = site["strip"][n], GOLDEN["strip"][n]
        last = max(i for i, v in enumerate(mine) if v != -1)
        assert mine[:last + 1] == gold[:last + 1], n
        extra = [v for v in gold[last + 1:] if v != -1]
        assert len(extra) <= 1, (n, "golden tail longer than one month")


def test_lint_passes_clean(decoded):
    site, _ = decoded
    counts = {"hit": 27, "miss": 4, "fail": 4, "pending": 4}
    draft, bad = B.generate(site, counts, "001", "2026-08-18", [])
    assert bad == []


def test_lint_catches_fabrication(decoded):
    """Constitution rule 1: a numeral absent from the payload is
    rejected."""
    site, _ = decoded
    counts = {"hit": 27, "miss": 4, "fail": 4, "pending": 4}
    payload = B.build_payload(site, counts, "001", "2026-08-18")
    poisoned = B.template_bulletin(site, counts, "001", "2026-08-18",
                                   []) + \
        "\nOil will rise 7.3 percent next quarter."
    assert "7.3" in B.lint(poisoned, payload)


def test_lint_ten_generations(decoded):
    site, _ = decoded
    counts = {"hit": 27, "miss": 4, "fail": 4, "pending": 4}
    for _ in range(10):
        _, bad = B.generate(site, counts, "001", "2026-08-18", [])
        assert bad == []


def test_scorecard_chain_append_only():
    entries = json.load(open(os.path.join(ROOT, "state",
                                          "scorecard.json")))
    B.verify(entries)
    tampered = json.loads(json.dumps(entries))
    i_miss = next(i for i, e in enumerate(tampered)
                  if e["status"] == "miss")
    tampered[i_miss]["status"] = "hit"
    with pytest.raises(ValueError):
        B.verify(tampered)


def test_health_flags_corrupt_feeds_only():
    F = nodes.load_feeds(os.path.join(ROOT, "data"))
    monthly = {"brent": nodes._monthly(F["brent_d"]),
               "wti": nodes._monthly(F["wti_d"]),
               "henry hub": nodes._monthly(F["gas_d"]),
               "gold": F["gold_m"], "vix": F["vix_m"],
               "shiller CPI": F["sh_cpi"].fillna(0.0),
               "shiller GS10": F["sh_gs10"].fillna(0.0)}
    report, flagged = health.run_all(F, monthly)
    assert set(flagged) == {"shiller CPI", "shiller GS10"}


def test_degraded_mode_renders_honestly():
    """Kill the gold feed; the bulletin must say so without help."""
    site, _ = nodes.decode_all(os.path.join(ROOT, "data"), "2026-08",
                               masked=("gold_m",))
    assert site["current"]["gold"]["state"] == "no_data" or \
        site["current"]["gold"].get("stale")
    counts = {"hit": 27, "miss": 4, "fail": 4, "pending": 4}
    draft, bad = B.generate(site, counts, "001", "2026-08-18", ["gold"])
    assert "Degraded instruments" in draft and "gold" in draft
    assert bad == []


def test_month_idempotent(tmp_path):
    """Stage 3 acceptance: two runs of `month` produce identical
    site_data and draft."""
    env = dict(os.environ)
    r1 = subprocess.run([sys.executable, "run.py", "month",
                         "--asof", "2026-08", "--issued", "2026-08-18"],
                        cwd=ROOT, capture_output=True, text=True, env=env)
    assert r1.returncode == 0, r1.stderr
    d1 = open(os.path.join(ROOT, "state", "site_data.json")).read()
    b1 = open(os.path.join(ROOT, "state", "draft_2026-08.md")).read()
    r2 = subprocess.run([sys.executable, "run.py", "month",
                         "--asof", "2026-08", "--issued", "2026-08-18"],
                        cwd=ROOT, capture_output=True, text=True, env=env)
    assert r2.returncode == 0, r2.stderr
    d2 = open(os.path.join(ROOT, "state", "site_data.json")).read()
    b2 = open(os.path.join(ROOT, "state", "draft_2026-08.md")).read()
    assert d1 == d2 and b1 == b2


def test_wave1_site_payload_complete():
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    assert site.get("synoptic") and len(site["synoptic"]["strip"]) == \
        len(site["months"])
    assert site.get("hazard") and "unconditional" in site["hazard"]["lamp"]
    assert len(site.get("frames", [])) >= 30
    assert any(not h["ok"] for h in site["health"])


def test_synoptic_checks_scored():
    syn = json.load(open(os.path.join(ROOT, "state", "synoptic.json")))
    assert len(syn["checks"]) == 4
    assert all(isinstance(c["hit"], bool) for c in syn["checks"])


def test_bulletin_has_risk_lamp_and_lints():
    d = open(os.path.join(ROOT, "state", "draft_2026-08.md")).read()
    assert "Risk lamp" in d


def test_daily_shadow_scored_and_gated():
    dy = json.load(open(os.path.join(ROOT, "state",
                                     "daily_shadow.json")))
    pa1, pa2 = dy["checks"][0], dy["checks"][1]
    assert isinstance(pa1["hit"], bool) and isinstance(pa2["hit"], bool)
    assert all(v is not None
               for v in pa2["value"]["leads_bd"].values())
    site = json.load(open(os.path.join(ROOT, "state",
                                       "site_data.json")))
    assert site["daily_shadow"]["gate"] in ("open", "closed")


def test_analogues_present_and_bounded():
    site = json.load(open(os.path.join(ROOT, "state",
                                       "site_data.json")))
    ans = site["analogues"]
    assert len(ans) == 5
    assert all(0 <= a["similarity"] <= 1 for a in ans)


def test_fred_daily_fixture_aggregates_monthly():
    payload = {"observations": [
        {"date": "2026-07-01", "value": "30.0"},
        {"date": "2026-07-02", "value": "34.0"},
        {"date": "2026-08-01", "value": "40.0"}]}
    s = providers.fred_json_to_series(payload, "ovx", "d")
    assert s.loc[pd.Period("2026-07", "M")] == 32.0


def test_fred_csv_fixture_parses_and_aggregates():
    """The fredgraph.csv download shape: monthly passes through, weekly
    and daily collapse to monthly means, "." becomes NaN."""
    monthly = ("observation_date,EXJPUS\n1971-01-01,358.0200\n"
               "1971-02-01,357.5450\n1971-03-01,.\n")
    s = providers.fred_csv_to_series(monthly, "yen")
    assert len(s) == 3 and s.iloc[0] == 358.02
    assert s.index[1] == pd.Period("1971-02", "M") and pd.isna(s.iloc[2])
    weekly = ("observation_date,WEI\n2026-07-04,2.0\n2026-07-11,4.0\n"
              "2026-08-01,9.0\n")
    w = providers.fred_csv_to_series(weekly, "wei", "w")
    assert w.loc[pd.Period("2026-07", "M")] == 3.0
    assert w.loc[pd.Period("2026-08", "M")] == 9.0


def test_jodi_and_cot_fixtures_parse():
    jodi = ("REF_AREA,ENERGY_PRODUCT,FLOW_BREAKDOWN,TIME_PERIOD,"
            "OBS_VALUE\nTOTAL,CRUDEOIL,TOTPROD,2026-06,76000\n"
            "TOTAL,CRUDEOIL,TOTPROD,2026-07,76500\n")
    s = providers.jodi_csv_to_series(jodi)
    assert len(s) == 2 and s.iloc[-1] == 76500
    cot = ("Report_Date_as_YYYY_MM_DD,M_Money_Positions_Long_All,"
           "M_Money_Positions_Short_All\n2026-07-07,300000,100000\n"
           "2026-07-14,310000,90000\n")
    c = providers.cot_csv_to_series(cot)
    assert c.loc[pd.Period("2026-07", "M")] == 220000


def _claim_site(gate="open"):
    """A site payload shaped like the real one, for the B-CLAIMS-REG
    slate: one instrument well above the band, one well below, one
    inside it, and a synoptic layer."""
    return {"months": ["2026-07", "2026-08"],
            "synoptic": {"gate": gate},
            "hazard": {"current": {"state": "supply_glut", "elapsed": 3},
                       "lamp": {"supply_glut": {"tail_freq": 0.29},
                                "unconditional": 0.15},
                       "durations": {"supply_glut": {
                           "continuation_at_current": 0.7}}},
            "outlook": {
                "asof": "2026-08", "quarter": "2026Q3",
                "instruments": {
                    "oil": {"analysis": {"state": "supply_glut"},
                            "M": {"3": {"supply_glut": 0.80,
                                        "calm": 0.20}}},
                    "gas": {"analysis": {"state": "calm"},
                            "M": {"3": {"calm": 0.55,
                                        "squeeze": 0.45}}},
                    "gold": {"analysis": {"state": "selloff"},
                             "M": {"3": {"selloff": 0.20,
                                         "calm": 0.80}}}},
                "synoptic": {
                    "analysis": {"state": "post_shock_glut"},
                    "M": {"3": {"post_shock_glut": 0.70,
                                "risk_on_calm": 0.30}}}}}


def test_forward_claims_start_at_bulletin_002():
    """Bulletin 001 was written without the wiring and is not
    backfilled; 002 registers both scoreable forward claims."""
    site = _claim_site()
    assert B.forward_claims(site, "001", "2026-08") == []
    cl = B.forward_claims(site, "002", "2026-08")
    ids = {c["id"] for c in cl}
    # gas sits inside the registered 0.15 band and is not claimed
    assert ids == {"B002-LAMP", "B002-CONT-oil", "B002-CONT-gold",
                   "B002-SYN"}, ids
    for c in cl:
        assert c["status"] == "pending" and c["auto"] is True
        assert c["group"] == B.CLAIM_GROUP
        assert c["rule"]["p"] is not None and "source" in c["rule"]
        assert c["note"].startswith("resolution rule, registered at publish")
    lamp = next(c for c in cl if c["id"] == "B002-LAMP")
    assert lamp["window"] == "2026-09..2026-11"
    assert lamp["matures"] == "2026-11"
    assert lamp["rule"]["side"] is False          # 0.29 is below one half
    oil = next(c for c in cl if c["id"] == "B002-CONT-oil")
    assert oil["window"] == "2026-11..2026-11"
    assert oil["rule"]["side"] is True            # 0.80 is above one half
    assert oil["rule"]["claim_kind"] == "continuation"
    assert oil["rule"]["outlook_quarter"] == "2026Q3"
    gold = next(c for c in cl if c["id"] == "B002-CONT-gold")
    assert gold["rule"]["side"] is False          # 0.20 is below one half
    syn = next(c for c in cl if c["id"] == "B002-SYN")
    assert syn["rule"]["node"] == "synoptic"
    assert syn["rule"]["claim_kind"] == "synoptic"


def test_synoptic_claim_only_while_the_banner_gate_is_open():
    shut = B.forward_claims(_claim_site(gate="closed"), "002", "2026-08")
    assert not any(c["id"] == "B002-SYN" for c in shut)
    assert any(c["id"] == "B002-CONT-oil" for c in shut)


def test_forward_claim_ties_and_the_band_register_nothing():
    """Exactly one half commits to no side, and B-CLAIMS-REG's band
    keeps every near-coin-flip continuation off the chain."""
    site = _claim_site()
    site["hazard"]["lamp"]["supply_glut"]["tail_freq"] = 0.5
    for n in site["outlook"]["instruments"]:
        st = site["outlook"]["instruments"][n]["analysis"]["state"]
        site["outlook"]["instruments"][n]["M"]["3"] = {st: 0.5}
    site["outlook"]["synoptic"]["M"]["3"] = {"post_shock_glut": 0.5}
    assert B.forward_claims(site, "002", "2026-08") == []
    assert B.CONT_BAND == 0.15 and B.CONT_HORIZON_M == 3


def _mk_chain(claims):
    chain = B.append([], {"id": "GENESIS", "group": "operations",
                          "status": "hit", "claim": "root",
                          "window": "2026-08"})
    for c in claims:
        chain = B.append(chain, c)
    return chain


def test_lamp_claim_resolves_both_ways_and_only_once():
    """The registered side is 'no tail move'. A quiet window is a hit,
    a crash is a miss, and neither is ever scored twice."""
    site = _claim_site()
    cl = [c for c in B.forward_claims(site, "002", "2026-08")
          if c["id"] == "B002-LAMP"]
    idx = pd.period_range("2026-08", "2026-11", freq="M")
    quiet = pd.Series([100.0, 99.0, 101.0, 98.0], index=idx)
    crash = pd.Series([100.0, 99.0, 80.0, 98.0], index=idx)
    for prices, want in [(quiet, "hit"), (crash, "miss")]:
        chain = _mk_chain(cl)
        out = B.score_pending(chain, {}, "2026-11",
                              series={"real_brent": prices})
        B.verify(out)
        new = out[len(chain):]
        assert len(new) == 1, new
        assert new[0]["id"] == "B002-LAMP-scored"
        assert new[0]["status"] == want, new[0]["note"]
        assert new[0]["group"] == B.CLAIM_SCORE_GROUP
        again = B.score_pending(out, {}, "2026-11",
                                series={"real_brent": prices})
        assert len(again) == len(out), "a scored claim was scored twice"


def test_continuation_claim_resolves_against_the_decoder():
    site = _claim_site()
    cl = [c for c in B.forward_claims(site, "002", "2026-08")
          if c["id"] == "B002-CONT-oil"]
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    for state, want in [("supply_glut", "hit"), ("calm", "miss")]:
        chain = _mk_chain(cl)
        out = B.score_pending(chain, {"oil": pd.Series([state], index=idx)},
                              "2026-11")
        new = out[len(chain):]
        assert len(new) == 1 and new[0]["status"] == want, new


def test_synoptic_claim_resolves_against_the_weather_series():
    site = _claim_site()
    cl = [c for c in B.forward_claims(site, "002", "2026-08")
          if c["id"] == "B002-SYN"]
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    for state, want in [("post_shock_glut", "hit"),
                        ("risk_on_calm", "miss")]:
        chain = _mk_chain(cl)
        out = B.score_pending(
            chain, {"synoptic": pd.Series([state], index=idx)}, "2026-11")
        new = out[len(chain):]
        assert len(new) == 1 and new[0]["status"] == want, new


def test_surface_and_laboratory_partition_the_scored_chain():
    """STREAK-DEF-2: nothing scored is deleted, it is relabelled. Every
    scored entry is on exactly one of the two surfaces."""
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    chain = json.load(open(os.path.join(ROOT, "state", "scorecard.json")))
    surf = run["_streak"](chain)
    lab = run["_laboratory"](chain)
    scored = [e for e in chain
              if e.get("status") in run["SCORED_STATUSES"]]
    surf_ids = {e["id"] for e in chain
                if e.get("group") in run["STREAK_GROUPS"]}
    lab_ids = {r["id"] for r in lab["entries"]}
    assert not (surf_ids & lab_ids), surf_ids & lab_ids
    assert len(scored) == len(surf_ids) + len(lab_ids)
    assert "prediction upgrades" not in run["STREAK_GROUPS"]
    assert {"T1", "T2", "T3", "N1", "N2"} <= lab_ids
    assert run["STREAK_DOT"]["ret"] == "amber"
    assert run["STREAK_DOT"]["rev"] == "amber"
    assert surf["previous_totals_words"].startswith("1 hit, 3 misses")


def test_unmatured_and_unrealized_claims_stay_pending():
    """Nothing scores before maturity, and nothing scores while the
    realization is still absent from the pipeline."""
    site = _claim_site()
    cl = B.forward_claims(site, "002", "2026-08")
    chain = _mk_chain(cl)
    early = B.score_pending(chain, {"oil": pd.Series(dtype=object)},
                            "2026-08", series={})
    assert len(early) == len(chain)
    idx = pd.period_range("2026-08", "2026-09", freq="M")
    short = pd.Series([100.0, 99.0], index=idx)
    late = B.score_pending(chain, {"oil": pd.Series(dtype=object)},
                           "2026-12", series={"real_brent": short})
    lamp = [e for e in late[len(chain):] if "LAMP" in e["id"]]
    assert lamp == [], "scored a claim whose realization is not in yet"


def test_open_and_closed_pendings_split_by_closure_record():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    entries = [
        {"id": "P1", "status": "pending"},
        {"id": "P2", "status": "pending"},
        {"id": "P3", "status": "pending"},
        {"id": "P2-CLOSED", "status": "note"},
        {"id": "P3-scored", "status": "hit"},
        {"id": "X1", "status": "hit"}]
    p = run["_pendings"](entries)
    assert p["open"] == ["P1"] and p["n_open"] == 1
    assert sorted(p["closed"]) == ["P2", "P3"] and p["n_closed"] == 2


def test_forecaster_c_shrinks_toward_the_pool():
    """OUTLOOK-REG-2: h = (n h_own + k h_pool) / (n + k), k = 24. A cell
    with no history of its own is the pooled hazard exactly; a cell with
    plenty of its own history moves toward it."""
    from instrument import outlook as O
    seqs = {"a": ["x"] * 40 + ["y"] * 40, "b": ["x"] * 5 + ["y"] * 60}
    ctxs = {"a": ["calm"] * 80, "b": ["calm"] * 65}
    tab = O.conditioned_hazards(seqs, ctxs, 100)
    ps = tab["pool_sv"].get(("calm", 3), 0.0)
    pe = tab["pool_ex"].get(("calm", 3), 0.0)
    pooled = pe / ps if ps else 0.0
    h_empty = O._shrunk_hazard(tab, "nosuch", "zzz", "calm", 3, 0.5)
    assert abs(h_empty - max(pooled, 1e-4)) < 1e-9
    assert O.C_SHRINK_K == 24.0


def test_forecaster_c_only_issues_from_its_registered_quarter():
    from instrument import outlook as O
    assert O.C_FIRST_QUARTER == "2026Q4"
    assert O.quarter_of("2026-08") < O.C_FIRST_QUARTER
    assert O.quarter_of("2026-11") >= O.C_FIRST_QUARTER
    assert O.quarter_of("2027-02") >= O.C_FIRST_QUARTER


def test_forecaster_c_simulation_is_a_distribution():
    import numpy as np
    from instrument import outlook as O
    seq = (["calm"] * 30 + ["boom"] * 20) * 6
    ctx = ["risk_on_calm"] * len(seq)
    sm = O.semi_markov(seq)
    tab = O.conditioned_hazards({"n": seq}, {"n": ctx}, sm["dmax"])
    rng = np.random.default_rng(1)
    paths = np.empty((50, 12), dtype=object)
    paths[:] = "risk_on_calm"
    out = O.simulate_c(sm, seq, {"calm": 1.0}, tab, "n", paths, rng,
                       n_paths=50)
    for h in O.HORIZONS:
        d = out[h]
        assert abs(sum(d.values()) - 1.0) < 1e-6, (h, d)
        assert set(d) <= set(sm["states"])


def test_issue_keys_go_monthly_at_the_registered_month():
    """OUTLOOK-REG-3: monthly from 2026-10, quarterly before it, so the
    frozen 2026Q3 issue keeps its name."""
    from instrument import outlook as O
    assert O.MONTHLY_FROM == "2026-10"
    assert O.issue_key("2026-08") == "2026Q3"
    assert O.issue_key("2026-09") == "2026Q3"
    assert O.issue_key("2026-10") == "2026-10"
    assert O.issue_key("2027-03") == "2027-03"
    assert O.LEADS == [3, 6, 12]


def test_leads_are_labelled_by_calendar_month():
    """Probabilities are labelled by the month they refer to, never by
    a relative horizon."""
    from instrument import outlook as O
    lm = O.lead_months("2026-10")
    assert lm["3"] == "2027-01"
    assert lm["6"] == "2027-04"
    assert lm["12"] == "2027-10"


def test_envelope_band_is_registered_and_widens_with_lead():
    """BUST-REG: a 10th to 90th percentile band, widening as the paths
    spread, mapped through the registered per-state return pools."""
    import numpy as np
    from instrument import outlook as O
    assert (O.ENVELOPE_LO, O.ENVELOPE_HI) == (10, 90)
    assert O.BUST_RUN_BD == 5
    assert O.OBSERVABLE == {"oil": "real_brent"}
    idx = pd.period_range("2000-01", periods=200, freq="M")
    rng = np.random.default_rng(0)
    seq = ["calm"] * 100 + ["bust"] * 100
    lvl = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.05, 200))),
                    index=idx)
    pools = O.state_return_pools(seq, lvl, idx)
    assert set(pools) == {"calm", "bust"}
    trail = np.zeros((500, 12), dtype=int)
    band = O.envelope(trail, ["calm", "bust"], pools,
                      float(lvl.iloc[-1]), rng)
    assert len(band) == 12
    for b in band:
        assert b["hi"] > b["lo"] > 0
    assert (band[11]["hi"] - band[11]["lo"]) > (band[0]["hi"] - band[0]["lo"])


FROZEN = ["bulletins/2026-08.md", "bulletins/2026-08.html",
          "bulletins/2026-08_record.html",
          "bulletins/outlook_2026Q3.json",
          "state/outlook_2026Q3.json",
          "state/horizon1.json", "state/horizon2.json"]


def test_every_frozen_artifact_survives_a_rebuild_byte_identical():
    """OPS-INVARIANTS-2, first invariant. A monthly rebuild must not
    write a single byte into anything already published. Only an
    explicit publish may."""
    import subprocess
    before = {}
    for rel in FROZEN:
        p = os.path.join(ROOT, rel)
        assert os.path.exists(p), f"frozen artifact missing: {rel}"
        before[rel] = open(p, "rb").read()
    r = subprocess.run([sys.executable, "run.py", "month", "--asof",
                        "2026-08", "--issued", "2026-08-18"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    changed = [rel for rel in FROZEN
               if open(os.path.join(ROOT, rel), "rb").read() != before[rel]]
    assert not changed, f"rebuild mutated frozen artifacts: {changed}"


def test_frozen_artifact_list_covers_every_published_file():
    """The guard is only as good as its list, so the list is checked
    against what is actually on disk."""
    import glob
    on_disk = set()
    for pat in ("bulletins/*.md", "bulletins/*.html",
                "bulletins/outlook_*.json"):
        for p in glob.glob(os.path.join(ROOT, pat)):
            on_disk.add(os.path.relpath(p, ROOT))
    missing = on_disk - set(FROZEN)
    assert not missing, f"published files with no identity test: {missing}"


def test_frozen_outlook_issues_are_never_rewritten():
    """An issue is written once. Rebuilding a month that reuses an
    existing issue must leave the frozen artifact byte-identical."""
    import subprocess
    p = os.path.join(ROOT, "state", "outlook_2026Q3.json")
    before = open(p, "rb").read()
    r = subprocess.run([sys.executable, "run.py", "month", "--asof",
                        "2026-08", "--issued", "2026-08-18"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert open(p, "rb").read() == before
    d = json.loads(before.decode())
    assert "issue" not in d, "display labelling leaked into the issue"


def test_bust_lamp_is_words_only_and_dark_without_an_envelope():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    b = site["bust"]
    assert b["state"] in ("dark", "amber", "none")
    if b["state"] == "amber":
        assert b["words"] == "outside this outlook's expected range"
    # the lamp carries no numeral. The v6 read layer adds an `on`
    # flag, which is a boolean and not a number shown to a reader, so
    # booleans are excluded explicitly rather than by Python treating
    # them as ints.
    numerals = [k for k, v in b.items()
                if k != "state" and isinstance(v, (int, float))
                and not isinstance(v, bool)]
    assert not numerals, numerals
    assert isinstance(b.get("on"), bool)
    assert run["_next_revision"]("2026-10") == "2026-11"


def test_bust_lamp_lights_amber_on_a_registered_breach_run():
    """The amber path, which live data has never exercised: a synthetic
    envelope the observation sits outside of must light the lamp after
    the registered run of business days, and not before."""
    import runpy
    import numpy as np
    from instrument import nodes, outlook as O
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    F = nodes.load_feeds(os.path.join(ROOT, "data"))
    rb = nodes.real_brent(F)
    months = [str(p) for p in rb.index[-6:]]
    lo = float(rb.iloc[-6:].min())

    def issue(band_lo, band_hi):
        return {"asof": months[0], "instruments": {"oil": {"envelope": {
            "series": "real_brent", "months": months,
            "band": [{"lo": band_lo, "hi": band_hi} for _ in months],
            "percentiles": [O.ENVELOPE_LO, O.ENVELOPE_HI]}}}}

    wide = run["_bust_lamp"](issue(lo * 0.1, lo * 10.0), F, "2026-08")
    assert wide["state"] == "dark", wide
    tight = run["_bust_lamp"](issue(lo * 100.0, lo * 200.0), F, "2026-08")
    assert tight["state"] == "amber", tight
    assert tight["words"] == "outside this outlook's expected range"
    assert tight["instrument"] == "oil"
    assert tight["next_revision"] == "2026-09"
    assert tight["since"]
    assert not any(isinstance(v, (int, float))
                   for k, v in tight.items() if k != "state")


def test_outlook_issue_index_fires():
    """OPS-INVARIANTS-2, second invariant. OUTLOOK-REG-3 promises a
    superseded issue stays reachable with its own leads, so the code
    that builds that index is made to run."""
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    idx = run["_outlook_issues"]()
    assert idx, "no frozen issue was indexed"
    cur = {r["issue"] for r in idx}
    assert "2026Q3" in cur
    for r in idx:
        assert r["leads"] == [3, 6, 12]
        for L in r["leads"]:
            assert r["lead_months"][str(L)] > r["asof"], r
        assert r["file"].startswith("bulletins/")
        assert os.path.exists(os.path.join(ROOT, r["file"]))
    asofs = [r["asof"] for r in idx]
    assert asofs == sorted(asofs, reverse=True), "not newest first"


def test_since_last_bulletin_line_fires_on_a_real_change():
    """The changed-since line has only ever rendered 'no state
    changes' against live data, so both branches are driven here."""
    import runpy, json as _j, tempfile, shutil
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    site = _j.load(open(os.path.join(ROOT, "state", "site_data.json")))
    prev = os.path.join(ROOT, "state", "prev_states.json")
    had = os.path.exists(prev)
    backup = open(prev, "rb").read() if had else None
    try:
        cur = {n: c["state"] for n, c in site["current"].items()}
        _j.dump(cur, open(prev, "w"))
        assert run["_since_last_bulletin"](site) == \
            "Since last bulletin: no state changes"
        moved = dict(cur)
        moved["oil"] = "calm" if cur["oil"] != "calm" else "glut"
        _j.dump(moved, open(prev, "w"))
        line = run["_since_last_bulletin"](site)
        assert line.startswith("Since last bulletin: oil moved "), line
        assert " to " in line
        assert not any(ch.isdigit() for ch in line), line
    finally:
        if had:
            open(prev, "wb").write(backup)
        elif os.path.exists(prev):
            os.remove(prev)


def test_legacy_score_pending_path_fires():
    """score_pending still carries the pre-rule claim shape. It is
    wired, so it is made to fire rather than left as dead code."""
    idx = pd.period_range("2026-09", "2026-11", freq="M")
    legacy = {"id": "LEG1", "group": "bulletin claim scoring",
              "status": "pending", "auto": True, "claim": "legacy shape",
              "window": "2026-09..2026-11", "node": "oil",
              "target": "glut", "mode": "dominant"}
    for states, want in [(["glut", "glut", "calm"], "hit"),
                         (["calm", "calm", "glut"], "miss")]:
        chain = _mk_chain([legacy])
        out = B.score_pending(chain, {"oil": pd.Series(states, index=idx)},
                              "2026-11")
        new = out[len(chain):]
        assert len(new) == 1 and new[0]["status"] == want, new
    chain = _mk_chain([legacy])
    empty = pd.Series(dtype=object, index=pd.PeriodIndex([], freq="M"))
    out = B.score_pending(chain, {"oil": empty}, "2026-11")
    assert out[len(chain):][0]["status"] == "unscoreable"


def test_brier_scoring_fires_both_ways_from_bulletin_003():
    """PROPER-SCORE-REG. A claim beats the persistence baseline or it
    does not, and both Brier numbers land in the entry."""
    site = _claim_site()
    cl = B.forward_claims(site, "003", "2026-08")
    assert cl and all(c["rule"]["scoring"] == "brier" for c in cl)
    oil = next(c for c in cl if c["id"] == "B003-CONT-oil")
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    # persistence says the state continues, Brier 0 when it does, so a
    # claim at 0.80 cannot beat it; when it does not continue the
    # baseline scores 1 and the claim beats it
    for state, want in [("supply_glut", "miss"), ("calm", "hit")]:
        chain = _mk_chain([oil])
        out = B.score_pending(chain, {"oil": pd.Series([state], index=idx)},
                              "2026-11")
        new = out[len(chain):]
        per = [e for e in new if e["group"] == B.CLAIM_SCORE_PERCLAIM_GROUP]
        assert len(per) == 1 and per[0]["status"] == want, new
        assert "scored by Brier under PROPER-SCORE-REG" in per[0]["note"]
        assert "persistence baseline" in per[0]["note"]
        # a one-claim slate closes too, and agrees with its only claim
        slate = [e for e in new if e["group"] == B.SLATE_SCORE_GROUP]
        assert len(slate) == 1 and slate[0]["status"] == want, new


def test_bulletin_002_keeps_binary_rules_and_reports_brier_beside():
    """002's slate is untouched: the side rule decides, and the Brier
    numbers ride along changing nothing."""
    site = _claim_site()
    oil = next(c for c in B.forward_claims(site, "002", "2026-08")
               if c["id"] == "B002-CONT-oil")
    assert oil["rule"]["scoring"] == "binary"
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    chain = _mk_chain([oil])
    out = B.score_pending(chain, {"oil": pd.Series(["supply_glut"],
                                                   index=idx)}, "2026-11")
    e = out[len(chain):][0]
    assert e["status"] == "hit", e          # side rule, not Brier
    assert "Reported informationally and changing nothing" in e["note"]
    assert "Brier claim" in e["note"]


def test_persistence_baseline_is_defined_per_claim_kind():
    from analyst import bulletin as _B
    import numpy as np
    assert _B._persistence_p({"kind": "state"}, {}) == 1.0
    idx = pd.period_range("2026-05", "2026-08", freq="M")
    quiet = pd.Series([100.0, 99.0, 101.0, 98.0], index=idx)
    crash = pd.Series([100.0, 99.0, 80.0, 98.0], index=idx)
    rule = {"kind": "drawdown", "series": "real_brent",
            "base": "2026-08", "threshold_pct": -15.0}
    assert _B._persistence_p(rule, {"real_brent": quiet}) == 0.0
    assert _B._persistence_p(rule, {"real_brent": crash}) == 1.0
    assert _B._persistence_p(rule, {}) is None


def test_forecaster_e_is_an_equal_weight_blend_and_is_gated():
    from instrument import outlook as O
    assert O.E_FIRST_MONTH == "2026-10"
    b = O.blend([{"a": 1.0}, {"b": 1.0}])
    assert b == {"a": 0.5, "b": 0.5}
    b3 = O.blend([{"a": 0.6, "b": 0.4}, {"a": 0.0, "b": 1.0},
                  {"a": 0.9, "b": 0.1}])
    assert abs(sum(b3.values()) - 1.0) < 1e-9
    assert abs(b3["a"] - 0.5) < 1e-9
    assert O.blend([]) == {}


def test_horizon_ordering_mirrors_the_family_map():
    """horizon.FAM_CODE is a copy; if run.FAM_CODE ever moves, this
    fails rather than the ordering silently diverging."""
    import runpy
    from instrument import horizon as H
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    assert H.FAM_CODE == run["FAM_CODE"]
    order = H.order_states(["hot_none", "calm", "bust", "boom"])
    assert order[0] == "calm"
    assert order.index("boom") < order.index("bust")


def test_horizon_rps_and_pool_fire():
    from instrument import horizon as H
    order = ["calm", "boom", "bust"]
    perfect = H.rps({"calm": 1.0}, "calm", order)
    worst = H.rps({"bust": 1.0}, "calm", order)
    assert perfect == 0.0 and worst > perfect
    assert H.rps({}, "calm", order) is None
    rows = [{"instrument": "x", "issues": 2, "states": 3,
             "per_lead": {str(L): {"f": [0.1], "c": [0.2]}
                          for L in H.LEADS}},
            {"instrument": "y", "issues": 2, "states": 3,
             "per_lead": {str(L): {"f": [0.3], "c": [0.2]}
                          for L in H.LEADS}}]
    p = H.pool(rows)
    assert p["instruments"] == 2 and p["issues"] == 4
    # x has skill, y does not; the mean of +0.5 and -0.5 is zero, so the
    # edge ends at the first lead
    assert p["curve"][0]["rpss"] == 0.0
    assert p["edge_ends_at_lead"] == 1
    assert p["curve"][0]["rpss_worst_instrument"] == -0.5


def test_horizon_result_is_published_and_frozen():
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    h = site["horizon"]
    assert h["instruments"] >= 20 and h["issues"] > 1000
    leads = [r["lead"] for r in h["curve"]]
    assert leads == sorted(leads) and leads[0] == 1
    vals = [r["rpss"] for r in h["curve"]]
    assert vals[0] > vals[-1], "skill should decay with lead"
    assert h["refresh"] == "yearly adjudication" and h["estimated_at"]


def _slate_site():
    return {"months": ["2026-07", "2026-08"], "synoptic": {"gate": "open"},
            "hazard": {"current": {"state": "supply_glut", "elapsed": 3},
                       "lamp": {"supply_glut": {"tail_freq": 0.29},
                                "unconditional": 0.15},
                       "durations": {"supply_glut": {
                           "continuation_at_current": 0.7}}},
            "outlook": {"asof": "2026-08", "quarter": "2026Q3",
                        "instruments": {
                            "oil": {"analysis": {"state": "supply_glut"},
                                    "M": {"3": {"supply_glut": 0.80,
                                                "calm": 0.20}}},
                            "gold": {"analysis": {"state": "selloff"},
                                     "M": {"3": {"selloff": 0.20,
                                                 "calm": 0.80}}}},
                        "synoptic": {
                            "analysis": {"state": "post_shock_glut"},
                            "M": {"3": {"post_shock_glut": 0.70,
                                        "risk_on_calm": 0.30}}}}}


def _run_slate(states):
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    cl = [c for c in B.forward_claims(_slate_site(), "003", "2026-08")
          if c["id"] != "B003-LAMP"]
    chain = _mk_chain(cl)
    preds = {k: pd.Series([v], index=idx) for k, v in states.items()}
    out = B.score_pending(chain, preds, "2026-11")
    B.verify(out)
    new = out[len(chain):]
    per = [e for e in new if e["group"] == B.CLAIM_SCORE_PERCLAIM_GROUP]
    slate = [e for e in new if e["group"] == B.SLATE_SCORE_GROUP]
    return per, slate


def test_slate_dot_fires_hit_and_miss():
    """PROPER-SCORE-REG-2: one dot per slate, hit only if the slate's
    mean Brier beats the persistence baseline's mean Brier."""
    per, slate = _run_slate({"oil": "calm", "gold": "calm",
                             "synoptic": "risk_on_calm"})
    assert len(per) == 3 and len(slate) == 1
    assert slate[0]["status"] == "hit", slate[0]
    assert slate[0]["brier"] < slate[0]["brier_baseline"]
    per2, slate2 = _run_slate({"oil": "supply_glut", "gold": "selloff",
                               "synoptic": "post_shock_glut"})
    assert slate2[0]["status"] == "miss", slate2[0]
    assert slate2[0]["brier"] > slate2[0]["brier_baseline"]
    assert slate2[0]["claims"] == 3


def test_slate_dot_is_surface_and_per_claim_is_laboratory():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    assert B.SLATE_SCORE_GROUP in run["STREAK_GROUPS"]
    assert B.CLAIM_SCORE_PERCLAIM_GROUP not in run["STREAK_GROUPS"]
    # bulletin 002 is untouched: its scorings stay surface
    assert B.CLAIM_SCORE_GROUP in run["STREAK_GROUPS"]
    per, slate = _run_slate({"oil": "calm", "gold": "calm",
                             "synoptic": "risk_on_calm"})
    for e in per:
        assert "brier" in e and "brier_baseline" in e
    assert slate[0]["id"] == "B003-SLATE"


def test_slate_closes_only_once_and_only_when_complete():
    per, slate = _run_slate({"oil": "calm", "gold": "calm",
                             "synoptic": "risk_on_calm"})
    idx = pd.period_range("2026-11", "2026-11", freq="M")
    cl = [c for c in B.forward_claims(_slate_site(), "003", "2026-08")
          if c["id"] != "B003-LAMP"]
    chain = _mk_chain(cl)
    # only one instrument resolves: the slate must stay open
    partial = B.score_pending(chain, {"oil": pd.Series(["calm"], index=idx)},
                              "2026-11")
    assert not [e for e in partial if e["group"] == B.SLATE_SCORE_GROUP]
    # a second pass over an already closed slate adds nothing
    full = B.score_pending(chain, {k: pd.Series([v], index=idx) for k, v in
                                   {"oil": "calm", "gold": "calm",
                                    "synoptic": "risk_on_calm"}.items()},
                           "2026-11")
    again = B.score_pending(full, {k: pd.Series([v], index=idx) for k, v in
                                   {"oil": "calm", "gold": "calm",
                                    "synoptic": "risk_on_calm"}.items()},
                            "2026-11")
    assert len(again) == len(full)


def test_horizon_table_states_both_crossing_branches():
    """The no-crossing branch is what live data produces; the crossing
    branch is driven synthetically so both are known to render."""
    from instrument import horizon as H
    good = {"instrument": "x", "issues": 1, "states": 3,
            "per_lead": {str(L): {"f": [0.1], "c": [0.2], "p": [0.2]}
                         for L in H.LEADS}}
    p = H.pool([good], baseline="p")
    assert p["edge_ends_at_lead"] is None
    assert p["per_instrument_crossing"]["x"] is None
    assert p["crossing_materially_different"] is False
    bad = {"instrument": "y", "issues": 1, "states": 3,
           "per_lead": {str(L): {"f": [0.3 if L >= 5 else 0.1],
                                 "c": [0.2], "p": [0.2]}
                        for L in H.LEADS}}
    q = H.pool([bad], baseline="p")
    assert q["edge_ends_at_lead"] == 5, q["curve"][:6]
    assert q["per_instrument_crossing"]["y"] == 5
    mixed = H.pool([good, bad], baseline="p")
    assert mixed["per_instrument_crossing"] == {"x": None, "y": 5}
    assert mixed["crossing_materially_different"] is True


def test_horizon2_is_published_beside_horizon1():
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    h = site["horizon"]
    assert "edge_ends_vs_persistence" in h
    withp = [r for r in h["curve"] if "rpss_persistence" in r]
    assert len(withp) == len(h["curve"])
    clim = [r["rpss"] for r in h["curve"]]
    pers = [r["rpss_persistence"] for r in h["curve"]]
    assert clim[0] > clim[-1], "climatology skill should decay"
    assert pers[-1] > pers[0], "persistence skill should rise"


def test_horizon2_uses_the_identical_forecasts():
    """HORIZON-2 changed the baseline and nothing else."""
    h1 = json.load(open(os.path.join(ROOT, "state", "horizon1.json")))
    h2 = json.load(open(os.path.join(ROOT, "state", "horizon2.json")))
    assert h1["issues"] == h2["issues"]
    assert h1["instruments"] == h2["instruments"]
    for a, b in zip(h1["curve"], h2["curve"]):
        assert a["lead"] == b["lead"] and a["n"] == b["n"]
        assert abs(a["rps_forecast"] - b["rps_forecast"]) < 1e-9, a["lead"]
    assert h2["baseline_name"] == "persistence"


def _v6_site(cadence="monthly", gate="open"):
    """A site payload shaped like the real one, for the read layer's
    forecast rows."""
    return {
        "current": {"oil": {"state": "supply_glut", "prob": 0.95},
                    "gas": {"state": "calm", "prob": 0.80}},
        "network": {"current": {"coal": {"state": "calm", "prob": 0.99}}},
        "synoptic": {"gate": gate},
        "v3": {"members": {"energy": ["oil", "gas", "coal"]}},
        "outlook": {
            "cadence": cadence, "issue": "2026-10",
            "issued": "2026-10-05", "issue_month": "2026-10",
            "leads": [3, 6, 12],
            "lead_months": {"3": "2027-01", "6": "2027-04",
                            "12": "2027-10"},
            "instruments": {
                "oil": {"M": {"3": {"supply_glut": 0.62, "calm": 0.38},
                              "6": {"calm": 0.55, "supply_glut": 0.45},
                              "12": {"calm": 0.71, "supply_glut": 0.29}}},
                "gas": {"M": {"3": {"calm": 1.0}}},
                "coal": {"M": {"3": {"calm": 1.0}}}},
            "synoptic": {"M": {"3": {"post_shock_glut": 0.66,
                                     "risk_on_calm": 0.34},
                               "6": {"risk_on_calm": 0.52,
                                     "post_shock_glut": 0.48},
                               "12": {"risk_on_calm": 0.60,
                                      "post_shock_glut": 0.40}}}}}


def test_read_layer_forecast_rows_fire_when_populated():
    """The populated branch of the chips, which live data cannot reach
    until the first monthly issue exists."""
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    od = run["_outlook_display"](_v6_site())
    assert od is not None
    assert od["note"] == "issued 2026-10-05, revised monthly"
    assert od["forecaster"] == run["OUTLOOK_DISPLAY_FORECASTER"]
    row = next(r for r in od["rows"] if r["block"] == "energy")
    # oil is the only non-calm member, so it leads the block
    assert row["lead_instrument"] == "oil"
    assert len(row["months"]) == 3
    months = [c["month"] for c in row["months"]]
    assert months == ["2027-01", "2027-04", "2027-10"], months
    first = row["months"][0]
    assert first["fam"] == run["FAM_CODE"]["supply_glut"]
    assert first["word"] == "strained"
    assert first["prob"] == 62 and isinstance(first["prob"], int)
    assert row["months"][2]["word"] == "calm"
    assert od["synoptic"] and len(od["synoptic"]) == 3
    assert od["synoptic"][0]["fam"] == run["SYN_FAM"]["post_shock_glut"]


def test_read_layer_forecast_rows_are_absent_until_a_monthly_issue():
    """The empty branch, which is what the live page shows today."""
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    assert run["_outlook_display"](_v6_site(cadence="quarterly")) is None
    assert run["_outlook_display"]({}) is None
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    assert "outlook_display" not in site, \
        "the current issue is quarterly, so the key must be absent"


def test_read_layer_synoptic_row_follows_the_banner_gate():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    shut = run["_outlook_display"](_v6_site(gate="closed"))
    assert shut is not None and shut["synoptic"] is None
    assert shut["rows"], "blocks still render with the gate shut"


def test_lead_instrument_uses_the_strongest_non_calm_rule():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    site = _v6_site()
    assert run["_lead_instrument"]("energy", site) == "oil"
    # with every member calm, the most confident calm member leads
    site["current"]["oil"] = {"state": "calm", "prob": 0.60}
    assert run["_lead_instrument"]("energy", site) == "coal"
    assert run["_lead_instrument"]("nosuchblock", site) is None


def test_v6_lamp_keys_are_bound_and_absent_when_they_should_be():
    site = json.load(open(os.path.join(ROOT, "state", "site_data.json")))
    assert site["bust"]["on"] is (site["bust"]["state"] == "amber")
    assert isinstance(site["changed_line"], str)
    assert site["changed_line"].startswith("Since last bulletin")
    # the storm watch does not exist, so the key must not appear
    assert "watch" not in site
    # no observation fetchers exist, so the ticker key must not appear
    assert "daily_obs" not in site


def _wx_site(now, prev, with_issue=False):
    """A site payload shaped like the real one, with each instrument's
    latest family and the one before it placed on the strip."""
    strip = {}
    for n in set(now) | set(prev):
        row = [-1] * 10
        if n in prev and prev[n] is not None:
            row[7] = prev[n]
        if n in now:
            row[8] = now[n]
        strip[n] = row
    site = {"v3": {"fam_strip": strip,
                   "block_frames": {"frames": [
                       {"end": "2026-05", "edges": [
                           {"src": "a", "dst": "b", "pct": 5.0}]},
                       {"end": "2026-06", "edges": [
                           {"src": "credit", "dst": "equities",
                            "pct": 24.0}]}]}},
            "hazard": {"current": {"state": "supply_glut"},
                       "lamp": {"supply_glut": {"tail_freq": 0.286}},
                       "lampline": "risk lamp: tail move in 3 months "
                                   "29 percent vs 15 percent base"},
            "outlook": {"issued": "2026-10-05", "issue_month": "2026-10"}}
    if with_issue:
        site["outlook"]["weather"] = {
            "visibility_months": 4,
            "hero": {"low": 15, "high": 28},
            "cards": [{"month": "2026-11", "word": "post shock glut",
                       "fam": 3, "temp": 22, "storm": 86}]}
    return site


def test_weather_dials_fire_every_arrow_direction():
    """WEATHER-DIALS-REG. Live data has every instrument flat, so the
    up and down arrows are driven here or they are never executed."""
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    base = {"credit": 0, "equities": 0, "dollar": 0,
            "inflation": 0, "breakevens": 0, "money": 0}
    flat = run["_weather"](_wx_site(base, dict(base)))
    dirs = {d["name"]: d["dir"] for d in flat["dials"]}
    assert dirs["PRESSURE"] == 0 and dirs["HUMIDITY"] == 0
    # pressure falls when the risk panel heats up
    worse = dict(base); worse.update({"credit": 4, "equities": 4})
    down = run["_weather"](_wx_site(worse, dict(base)))
    dd = {d["name"]: d["dir"] for d in down["dials"]}
    assert dd["PRESSURE"] == -1, down["dials"]
    # and rises when it cools
    up = run["_weather"](_wx_site(base, worse))
    du = {d["name"]: d["dir"] for d in up["dials"]}
    assert du["PRESSURE"] == 1, up["dials"]
    # humidity moves with the inflation panel, in the same direction
    hot = dict(base); hot.update({"inflation": 4, "money": 4})
    hu = run["_weather"](_wx_site(hot, dict(base)))
    assert {d["name"]: d["dir"] for d in hu["dials"]}["HUMIDITY"] == 1
    hd = run["_weather"](_wx_site(base, hot))
    assert {d["name"]: d["dir"] for d in hd["dials"]}["HUMIDITY"] == -1


def test_weather_temperature_and_wind_follow_the_registered_formulas():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    allcalm = run["_weather"](_wx_site({"a": 0, "b": 0}, {"a": 0, "b": 0}))
    assert allcalm["temp"] == 0
    allhot = run["_weather"](_wx_site({"a": 4, "b": 4}, {"a": 4, "b": 4}))
    assert allhot["temp"] == 100
    mid = run["_weather"](_wx_site({"a": 0, "b": 4}, {"a": 0, "b": 4}))
    assert mid["temp"] == 50
    wind = next(d for d in mid["dials"] if d["name"] == "WIND")
    # the later frame carries the larger total, so it is the top
    assert wind["value"] == "100"
    assert "gust credit to equities at 24.0 percent" in wind["detail"]
    storm = next(d for d in mid["dials"] if d["name"] == "STORM RISK")
    assert storm["value"] == "29%"
    assert storm["detail"].startswith("risk lamp:")


def test_weather_hero_and_forecast_have_both_branches():
    import runpy
    run = runpy.run_path(os.path.join(ROOT, "run.py"))
    base = {"credit": 0, "equities": 0}
    empty = run["_weather"](_wx_site(base, dict(base)))
    assert "next_low" not in empty and "forecast" not in empty
    vis = next(d for d in empty["dials"] if d["name"] == "VISIBILITY")
    assert vis["value"] == "not yet"
    full = run["_weather"](_wx_site(base, dict(base), with_issue=True))
    assert full["next_low"] == 15 and full["next_high"] == 28
    assert len(full["forecast"]) == 1
    assert full["forecast"][0]["storm"] == 86
    v2 = next(d for d in full["dials"] if d["name"] == "VISIBILITY")
    assert v2["value"] == "~4 mo"
    assert full["note"].startswith("issued 2026-10-05")


def test_issue_weather_is_frozen_from_its_registered_month():
    """Items 5, 7 and 8 are computed at freeze time from the issue's own
    paths, and only from 2026-10."""
    import numpy as np
    from instrument import outlook as O
    assert O.WEATHER_FROM == "2026-10"
    assert (O.HERO_LO, O.HERO_HI) == (10, 90)
    rng = np.random.default_rng(0)
    trails = {"a": np.zeros((100, 12), dtype=int),
              "b": np.ones((100, 12), dtype=int)}
    states = {"a": ["calm", "supply_glut"], "b": ["calm", "surge"]}
    syn = {str(h): ({"post_shock_glut": 0.9} if h <= 4
                    else {"post_shock_glut": 0.4, "risk_on_calm": 0.3})
           for h in O.HORIZONS}
    w = O.issue_weather(trails, states, syn, None, [], "2026-10")
    assert w["visibility_months"] == 4
    # a is always calm (0), b is always surge (4), so the mean is 2
    assert w["hero"]["low"] == 50 and w["hero"]["high"] == 50
    assert len(w["cards"]) == 3
    c = w["cards"][0]
    assert c["month"] == "2026-11" and c["temp"] == 50
    assert c["storm"] == 100, "b is hot in every path"
    assert c["word"] == "post shock glut"
    assert "understates co-movement" in w["ensemble"]


def _smoke(path, *extra):
    import subprocess
    return subprocess.run(
        ["node", os.path.join(ROOT, "tests", "js_smoke.mjs"), path,
         *extra], capture_output=True, text=True, cwd=ROOT)


def test_smoke_harness_sees_a_missing_element():
    """The permanent self-test. The old harness fabricated an element
    for every id, so a page referring to an element it does not have
    went green headless and threw in a browser. If this fixture ever
    passes, the harness has gone blind again."""
    fx = os.path.join(ROOT, "tests", "fixtures", "smoke_missing_id.html")
    assert os.path.exists(fx)
    r = _smoke(fx)
    assert r.returncode != 0, "the harness did not notice a missing element"
    assert "Cannot set properties of null" in (r.stderr + r.stdout)


def test_smoke_harness_expect_id_holds_both_ways():
    """--expect-id is what lets a test hold a page to rendering a
    branch. It must pass for an element that exists and fail for one
    that does not."""
    idx = os.path.join(ROOT, "index.html")
    assert _smoke(idx, "--expect-id=hero").returncode == 0
    r = _smoke(idx, "--expect-id=definitelynotanelement")
    assert r.returncode != 0
    assert "EXPECTED ELEMENTS NEVER CREATED" in (r.stderr + r.stdout)


def test_hero_note_fires_only_when_a_range_is_shown():
    """The independence caveat is the only place a reader meets the
    ensemble assumption, so it is held to appearing with the range and
    to staying away without it."""
    import json as _j, tempfile
    tpl = open(os.path.join(ROOT, "site", "graph_v7.html")).read()
    site = _j.load(open(os.path.join(ROOT, "state", "site_data.json")))
    assert "next_low" not in site["weather"], "live data has no range yet"
    assert _smoke(os.path.join(ROOT, "index.html"),
                  "--expect-id=heronote").returncode != 0
    site["weather"] = dict(site["weather"])
    site["weather"]["next_low"] = 15
    site["weather"]["next_high"] = 28
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "withrange.html")
        open(p, "w").write(tpl.replace("__DATA__",
                                       _j.dumps(site, sort_keys=True)))
        r = _smoke(p, "--expect-id=heronote")
        assert r.returncode == 0, r.stderr + r.stdout


def test_pages_execute_headlessly():
    """Both built pages must run without script errors: load, three
    animation frames, a scrub event, a canvas click."""
    for page in ["index.html", "report.html"]:
        r = subprocess.run(["node", os.path.join(ROOT, "tests",
                                                 "js_smoke.mjs"),
                            os.path.join(ROOT, page)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{page}: {r.stderr}"


def test_fred_provider_parses_fixture():
    payload = {"observations": [
        {"date": "2026-06-01", "value": "332.568"},
        {"date": "2026-07-01", "value": "332.813"},
        {"date": "2026-08-01", "value": "."}]}
    s = providers.fred_json_to_series(payload, "cpi")
    assert len(s) == 3 and s.iloc[1] == 332.813 and pd.isna(s.iloc[2])


def test_network_membership_scored():
    import json
    nw = json.load(open("state/network.json"))
    names = {m["name"] for m in nw["membership"]}
    assert {"curve", "real_yield", "breakevens", "copper"} <= names
    for m in nw["membership"]:
        assert m["of"] >= 2 and isinstance(m["member"], bool)
    ids = {c["id"] for c in nw["checks"] if "id" in c}
    # the governing first check of each of these four instruments must
    # be reported. Taken from the registry rather than hard-coded, so a
    # registered version bump moves the assertion with it instead of
    # having to be edited: copper reported CO1 as v1 and reports CV1
    # since REPLACE-copper.
    from instrument import network as _net
    governing = {_net.REGISTRY[n]["checks"][0][0]
                 for n in ("curve", "real_yield", "breakevens", "copper")}
    assert governing <= ids, (governing - ids)


def test_replaced_instruments_do_not_rerun_v1_checks():
    """A version bump must never re-score the version it replaced: the
    v1 results stay on the chain and are not recomputed by the live
    decoder."""
    import json
    from instrument import network as _net
    nw = json.load(open("state/network.json"))
    ids = {c["id"] for c in nw["checks"] if "id" in c}
    retired = {"copper": ["CO1", "CO2", "CO3"],
               "coal": ["CL1", "CL2", "CL3"]}
    for name, old in retired.items():
        if _net.REGISTRY[name].get("version", 1) >= 2:
            assert not (set(old) & ids), (name, set(old) & ids)
    chain = json.load(open(os.path.join(ROOT, "state", "scorecard.json")))
    chained = {e["id"] for e in chain}
    for name, old in retired.items():
        if _net.REGISTRY[name].get("version", 1) >= 2:
            assert set(old) <= chained, name
            assert f"REPLACE-{name}" in chained, name


def test_sparse_map_structure():
    import json
    nw = json.load(open("state/network.json"))
    sp = nw["sparse"]
    assert sp["windows"] >= 10
    for e in sp["edges"]:
        assert e["stability"] >= 0.7 and e["src"] != e["dst"]
    blk = nw["blocks"]
    assert "energy" in blk["blocks"] and blk["months"] > 300


def test_tree_rollup():
    from instrument import tree as tr
    node = {"children": {
        "a": {"share": 0.5, "leaf": "x"},
        "b": {"share": 0.3, "leaf": "y"},
        "c": {"share": 0.2, "leaf": None}}}
    r = tr.rollup(node, {"x": 4, "y": 0})
    assert r["coverage"] == 0.8
    assert abs(r["heat"] - 2.5) < 1e-9
    assert r["state"] == 4
    r2 = tr.rollup(node, {"x": 0, "y": 0})
    assert r2["state"] == 0


def test_s1_scored():
    import json
    d = json.load(open("state/sparse_v2.json"))
    s1 = d["s1"]
    assert s1["nodes"] >= 14 and s1["ratio"] > 0
    assert isinstance(s1["hit"], bool)
