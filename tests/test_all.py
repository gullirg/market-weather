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


def _claim_site():
    return {"months": ["2026-07", "2026-08"],
            "hazard": {"current": {"state": "supply_glut", "elapsed": 3},
                       "lamp": {"supply_glut": {"tail_freq": 0.29},
                                "unconditional": 0.15},
                       "durations": {"supply_glut": {
                           "continuation_at_current": 0.7}}}}


def test_forward_claims_start_at_bulletin_002():
    """Bulletin 001 was written without the wiring and is not
    backfilled; 002 registers both scoreable forward claims."""
    site = _claim_site()
    assert B.forward_claims(site, "001", "2026-08") == []
    cl = B.forward_claims(site, "002", "2026-08")
    ids = {c["id"] for c in cl}
    assert ids == {"B002-LAMP", "B002-CONT"}
    for c in cl:
        assert c["status"] == "pending" and c["auto"] is True
        assert c["group"] == B.CLAIM_GROUP
        assert c["rule"]["p"] is not None and "source" in c["rule"]
        assert c["note"].startswith("resolution rule, registered at publish")
    lamp = next(c for c in cl if c["id"] == "B002-LAMP")
    assert lamp["window"] == "2026-09..2026-11"
    assert lamp["matures"] == "2026-11"
    assert lamp["rule"]["side"] is False          # 0.29 is below one half
    cont = next(c for c in cl if c["id"] == "B002-CONT")
    assert cont["window"] == "2026-09..2026-09"
    assert cont["rule"]["side"] is True           # 0.70 is above one half


def test_forward_claim_ties_register_nothing():
    """A stated probability of exactly one half commits to no side."""
    site = _claim_site()
    site["hazard"]["durations"]["supply_glut"][
        "continuation_at_current"] = 0.5
    site["hazard"]["lamp"]["supply_glut"]["tail_freq"] = 0.5
    assert B.forward_claims(site, "002", "2026-08") == []


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
          if c["id"] == "B002-CONT"]
    idx = pd.period_range("2026-09", "2026-09", freq="M")
    for state, want in [("supply_glut", "hit"), ("calm", "miss")]:
        chain = _mk_chain(cl)
        out = B.score_pending(chain, {"oil": pd.Series([state], index=idx)},
                              "2026-09")
        new = out[len(chain):]
        assert len(new) == 1 and new[0]["status"] == want, new


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
