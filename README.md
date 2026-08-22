# market-weather

An autonomous economic analyst that publishes a monthly read on the macro weather and keeps a public, audited track record of every claim it has ever made. Regime instruments are decoded from free public data by fixed templates registered before estimation, and each one joins the public network only by passing at least two of its three held-out checks, with every result published whichever way it falls. A hash-chained scorecard makes the record append-only, and a numeral linter makes it impossible for the bulletin to publish a number the pipeline did not compute.

Site: https://gullirg.github.io/market-weather/
Record page: https://gullirg.github.io/market-weather/report.html

## Chain anchor

Scorecard entries: 137. Chain head hash: d91eee75311cc0ce.

Every entry carries the hash of the entry before it. Any retro-edit breaks the chain and `analyst.bulletin.verify` raises. To check the anchor yourself:

```bash
python3 -c "import json;from analyst import bulletin as B;e=json.load(open('state/scorecard.json'));B.verify(e);print(len(e), e[-1]['hash'])"
```

## Run

```bash
python3 run.py month --asof 2026-08 --issued 2026-08-18
python3 run.py publish --asof 2026-08
```

Tests: `python3 -m pytest tests/ -q` plus `node tests/js_smoke.mjs index.html` and `node tests/js_smoke.mjs report.html`.
