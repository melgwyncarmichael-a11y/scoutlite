# ScoutLite Evaluation Report

**PE6201 — Player Research Brief Tool.** Compiled 2026-09-16. Covers the three eval tracks
run against ScoutLite's pipeline, mapped to the Technical Vision doc's §6 eval items
(B1–B7 in `TESTS.md`).

## Executive summary

Three things in ScoutLite can go wrong in ways no unit test catches: the deterministic Quality
signal can be *technically correct but misleading*, the LLM-written sections can hallucinate
or hype, and the LLM's Fit signal can be inconsistent. Each got its own eval track. All three
surfaced real, fixable problems — **5 bugs found and fixed as a direct result of running these
evals**, not from writing more unit tests in the abstract:

| Track | Question | Headline result |
|---|---|---|
| **A** — Quality signal validity | Does the 1–5 number mean what it claims? | 67% → **80% exact match** on position grouping after a fix, verified against real data; 9 → 8 of 13 flagged surprising on face-validity, one resolved by a bug fix, two more (Rice, Rodri) now backed by a genuinely broader metric set |
| **B** — Hallucination / hype | Does the LLM invent facts or oversell real ones? | **50% recall** on hype, **7% false-positive** rate — small sample, matches the design hypothesis |
| **C** — Fit-signal consistency | Does the same input ever give a different Fit score? | Stable within every case — but **21 of 21 runs landed on the same score (3/5)**, exposing a scope limitation, not just confirming stability |

The pattern across all three: the deterministic and LLM-written parts of ScoutLite are mostly
behaving *honestly* — refusing to guess, disclosing uncertainty, hedging when data is thin —
but that honesty exposed real gaps in what the underlying data can actually support, in two
different signals independently.

## Method

Each track has its own capture/build/score tooling under `eval/` (full documentation in
`eval/README.md`), following the same shape throughout: a script captures real pipeline output
into JSON, a builder turns it into a CSV with the tedious parts (sentence splitting, cross-
referencing, context) pre-filled, a human labels the judgment columns, and a scorer computes
the actual numbers from those labels. All scoring logic is pure and unit-tested independent of
whether real labeling has happened yet — the suite is **113 tests** as of this report.

---

## Track A — Quality Signal Validity

*(Full detail: `NOTES.md`, entries "Track A scaffolded" and "Track C: a real scope
limitation"; raw data in `eval/track_a_position_survey.csv` and
`eval/track_a_quality_spotcheck.csv`.)*

### A1 — Position-group survey (completes `TESTS.md` B5)

15 players, checking whether `classify_position_group()`'s real-world output holds up.
**67% exact match** to the labeler's own first-guess role, **87% called defensible anyway**
(13 of 15) — most of the gap is a coarse-but-honest simplification (an AM classified as
Attack: *"a number 10 is in the middle between attack and midfield... makes sense"*).

The 2 rows called **not** defensible are the real finding: Declan Rice and Rodri, both listed
`DF-MF (CM-DM)`, both land in Defense — while **Casemiro**, the same defensive-midfielder role
with the same `(CM-DM)` tag, correctly lands in Midfield, purely because FBref didn't prefix
him with `DF-`. Same job, two different buckets, by coincidence of which code FBref lists
first. Not a blunt simplification — a real inconsistency.

### A2 — Quality face-validity spot check ("the Ronaldo test," completes B3)

13 players scored, reputation tier picked blind before the score. **9 of 13 originally flagged
surprising**, breaking into three distinct, explainable patterns:

1. **Averaging dilutes a specialist's peak trait.** Haaland: `goals 100th %ile, xG 99th %ile`
   but `assists 56th, xA 53rd` — averaged to 77, just under the cutoff for 5/5, landing at 4/5
   despite being literally top-of-population on the two metrics that define a pure striker.
2. **Position misclassification directly breaks the signal** for Rodri and Trent
   Alexander-Arnold — both bucketed Defense (see A1), so their *entire* score is one
   `defensive_actions_per90` percentile (48th and 50th respectively). Neither player's actual
   defining trait is measured at all.
3. **A real bug — found and fixed.** Mbappé's four components all came back at exactly
   `50.0%`, the code's hardcoded empty-population fallback, not four real percentiles. His
   season was only 4 games in; essentially no player league-wide had cleared the 450-minute
   floor yet, so the reference population was genuinely empty, and the signal silently
   rendered a normal-looking `3/5` that measured nothing. **Fixed in `scoring.py`**: a
   component is only averaged in when its population is non-empty; an entirely-empty
   population now correctly returns "not available" instead of fabricating a score. Re-run
   against live data post-fix: **5/5**, `avg_percentile 85.7`, matching the "World's Elite"
   tier the labeler picked before ever seeing the buggy number. Final surprising count after
   the fix: **8 of 13**.

---

## Track B — Hallucination / Hype

