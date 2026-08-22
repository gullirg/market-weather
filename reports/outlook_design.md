# Borrowing from weather physics: the outlook layer and the streak

## 1. What transfers from numerical weather prediction, honestly

1. Ensemble forecasting. Operational centers replaced single forecasts
   with ensembles from perturbed initial conditions and publish the
   spread as the forecast. Transfer: our initial condition uncertainty
   is the current state posterior each instrument already emits; model
   uncertainty enters by estimating the transition structure on
   block-bootstrapped history; sampled trajectories through state space
   form the ensemble. The forecast is a distribution over named states
   by horizon, never a path.
2. The double baseline. A forecast counts as skillful only if it beats
   persistence (states stay put) and climatology (unconditional state
   frequencies). Persistence is ferociously strong for regimes;
   adopting this bar is the single most important honesty borrow.
3. The verification stack. Brier score for event probabilities, ranked
   probability score for multi-category state forecasts, skill scores
   expressed against climatology, reliability diagrams once enough
   forecasts accumulate. All scoreable on the chain, quarterly.
4. Analogue ensembles. The Lorenz analogue method, retired here for
   forecasting, was revived operationally as the analogue ensemble: the
   K nearest historical states vote on what followed. Our analogue
   engine supplies this second forecaster for free, with its existing
   exclusion windows preventing leakage.
5. Assimilation vocabulary. The decoded present is the analysis; the
   forecast is the outlook. The page adopts the words.

Explicitly not borrowed: dynamical simulation (their equations are
physics, ours would be invention) and determinism beyond the
predictability horizon, where meteorology itself falls back to climate
probabilities, which is what the successor representation layer is.

## 2. The outlook, registered form

OUTLOOK v1, two forecasters and two baselines, all specified before the
first scored quarter:

1. Forecaster M (Markov): per-instrument semi-Markov transition
   structure (duration-dependent exit hazards, absorbing the
   long-queued G2), estimated once per quarter on full history; horizon
   1 to 12 months state distributions; synoptic occupancy as the
   discounted successor representation over the joint decoded synoptic
   series, discount 0.9.
2. Forecaster A (analogue ensemble): top K = 20 analogues of the
   current joint state under the registered weights, exclusion 12
   months, empirical distribution of states at each horizon.
3. Baselines: persistence (current state with probability one) and
   climatology (unconditional state frequencies over full history).
4. Scoring, quarterly, chained: ranked probability skill score against
   climatology per instrument and for the synoptic layer, at horizons
   3, 6 and 12 months; a forecaster is called skillful at a horizon
   only if it also beats persistence there. Reliability diagram
   published after eight scored quarters, not before.
5. Publication: probabilities only, in the plume and cone visuals; no
   state-word predictions in the bulletin until a forecaster has two
   consecutive skillful quarters at that horizon, and then only with
   its skill score printed beside it.

## 3. Visualization borrows

1. The plume: stacked probability bands over the next 12 months in the
   family palette, the outlook's primary object, one per instrument in
   its card and one for the synoptic layer.
2. The cone: the synoptic outlook drawn with widening uncertainty by
   horizon, hurricane-cone grammar, on the graph page behind an OUTLOOK
   toggle that never displaces the analysis view.
3. Meteograms: on card tap, 12 months of decoded past flowing into 12
   months of probability bands, one small multiple per instrument.
4. Analysis and outlook labelled as such wherever both appear.

## 4. The streak, definition before decoration

1. Surface: one quiet row of dots under the banner, uptime-monitor
   grammar: green hit, red miss, grey null or unscoreable, hollow
   pending; beside it one pair in words and numerals, hits and misses;
   the row is the last 40 scored claims.
2. Governance: a chained entry STREAK-DEF, appended before the first
   render, fixing what counts as a dot: entries whose group marks them
   as scored forward-looking claims (bulletin claim scorings and, once
   live, outlook quarter scorings), explicitly excluding registrations,
   joins, operational entries, and held-out design checks. The surface
   number is thereby itself auditable against the chain.
3. Click-through: the row links to the record page anchored at the
   scorecard, filtered to exactly the STREAK-DEF set, most recent
   first, each dot resolving to its full chain entry.
4. The streak never reorders, never truncates misses, and renders nulls
   as grey rather than omitting them.
