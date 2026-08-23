# Performance campaign 1

Branch `performance-1`. Chain moved from 140 entries, head
`2a86ac389b3f5c49`, to 163 entries, head `80417d51e3ed4da6`. Twenty
three entries appended: nine hits, five misses, one failed gate, one
pending goal, seven registrations and amendments.

Registration came first in every stage. No template, window, check or
threshold was changed after a result was seen, and no shut gate was
reopened.

## 0. PERF-GOAL

1. Chained before any work, group "campaign goal, registered before
   work", status pending, auto, maturity 2026-12-31.
2. Terms: at the first outlook scoring a majority of instruments show
   positive RPSS against climatology and also beat persistence at the
   three month horizon, and the stage E calibration upgrade shows a
   validated Brier improvement.
3. The entry is auto-flagged but resolves against other chain entries
   rather than a pipeline series, so a registered campaign rule kind
   leaves it pending until December judges it deliberately.

## 1. Stage A, the daily decoder rebuilt as D-HSMM

1. Registration: REG-DHSMM, amended before estimation by
   REG-DHSMM-AMEND.
2. Four family states on the unchanged G12 daily panel, negative
   binomial sojourns on duration minus five so no stay shorter than
   five business days is representable, diagonal Gaussian emissions,
   everything estimated once by EM. Labels pinned to the G12 templates
   at initialization. Filtered causal decode, the same semantics G12
   used, so the flip rate is comparable.
3. One estimation over 9669 business days. EM converged in 27
   iterations to per-state mean sojourns of 42 to 86 business days.
4. DH1 hit. 4 of 5 pinned episodes captured within 25 business days;
   the 2014-11 shale glut was missed.
5. DH2 miss. 38.76 family flips per decade over 8906 eligible business
   days, against a budget of 6 and against the 32.26 G12 recorded on
   the same measure.
6. DH3 miss. Median family run 35.0 business days against a floor of
   40, and against G12's 46.0.
7. DH2b, registered as a diagnostic before estimation after synthetic
   validation showed a filtered marginal does not inherit the model's
   minimum stay. The MAP segmentation honours the five day minimum
   exactly, shortest run 5, median run 54.5, and still flips 33.39
   times per decade while capturing only 3 of 5 episodes.
8. DH-GATE fail. The gate required DH1 and DH2. The registered
   diagnosis is falsified: the chatter was attributed to the geometric
   sojourn of a vanilla hidden Markov model, and an explicit duration
   model produced more flips rather than fewer on both decodes. The
   instability is in the daily features, not in the duration prior.
9. No chip appears. GATE-G12 was not reopened and the storm watch lamp
   is untouched. Per the registration the daily clock question is
   closed for the year.

## 2. Stage B, decomposability sharpened

1. Registration: REG-S2. The bar stayed at 1.5.
2. One run over 22 instruments, 199 months, 18 windows.
3. S2a miss. Ratio 1.11, within 4.27 against between 3.85, with the
   first principal component removed.
4. The same panel un-removed scores 1.31, so removing the common
   factor made near-decomposability worse rather than better and the
   registered hypothesis is falsified. The first principal component
   carries 0.212 of panel variance and evidently carries within-family
   co-movement at least as much as cross-family.
5. S2b miss. Fast components, residuals from a centered 12 month
   moving average, reach 1.38 over 16 windows: the best of the three
   measures and still short. Slow components score 1.28 from a single
   full sample GFEVD, published with no verdict claimed.
6. Ordering of the three: fast 1.38, un-removed 1.31, common factor
   removed 1.11. The finding is one sentence in the record page's tree
   note, with every numeral coming from the payload.

## 3. Stage C, commodity v2

1. Registration: REG-COMMODITY-V2, including the replacement rule of
   2 of 3 plus a hit on the diagnosed window, and a disclosure that
   the third feature first exists in 1998-11 so most of CV2's window
   decodes with it masked.
2. copper v2, 3 of 3. CV1 dominant bust at share 1.00 on 2014-09 to
   2016-02, the window v1 missed with calm dominant and a bust share
   of 0.44. CV2 dominant bust 0.68. CV3 dominant boom 1.00.
3. coal v2, 3 of 3. CB1 dominant bust 1.00. CB2 present 0.80. CB3
   present 1.00.
4. Both earned replacement. REPLACE-copper and REPLACE-coal are
   chained and the live registry runs the three-feature decoders.
5. What replaced what: copper v1, two momentum features, replaced by
   copper v2, the same two plus the rolling z of log real price
   against its own trailing 60 month mean. coal v1 likewise. Coal was
   replaced on the shared-feature-set hypothesis, not on a recorded
   miss of its own; coal v1 was 3 of 3.
6. v1's record is untouched. CO1, CO2, CO3, CL1, CL2 and CL3 stay
   scored on the chain, keep their rows on the record page, and are
   never re-run against v2. A test enforces exactly that, and the
   membership test now takes its spot-check ids from the registry so a
   registered version bump moves the assertion instead of breaking it.
7. The enlarged panel still passes: block GFEVD sample 432 months,
   sparse map 22 nodes and 151 edges, membership 15 of 15.

## 4. Stage D, forecaster C

1. Registration: OUTLOOK-REG-2, an append-only amendment. Nothing was
   estimated or scored.
2. Per-instrument exit hazards conditioned on the current synoptic
   state, shrunk toward the pooled across-instrument hazard with k
   fixed at 24; next-state rows conditioned the same way and shrunk
   toward forecaster M's unconditional row; forward simulation
   identical to M over one shared set of simulated weather paths, so
   every instrument is conditioned on a common weather.
