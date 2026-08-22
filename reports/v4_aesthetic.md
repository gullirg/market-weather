# v4 aesthetic restoration

Branch `aesthetic-v4`, merged to `main` on 2026-08-22, outside the
September publication window. Site layer only.

## 1. What changed visually, stage

1. The stage renders to a canvas layer instead of generated SVG
   markup. The coordinate system, POS map, click hit-testing at radius
   forty-six, pins, slider, cards and DATA access are the ones that
   were already there.
2. Surface is `#0b0e14` under a radial vignette that lifts the centre
   by six points of luminance to `#161c28` and falls back to base. The
   gradient is built once per resize and filled per frame.
3. Blocks are radial gradient discs, family colour at half alpha in
   the core falling to zero at radius forty-six, with a one-pixel rim
   in the same colour. The rim is solid for a block live in the frame
   and dashed for one awaiting data. A faint outer ring at radius
   fifty-two marks a block holding an in-frame member that joined
   after founding. Family colour still comes from the existing famcode
   priority logic.
4. Orbs breathe between scale one and one and five hundredths. The
   period is one and six tenths of a second plus two and two tenths
   times the block's strongest member confidence at LIVE, so a surer
   block breathes slower and deeper. Scrubbed into history every block
   takes a uniform calm breath at six tenths.
5. Edges are quadratic curves with the control point pushed
   perpendicular from the midpoint by eight percent of the segment
   length. A faint neutral stroke sits underneath at the width the
   previous build used. Particles travel source to destination on top,
   respawning at source, count set by the edge percentage and capped
   globally at four hundred with proportional allocation above the
   cap. Across all fifty-three frames the busiest allocation is two
   hundred and forty-two particles on forty-eight edges, so the cap
   never binds on current data.
6. Edge percentages are hidden at rest. They appear on a block's
   incident edges while it is selected, and on a single edge while the
   pointer is over its midpoint. Block names and family words are
   unchanged.
7. The active pin carries a soft glow in the dominant family colour of
   its frame, the modal non-calm family across blocks in that month,
   grey when there is none. Slider styling is untouched.
8. Cards are frosted glass over a solid fallback, with a hairline
   white border and a three-pixel glow on the lamp dots. Content and
   wording are unchanged except that the separator between an
   instrument and its state is now a middle dot rather than an em
   dash, which the house style forbids. The middle dot was already the
   separator in the header line.

## 2. Reduced motion

`prefers-reduced-motion: reduce` is read once at init through
`matchMedia`. Under it the orbs are flat discs with their rims and no
breathing, and the edges are the static strokes with no particles.
Everything else, including every honesty line, renders identically.

## 3. Honesty lines at rest

The footer block-replay line, the window count, the edge rule, the
health lamps, the per-card composition line, the awaiting-data markers
and the no-data-in-this-window note all render in the resting view.
None of them moved behind interaction.

## 4. The three audience gaps

1. Share embed. Both pages carry og:type, og:site_name, og:title,
   og:description, og:url, og:image with dimensions, and the twitter
   summary_large_image card. The description is the live banner
   sentence followed by a standing sentence, injected at build time and
   worded without numerals. The image is `share.png` at an absolute
   URL.
2. Legend overlay. A small button at the bottom right of the stage
   opens a frosted panel with five lines: what a node is, what colour
   means, what an edge percentage means, what breathing means, and one
   line on the gates linking to the record. Words only, no numerals,
   dismissed by tapping outside.
3. Changed since last bulletin. `publish` now also writes
   `state/prev_states.json`, the published month's state map. The next
   build reads it and injects one line under the banner naming the
   instruments whose state moved, in words with no numerals, or "no
   state changes". It is page only: it never enters the payload, the
   payload builder or the bulletin. This month it reads no state
   changes, which is correct, because the published month and the
   built month are the same.

## 5. Record page

Surface, ink, dim, faint and line tokens now match the stage, with a
static background vignette and a three-pixel glow on the legend lamp
dots. There is no motion of any kind. The family colour variables are
deliberately untouched, so the strip rows render exactly as before,
and the sections, notes and wording are unchanged.

## 6. Payload identity

`state/site_data.json` is byte-identical before and after an identical
month run, confirmed by `git diff --quiet HEAD -- state/site_data.json`
returning clean after every rebuild in this branch. No decoder, gate,
check, chain entry or bulletin text was touched. The chain stands at
one hundred and thirty-seven entries, head `d91eee75311cc0ce`,
unchanged by this work.

## 7. Smoke passes

`tests/js_smoke.mjs` stubs `matchMedia` and runs each page twice, once
with reduced motion off and once on, with the canvas 2d methods stubbed
as no-ops. Final run:

1. `node tests/js_smoke.mjs index.html` OK, both motion passes.
2. `node tests/js_smoke.mjs report.html` OK, both motion passes.
3. `python3 -m pytest tests/ -q` 23 passed.

## 8. Frame time

Measured in Chrome on this M-class laptop at viewport 1280 by 527,
device pixel ratio capped at two, thirty-seven edges and two hundred
particles, over three hundred consecutive draws with the first fifty
discarded:

1. mean 0.122 ms
2. median 0.100 ms
3. p95 0.200 ms
4. max 0.600 ms

Against a target of under three milliseconds per frame. The
requestAnimationFrame loop skips drawing entirely while
`document.hidden` is true. The temporary sample used to take this
measurement was removed from the template before merge.

## 9. Screenshots

1. `reports/screenshots/launch_stage.png`, the deployed stage at LIVE
   with the banner and the since-last-bulletin line.
2. `reports/screenshots/launch_record_scorecard.png`, the deployed
   record page at the head of the scorecard.
3. `share.png`, the share card, regenerated at 1200 by 630 from the
   deployed page.

## 10. Limitations

1. The proportional particle allocation above the four hundred ceiling
   is implemented but never exercised by current data, whose busiest
   frame allocates two hundred and forty-two.
2. `share.png` is a static render committed to the repository. It does
   not follow the live banner and needs regenerating whenever the
   weather word changes.
