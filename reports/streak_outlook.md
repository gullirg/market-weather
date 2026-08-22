# Streak and outlook

Branch `streak-outlook`, merged to `main` on 2026-08-22, outside the
September publication window. Chain moved from 137 entries, head
`d91eee75311cc0ce`, to 140 entries, head `2a86ac389b3f5c49`.

## 1. STREAK-DEF, as chained

Appended before the first render, group "operations, registered before
first render", status hit.

Claim:

> the public streak renders scored forward-looking claims only. An
> entry is a dot if and only if its group is one of: 'out of sample',
> 'prediction upgrades', 'corrections', 'bulletin claim scoring',
> 'outlook quarter scoring'. The first three are the forward-looking
> claims already on the chain; the last two are reserved now so that
> future scorings are auditable against a definition fixed before the
> first render. Dot colour: green for status hit or oos, red for miss
> or fail, grey for null, un, ret or rev, hollow ring for pending. The
> row shows the last forty matching entries in chain order and the
> totals are taken over the whole matching set.

Note:

> excluded group strings, every one present on the chain at
> registration: 'held-out identification', 'graph nodes', 'graph
> edges', 'stage 6 audit', 'v2 wave 1, registered before estimation',
> 'transmission rewiring, registered before estimation', 'fix wave,
> registered before each run', 'phase A and B, registered before
> estimation', 'structural check, registered before computation',
> 'network membership checks, registered before estimation', 'network
> membership, rule: 2 of 3', 'tree leaf checks, registered before
> estimation', 'G12 daily instrument checks, registered before
> estimation', 'G12 public gate, registered before estimation',
> 'registered queue', 'registration, recorded before estimation',
> 'nervous system architecture', 'composition hierarchy', 'network
> population', 'operations, registered before first render'. These are
> registrations, joins, membership rules, held-out design checks,
> operational entries and unscored pendings, none of which is a
> forward-looking claim. At registration the matching set holds eight
> entries: one out-of-sample call, three failed prediction upgrades,
> two registered nulls and two corrections. The streak is therefore
> small and unflattering by construction, which is the point: it never
> reorders, never truncates misses and never omits nulls.

## 2. Dot totals as rendered

The matching set holds eight entries out of one hundred and forty on
the chain. The index row renders eight dots and the pair "1 hit, 3
misses". The record page adds the null count: one hit, three misses,
four null or corrected.

In chain order, oldest first:

1. B1, out of sample, status oos, green. The 2026 war squeeze called at
   full probability in March and April.
2. T1, prediction upgrades, status fail, red. Regime-conditioned
   direction beats random walk.
3. T2, prediction upgrades, status fail, red. Calibrated intervals beat
   unconditional.
4. T3, prediction upgrades, status fail, red. Event rules add warning
   value.
5. N1, prediction upgrades, status null, grey. No three month
   directional edge, as registered.
6. N2, prediction upgrades, status null, grey. No twelve month
   directional edge, as registered.
7. F1, corrections, status ret, grey. The 2026 recession probabilities
   from the yield spread, retracted.
8. F2, corrections, status rev, grey. The May 2026 hoarding read,
   revised to squeeze under live deflation.

Everything is derived from the chain at build time in
`run._streak`; no total is hand kept, and the totals reach the page
through `build_payload`.

The honest finding behind that small number: this chain carries no
bulletin claim scorings at all. `analyst.bulletin.score_pending` has
never appended an entry, because no pending claim on the chain carries
the `auto` flag. The record's ninety-six hits are overwhelmingly
held-out design checks and membership joins, which are not forecasts.
The streak says so by being nearly empty, and it will fill from the
outlook quarter scorings.

## 3. OUTLOOK-REG, as chained

Group "registration, recorded before estimation", status note.

Claim:

> OUTLOOK v1 is registered in full before any estimate is produced. Two
> forecasters and two baselines. Forecaster M, Markov: a per-instrument
> semi-Markov transition structure with duration-dependent exit
> hazards, absorbing the long-queued G2, re-estimated once per quarter
> on full history, giving state distributions at horizons 1 to 12
> months; synoptic occupancy as the discounted successor representation
> over the joint decoded synoptic series with discount 0.9. Forecaster
> A, analogue ensemble: the top K of 20 analogues of the current joint
> state under the already registered analogue weights, exclusion window
> 12 months, taking the empirical distribution of states at each
> horizon. Baselines: persistence, the current state with probability
> one, and climatology, the unconditional state frequencies over full
> history.

Note:

