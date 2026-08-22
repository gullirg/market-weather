# Runbook

1. One-time: copy .env.example to .env, add FRED and EIA keys (free), optionally the Anthropic key for the prose layer. `pip install -r requirements.txt`.
2. Nightly (cron): `python run.py refresh --source live` refreshes the FRED CSVs; health results land in state/feed_health.json on the next month run.
3. Monthly, 3rd business day: `make month ASOF=YYYY-MM`, read state/monthly_diff.md and state/draft_YYYY-MM.md, then `make publish ASOF=YYYY-MM`. Commit and push; the site is index.html plus bulletins/.
4. Degraded feeds are masked and announced automatically. Do not hand-edit a draft; fix the feed or ship the degradation.
5. At most one registered queue item (G1 to G4) may be run per month; append its result to the scorecard whichever way it falls. The chain verifier rejects any retro-edit.
6. Still to wire on this host, per the build prompt decision tree: EIA API v2 for inventories (branch a), the futures curve via yfinance CL contracts (branch b, else stays masked), TTF (attempt once, else permanently-external).