*(Full detail: `NOTES.md`, entries "Track B labeled and scored for real" and the bug-fix
entries before it; raw data in `eval/track_b_labels.csv`.)*

70 sentences across 14 real generated briefs, every sentence from the two LLM-written sections
("What People Say," "Signals & Fit Read") — the only place hallucination or hype could happen,
since everything else in a brief is rendered straight from data.

**Result: 50% recall on hype (1 of 2 real cases), 7% false-positive rate (5 of 68 grounded
sentences the judge flagged anyway).** Small sample, but it lands exactly on the hypothesis
this eval was designed to test — the rule-based judge catches factual overreach reasonably
well (misreading a stat with too much confidence) and is weaker at catching plain narrative
hype dressed as an ordinary sentence, since that's tonal, not something a grounding regex can
see.

Getting a trustworthy number required real work, not just running a script:

- **Two regex bugs found and fixed**, both via real generated briefs, not synthetic edge
  cases: a bare apostrophe was misread as an opening quote (turning a possessive like
  "Ødegaard's resurgence" into a fake invented-quote finding spanning most of a paragraph);
  separately, trivially short real quotes ("found," "decision time") were skipped by a length
  floor before pairing, leaving their marks to combine with each other and manufacture a fake
  quote out of real prose. Both caused two real briefs to score 20–65% instead of 90%+ for
  reasons that had nothing to do with actual hallucination. Fixed, verified against the exact
  briefs that surfaced them, 3 regression tests added directly from that real data.
- **A genuine judge-vs-human disagreement, traced to the exact sentence.** The labeler's first
  pick for Haaland's one real exaggeration and the judge's own findings pointed at three
  different sentences in the same brief. Tracing each finding's quoted text back to its source
  sentence made the disagreement concrete: the judge over-flagged two fine, honestly-hedged
  sentences and missed the real one — exactly the kind of specific, checkable result this eval
  exists to produce instead of a vague "seems fine" impression.
- **Two scorer bugs found from the labeling process itself.** The labeler answered in full
  sentences ("Yes, same role, I think it's correct") rather than bare y/n; an exact-string
  match silently read every one of those as false, reporting a fabricated 0% on one metric and
  a fabricated 100% on another before being caught and fixed.

---

## Track C — Fit-Signal Consistency

*(Full report: `eval/TRACK_C_REPORT.md`; raw data in `eval/track_c_samples/`.)*

7 players, all 6 possible club-philosophy combinations, 3 runs each — 21 runs total, same
inputs held fixed per case, only the LLM call allowed to vary.

**Within-case stability: confirmed.** Every run in every case matched every other run in that
case; only the prose wording drifted, as designed.

**Across cases: the real finding. All 21 runs — every case, every philosophy combination —
landed on `fit_score: 3`.** Not from repeated boilerplate; each brief cites different real
stats and reaches 3 by a different path. One case (Trent Alexander-Arnold) was deliberately
chosen as an on-paper mismatch — a fullback known for attacking output tested against a
high-line, counter-pressing philosophy that specifically punishes that profile — and it still
landed on 3, naming the reason directly: *"There is no pace or sprint data listed, so the
speed-dependent transition fit central to this club's philosophy cannot be assessed at all."*

**Read plainly: this is a scope limitation, not a bug.** ScoutLite's two data sources (FBref
counting stats, Understat xG) never carry pace, sprint, or pressing-volume data — precisely
what club-philosophy fit depends on. The model is instructed to, and does, refuse to guess
rather than fabricate confidence. The consequence is that **the Fit signal may be structurally
unable to move off neutral for any player against any philosophy**, given today's inputs. The
fix isn't more reruns — it's either sourcing that data from somewhere, or being explicit in the
product that Fit is close to fixed-neutral until it does.

**Resolved, 2026-09-17 (v3 — see `NOTES.md`, "v3: both Signals fully deterministic").** Fit is
no longer an LLM-judged number at all. `compute_fit_signal()` computes it deterministically —
comparing the player's own percentile profile against a real reference club's current squad in
the same position group — the same architecture Quality already used. This doesn't source the
missing pace/pressing data (that gap is real and stays disclosed in every brief), but it does
fix the actual symptom this track found: the signal now varies meaningfully with real
statistical differences instead of defaulting to a fixed 3/5 regardless of input. The remaining
open question is whether profile-similarity is the *right* thing to measure, not whether the
number moves — that's a separate, ongoing judgment call, not a re-run of this track.

**Track C's own tooling reworked, 2026-09-18 (see `NOTES.md`).** The v3 change above never
touched `eval/track_b_capture.py`/`track_c_repeat.py`/`score_track_c.py` themselves — they
still built around the now-nonexistent `fit_score` key and would have crashed on any
philosophy-set capture. Fixed mechanically (they now read/report `fit_signal`), and reframed
conceptually: a deterministic label's cross-run consistency is guaranteed by construction, so
Track C now instead checks whether the LLM's *prose* ever misrepresents the fixed label across
reruns — closer to a Track-B-style hallucination check than the original question. A live
2-run smoke test of the reworked tooling caught bug #6 below.