3. C is gated to its registered first quarter, 2026Q4, and cannot join
   the frozen 2026Q3 issue, which is untouched. Verified on a scratch
   run that writes nothing: absent at Q3, present for all 22
   instruments at Q4, every distribution proper.
4. Scoring begins 2027Q1 on the same RPSS schedule as M and A. The
   registered success gate is C beating both M and A on three month
   RPSS in each of its first two scored quarters.
5. The outlook panel renders C's bands beside M and A, labelled by
   letter, and appears only when the payload carries C.

## 5. Stage E, the calibration audit

1. Registration: REG-CAL, including two disclosures made before the
   run. The expanding window is computed as one forward pass per
   instrument because the endpoint of a smoothed decode on data
   through t is exactly the filtered posterior at t, an identity
   verified numerically to five parts in ten to the fifteenth. EM
   fitted spreads and the deflator splice constant are held at full
   sample values because the legacy decoders are untouchable, so the
   audit isolates the effect of smoothing rather than of parameter
   drift.
2. Scope: 6830 causal decodes across all 22 live instruments from
   1998-01 to 2026-08. The read-only reconstruction reproduces the
   live decode for all 22 instruments at 1.0000 agreement, so the
   audit measures the published object.
3. Reliability, printed confidence against how often it was right:
   0.470 prints 0.461, 0.552 prints 0.558, 0.652 prints 0.638, 0.753
   prints 0.720, 0.855 prints 0.885, 0.962 prints 0.990.
4. Over the whole audit the mean printed confidence is 0.8382 against
   a realized agreement of 0.8553, so the printed numbers are if
   anything slightly modest.
5. CAL-1 miss, not adopted. Isotonic recalibration fitted on 3769
   months before 2015-01 and validated on 3061 months from 2015-01:
   Brier 0.09854 raw against 0.09841 recalibrated, a relative
   improvement of 0.0013 against the registered adoption threshold of
   0.05.
6. The check is a miss because its adoption condition was not met, not
   because the instrument failed. This is the first audit of any
   confidence number the system prints and it found them sound.
   Decoders are untouched either way, and the curve is published on
   the record page with every numeral coming from the payload.

## 6. The campaign against PERF-GOAL's terms

| Term | Status now | Judged |
|---|---|---|
| Majority of instruments positive RPSS against climatology at three months | Not yet measurable. The first outlook scoring is OUTLOOK-S-2026Q4 in December 2026 | December 2026 |
| The same majority beats persistence at three months | Not yet measurable, same schedule | December 2026 |
| Stage E shows a validated Brier improvement | Failed. Improvement 0.0013 against a threshold of 0.05, not adopted | Settled now |

1. One of PERF-GOAL's three terms is already settled and it failed, on
   the honest ground that there was nothing to improve.
2. The two forecasting terms remain open and are judged in December
   against OUTLOOK-S-2026Q4.
3. PERF-GOAL stays pending on the chain until then and is not scored
   by this campaign.

## 7. Payload

Diff of `state/site_data.json` against the campaign's starting build at
the same asof:

1. Two keys added, `calibration` and `s2`, both display fields for the
   stage B and stage E findings.
2. Four keys differ: `network` and `v3`, whose only changes are the
   copper and coal rows carried by REPLACE-copper and REPLACE-coal;
   `score`, by exactly this campaign's chained statuses, nine hits,
   five misses, one fail and one pending; and `pendings`, by
   PERF-GOAL alone.
3. Fifteen keys byte-identical: `analogues`, `current`,
   `daily_shadow`, `frames`, `hazard`, `health`, `issued`, `months`,
   `net`, `oil36`, `outlook`, `spill`, `streak`, `strip`, `synoptic`.
   The replacement did not ripple beyond the two instruments it
   names, and the frozen 2026Q3 outlook is untouched.

## 8. Gate

1. `node tests/js_smoke.mjs index.html` OK, both motion passes.
2. `node tests/js_smoke.mjs report.html` OK, both motion passes.
3. `python3 -m pytest tests/ -q` 33 passed, up from 29: three tests for
   forecaster C and one guard that a replaced instrument never re-runs
   the version it replaced.
4. Chain verified before and after every write session. 163 entries,
   head `80417d51e3ed4da6`.

## 9. Every chained id, in order

1. PERF-GOAL pending.
2. REG-DHSMM note, REG-DHSMM-AMEND note.
3. DH1 hit, DH2 miss, DH3 miss, DH2b note, DH-GATE fail.
4. REG-S2 note, S2a miss, S2b miss.
5. REG-COMMODITY-V2 note, CV1 hit, CV2 hit, CV3 hit, CB1 hit, CB2 hit,
   CB3 hit, REPLACE-copper hit, REPLACE-coal hit.
6. OUTLOOK-REG-2 note.
7. REG-CAL note, CAL-1 miss.

## 10. Limitations

1. Two of the five stages produced negative results and both were
   registered diagnoses that turned out to be wrong. The daily clock
   is closed for the year by its own registration; nothing in this
   campaign licenses another attempt at it.
2. Forecaster C is implemented and gated but has never issued. Its
   first real issue is the 2026Q4 outlook and its first score is
   2027Q1, so nothing here demonstrates that it works on live data.
3. The calibration audit holds EM-fitted spreads and the deflator
   splice constant at full sample values, which leaves a known
   residual look-ahead. Removing it would mean changing the legacy
   decoders, which this campaign's first invariant forbids.
4. S2's sibling sets follow the composition tree, so em_dollar,
   activity, housing, claims and money are ungrouped and contribute
   only to between-sibling pairs. A different grouping would give a
   different ratio; none was tried.