> Scoring, quarterly and chained as OUTLOOK-S-<quarter> in group
> 'outlook quarter scoring': ranked probability skill score against
> climatology, per instrument and for the synoptic layer, at horizons
> 3, 6 and 12 months. A forecaster is called skillful at a horizon only
> if it also beats persistence at that horizon; the climatology skill
> score alone is not sufficient. A reliability diagram is published
> only after eight scored quarters, never before. Publication rule:
> probabilities only, in the plume and cone visuals, and no state-word
> prediction enters the bulletin until a forecaster has two consecutive
> skillful quarters at that horizon, and then only with its skill score
> printed beside it. Nothing is estimated or scored by this entry; it
> fixes the form so that the first forecast cannot be tuned after the
> fact. Full design in reports/outlook_design.md section 2.

G2 is closed by `G2-CLOSED`, group "registered queue closure", status
note: semi-Markov episode targets are absorbed into forecaster M's
duration-dependent exit hazards. The chain is append-only, so the
original G2 row keeps its pending status and the published pending
count still includes it. That entry is the closure record, not an edit.

## 4. The first frozen forecast

1. Path, issued: `state/outlook_2026Q3.json`.
2. Path, frozen at publish: `bulletins/outlook_2026Q3.json`, copied by
   `cmd_publish` exactly as the bulletin is copied.
3. Quarter: 2026Q3. Issue date: 2026-08-18. Asof month: 2026-08.
4. Contents: 22 instruments and the synoptic layer, each with
   forecaster M and forecaster A distributions at all twelve horizons,
   climatology, persistence, the analysis state and its elapsed
   duration; the synoptic layer additionally carries the discounted
   successor representation at 0.9. Deterministic seed 3249580628,
   derived from the asof month, over 2000 simulated paths.
5. Re-estimation is once per quarter as registered. A later build
   inside the same quarter reuses the issued file rather than
   re-estimating, so a forecast is scored as issued and not as later
   revised.

## 5. When the first scoring happens

Nothing is scored by this campaign. The 2026Q3 issue targets 2026-11 at
the three month horizon, 2027-02 at six and 2027-08 at twelve.

1. First scoring: the 2026Q4 quarter end, December 2026, chained as
   `OUTLOOK-S-2026Q4`. Only the three month horizon of the 2026Q3 issue
   has a decoded realization by then.
2. The six month horizon first scores at the 2027Q1 quarter end.
3. The twelve month horizon first scores at the 2027Q3 quarter end.
4. The reliability diagram is not publishable until eight scored
   quarters have accumulated, which is 2028Q4 at the earliest.
5. No state word may enter the bulletin before two consecutive skillful
   quarters at a horizon, so the earliest possible bulletin wording
   change is the 2027Q1 quarter end, and only if both 2026Q4 and 2027Q1
   are skillful at three months. The bulletin generator is untouched by
   this campaign.

## 6. Payload

Diff of `state/site_data.json` against a pre-branch build at the same
asof: two keys added, `streak` and `outlook`, none removed, fifteen of
the sixteen pre-existing keys byte-identical (`analogues`, `current`,
`daily_shadow`, `frames`, `hazard`, `health`, `issued`, `months`,
`net`, `network`, `oil36`, `spill`, `strip`, `synoptic`, `v3`).

One pre-existing key differs, `score`, from `hit: 95` to `hit: 96`.
That is exactly the one chained entry in this campaign with a scoreable
status, STREAK-DEF. OUTLOOK-REG and G2-CLOSED carry status note and are
not counted. The difference is the arithmetic of an append-only chain
growing, not a change to how any pre-existing field is computed.

## 7. Gate

1. `node tests/js_smoke.mjs index.html` OK, both motion passes.
2. `node tests/js_smoke.mjs report.html` OK, both motion passes.
3. `python3 -m pytest tests/ -q` 23 passed.
4. Both smoke passes on index execute the outlook code path. Verified
   with a probe harness that raises if the OUTLOOK toggle listener is
   absent; it passed on both passes.
5. Chain verified before and after every write session. 140 entries,
   head `2a86ac389b3f5c49`.

## 8. Limitations

1. The streak has eight dots because the chain has eight scored
   forward-looking claims. The row will stay sparse until outlook
   quarters begin scoring in December 2026.
2. The legacy chain entries in the streak set carry placeholder claims
   of the form "see site scorecard T1". The record page joins them to
   the readable descriptions it already carries and keeps the raw chain
   claim visible in the expanded row. The index dot tooltips still show
   the chain text, which is what the chain says.
3. G2 still counts as pending in the published totals, because the
   chain cannot be edited.
4. Forecaster A drops an analogue at a horizon whose successor month
   falls outside the sample, and returns an empty distribution if every
   analogue is dropped. In the 2026Q3 issue that never happens: all
   twenty analogues resolve at all twelve horizons for all twenty two
   instruments and for the synoptic layer, so no horizon renders as a
   gap. The guard is untested by live data.