**New: Track C2 — Fit label calibration, 2026-09-18 (full report: `eval/TRACK_C2_REPORT.md`).**
Neither Track C's original nor reworked version ever checked whether the 15/35 percentile-point
cutoffs behind the Fit labels (`scoring.FIT_LABELS`) actually mean anything — they were a
first-pass guess, disclosed as such in `scoring.py`'s own comment. 9 hand-picked cases (6
players tested against the reference club they actually play for, expecting Hand-in-Glove; 3
players tested against a deliberately mismatched philosophy, expecting Completely Different)
came back only 2/9 matching that a-priori expectation — but the *why* is more useful than the
score: (1) the defense position group has only one shared metric, so its `avg_abs_diff` gets
none of the smoothing multi-metric groups (attack, midfield) get from averaging, making it
structurally more volatile, not mistuned; (2) a genuine standout player (Haaland, Kimmich)
reliably shows a real, correctly-computed gap from his own squad's *positional average* —
because that average includes weaker rotation players — which means "self-reference should
read Hand-in-Glove" was too strong an assumption for exactly the players most worth testing it
on, and the 15-point cutoff (two multi-metric self-reference cases landed at 16.0 and 17.1,
just past it) was plausibly set too tight. One case (Casemiro vs. Bayern, `avg_abs_diff` 47.9)
confirms the mechanism does work correctly when a real, large, multi-dimensional stylistic gap
exists. **Applied, 2026-09-18:** the Hand-in-Glove cutoff was raised from 15 to 20 in
`scoring.FIT_LABELS`. Re-running the same 9 cases against the new threshold: 4/9 now match
their expected label, up from 2/9 — at the cost of one case (Rúben Dias vs. Dortmund) moving
further from its expected label, the predicted tradeoff of a defense-group case sitting in the
same 16-17 band the fix was raised to catch. Defense's own volatility (Finding 1) was
deliberately left untouched, since it needs a second metric, not a different cutoff.

---

## Cross-cutting themes

Two patterns showed up independently in different tracks, which makes them more convincing
than either alone:

- **Role/position ambiguity keeps causing real problems.** Rodri appears as a genuine finding
  in *both* A1 (misclassified into Defense) and A2 (his Quality score is consequently just one
  narrow defensive metric) — the same underlying issue, discovered twice from different
  angles.
- **"The model is honest, but the data can't support the question" is the dominant failure
  mode.** Mbappé's fabricated score (A2) and the Fit signal's fixed-neutral ceiling (C) are the
  same shape of problem in two different signals: a genuine data-availability gap that the
  code either papered over (A2, now fixed) or that the model correctly disclosed instead of
  guessing (C, now documented as a real limitation rather than assumed to be fine).
- **Running the eval was the actual bug-finding mechanism.** All 5 fixed bugs (2 in the judge's
  quote regex, 2 in scoring against real labeled data, 1 in the Quality signal's population
  handling) were found by generating and reading real output, not by imagining edge cases up
  front. The existing 113-test pytest suite catches regressions once a bug is known, but none
  of these 5 were caught by tests written *before* the eval surfaced them — worth remembering
  as a reason to keep running real cases through the pipeline, not just adding more unit tests
  in isolation.

## Bugs found and fixed, across all three tracks

| # | Bug | Found via | Fixed in |
|---|---|---|---|
| 1 | Apostrophe misread as an opening quote → fake invented-quote finding | Track B, real brief (Declan Rice) | `judge_rules.py` |
| 2 | Short real quotes skipped, marks recombine into a fake quote | Track B, real brief (Virgil van Dijk) | `judge_rules.py` |
| 3 | Empty reference population silently fabricates a neutral score | Track A2, real capture (Kylian Mbappé) | `scoring.py` |
| 4 | Full-sentence labels silently read as false by an exact-match check | Track A/B, real labeling | `score_track_a.py`, `score_track_b.py` |
| 5 | Free-text `human_label` values not matched to their category | Track B, real labeling | `score_track_b.py` |
| 6 | Fit explanation fabricated "the scout's own role notes" when none were given | Track C, reworked tooling smoke test (Erling Haaland) | `scoutlite_combined.py`, `judge_rules.py` |

## Recommendations

**Done (2026-09-17 — see `NOTES.md`, "Post-eval v2"):**

1. ~~Revisit `classify_position_group()`~~ — fixed. `DF-MF` with a `CM`/`DM` secondary tag now
   classifies Midfield; genuine fullbacks (`FB`/`CB`/`WB`) are unaffected. Verified against all
   15 real Track A captures: exact-match rate **67% → 80%**.
2. ~~Caveat the Quality signal's averaging~~ — done. A new `specialist_caveat` fires when a
   player's components spread more than 40 percentile points, naming the risk explicitly
   instead of silently flattening a specialist's peak trait.
3. ~~Be explicit about the Fit signal's ceiling~~ — done. Every brief with a philosophy
   assessed now carries a fixed disclosure (`docx_report.FIT_SCOPE_CAVEAT`) that Fit can't see
   pace/sprint/pressing data.

**Also done (2026-09-17, same day — re-ran the eval set against v2 rather than leave it as an
assumption that the fixes worked):**

5. ~~Re-run A1/A2 after fix #1~~ — done, selectively. Re-checked Track B's 14 existing captures
   against the new hype regex (no new API calls needed, since the fix changes what the judge
   flags, not the brief text) — zero rule-based findings changed; the one real "overstated"
   miss from labeling doesn't contain any of the new keywords, so this fix wouldn't have caught
   it specifically (honest result, not a failure — confirms hype detection still needs the LLM
   supplement for subtler cases). Refreshed Track A1's `assigned_group` for all 15 captures:
   **exact-match rate 67% → 80%**, Rice and Rodri no longer mismatches. Re-captured Rice and
   Rodri for Track A2 (the only two whose position group actually changed, so their Quality
   score is now a genuinely different computation, not just a relabel): **Rodri 3/5 → 4/5**
   (avg percentile 48.3 → 63.1, now including his 70th-percentile key-passing output — directly
   answering the labeler's own note, "defense isn't the only thing... city do have a lot of the
   ball"); Rice stayed 4/5 but now backed by three dimensions of his game instead of one.
   Track C's full 21-run sweep was deliberately *not* re-run — none of the 4 fixes touch the
   LLM synthesis prompt or the Fit-score computation, so re-running would spend real API cost
   to almost certainly reproduce the same result. `reputation_tier`/`surprising` for Rice and
   Rodri were deliberately left for the labeler to reconsider given the metric set genuinely
   changed, not silently flipped — see `NOTES.md` for the full writeup.

**Also done, v3 (2026-09-17 — see `NOTES.md`, "v3: both Signals fully deterministic"):**

6. ~~Should Fit stay numeric~~ — resolved differently than either option originally posed: not
   a caveat on an LLM-judged number, and not dropping the number, but making the number itself
   deterministic. Fit is now a 3-tier label (Hand-in-Glove Fit / Somewhat Fits / Completely
   Different) computed by comparing the player's percentile profile against a real reference
   club's current squad — see the Track C section above for the full resolution.
8. ~~A genuinely different Quality scoring approach~~ — possession-adjustment (PAdj), not a
   standout-metric redesign, but addresses the same underlying complaint (a single blended
   number hiding real context): Quality now shows both a raw and a possession-adjusted
   percentile, correcting for a dominant-possession team's players facing fewer defensive
   opportunities. Verified live: Rodri's defensive-actions percentile moved 57 (raw) → 88
   (adjusted).

**Still open, left for the project owner's call:**

4. **Grow the Track B sample.** 2 real "overstated" cases is enough to match the hypothesis
   directionally, not enough to trust the 50% recall number as a stable rate — more labeled
   captures would tighten it. A small hype-keyword detector was added to `judge_rules.py`
   alongside the Tier-1 fixes to raise the floor on the most blatant cases, but it doesn't
   replace growing the sample to actually measure recall with confidence.
7. **Is sourcing pace/pressing data worth pursuing** at all, given ScoutLite's free/scraping-
   only sources? Likely a dead end, worth a quick access-check rather than an assumption. Both
   Quality's PAdj and Fit's reference-club redesign still can't see this data — it's the one
   gap no amount of restructuring the existing sources closes.
10. **Fit's 3-tier thresholds (15 / 35 percentile-point average difference) are a first pass,
    not eval-validated** — no labeled sample exists yet for this new mechanism, the same
    position Fit itself was in before Track C. A natural next eval track, not urgent.
9. **Keep the "run real cases, read real output" habit going.** Every bug in this report — and
   the position-classification fix above — was found that way, not by imagining edge cases up
   front. Cheap relative to what it catches.

## Supporting documents

- `NOTES.md` — full chronological build log, including every bug's discovery and fix in detail
- `TESTS.md` — the original system test matrix and B1–B7 eval item tracking
- `eval/README.md` — tooling documentation and workflow for all three tracks
- `eval/TRACK_C_REPORT.md` — standalone Track C report with the full 7-case results table
- `eval/track_a_position_survey.csv`, `eval/track_a_quality_spotcheck.csv`,
  `eval/track_b_labels.csv` — raw labeled data behind every number in this report
- `tests/` — 113 automated tests covering the pure/deterministic layers referenced throughout
