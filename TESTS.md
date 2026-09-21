# ScoutLite — Test Plan & Results

Companion to `NOTES.md` (which has the narrative build log — bugs found, access decisions,
reasoning). This file tracks the test matrix itself: what's been run, what passed, what's
still open. Built on the Technical Vision doc's Section 6 (Evals) and Section 7 (Manual test
plan), made concrete with real players and real results.

## System test cases — run 2026-09-08

11 of 12 succeeded; 1 (garbage name) correctly failed with no brief produced, as designed.

| # | Player | Season | Case being tested | Result |
|---|---|---|---|---|
| 1 | Erling Haaland | current | Elite attacker, baseline happy path | ✅ Pass. Bonus: current season was only 3 matches in — thin-data case covered for free, no crash |
| 2 | Kevin De Bruyne | current | Versatile position, known misclassification | ✅ Confirmed — still lands in **Attack** (FBref lists FW first), unchanged from earlier finding |
| 3 | Virgil van Dijk | 2023-2024 | Context confound (dominant-possession team) | ✅ Confirmed — Quality 2/5, identical to prior run |
| 4 | David Raya | 2023-2024 | Goalkeeper, full season (earlier test used a 1-match sample) | ✅ Pass — 65.2% save rate → 3/5 |
| 5 | Aaron Wan-Bissaka | 2023-2024 | "Average" squad-level profile | ⚠️ Scored 5/5, not average — see Finding 1 below |
| 6 | Macaulay Langstaff | current | Non-covered league (League Two) | ✅ Pass — Quality and xG/xA both cleanly "not available," FBref stats still populate |
| 7 | Danny Ward | current | Ambiguous common name | ✅ Confirmed — resolves to the same League One player as the original test |
| 8 | Kylian Mbappé | current | Compound surname (previously-fixed bug) | ✅ Regression pass — matched-name warning shows "Kylian Mbappe-Lottin" |
| 9 | "Vinicius Jr" | — | Known abbreviation-mismatch limitation | ⚠️ Fails earlier than documented — see Finding 2 below |
| 9b | "Vinicius Junior" (full word) | current | Isolation check for #9 | ✅ Pass — resolves cleanly end-to-end, confirms it's specifically the abbreviation |
| 10 | Trent Alexander-Arnold | current | Genuinely hyphenated, correct name | ✅ Pass — resolves cleanly; correctly ignored an unrelated "next Trent" headline about a different player |
| 11 | Declan Rice | 2023-2024 | Second versatile-position case | ✅ Confirmed — still lands in **Defense**, unchanged from earlier finding |
| 12 | "Zxqvblorp Nonexistentplayer" | — | Garbage input / fails-visibly check | ✅ Pass on the UI (clean "Something went wrong" message) — ⚠️ raw Python traceback on the CLI, see Finding 3 |

### Finding 1 — Wan-Bissaka's 5/5 is not a bug
Real-world Wan-Bissaka is genuinely elite specifically by the interceptions+tackles/90 metric —
this isn't a miscalibration, it's the same "narrow metric ≠ holistic quality" limitation as
Van Dijk's low score, just cutting the opposite direction. A scout weighing this signal should
know a high score here means "excels at defensive actions specifically," not "great all-round
defender."

### Finding 2 — abbreviation-mismatch is broader than previously documented
Previously written up as an Understat-only issue. Testing now shows **FBref's own search fails
on "Vinicius Jr" too** (confirmed reproducible via a retry, not transient), isolated by
confirming "Vinicius Junior" resolves cleanly through the whole pipeline. This means an
abbreviated name can block a brief from being generated at all, not just degrade the xG/xA
section as originally thought.

### Finding 3 — CLI vs UI error handling differs (fixed 2026-09-08)
`scoutlite_combined.py`'s `main()` wasn't wrapped in try/except, so any exception (not-found
player, transient FBref flakiness) surfaced as a raw traceback on the CLI. The actual product
surface (`app.py`) already handled this cleanly — confirmed side-by-side on the same garbage
input. **Fixed:** pipeline logic moved into a `run(args)` function, called from `main()` inside
a try/except that prints `Error: <message>` and exits with status 1, instead of a traceback.
Re-verified on the same garbage-name case (clean one-line error, exit code 1) and on a normal
run (Haaland, exit code 0, unaffected) to confirm no regression from the refactor.

## Report-content evals (Technical Vision doc, Section 6)

| Eval | Status | Notes |
|---|---|---|
| B1. Factuality (News/Fit sections only) | ✅ Spot-checked | No hallucinated stats found across the 11 briefs generated in this batch |
| B2. Headline attribution under ambiguity | ✅ Verified, repeatedly | Correctly discerned unrelated headlines in Trent Alexander-Arnold's ("next Trent"), Declan Rice's (Chelsea match ratings), and Kevin De Bruyne's (Inter Milan) briefs — didn't force a false connection in any of them |
| B3. Quality-vs-transfer-value spot check ("Ronaldo test") | ⬜ Not yet run | Needs manual transfer-value lookups for ~10 players |
| B4. Fit-signal consistency (same inputs, 3-5 reruns) | ⬜ Not yet run | This batch didn't set a club philosophy on any case |
| B5. Position-group accuracy rate | 🟡 Partial | 2 concrete data points so far (De Bruyne → Attack, Rice → Defense), not the full 15-20 player survey |
| B6. Time-to-brief | ⬜ Not yet measured | |
| B7. Model comparison | ⬜ Blocked | Needs the model-tiering work (Vision doc Section 5) before there's a second model to compare against |

## Judge loop (built 2026-09-10)

Re-scoped from the Vision doc: deterministic rules (`judge_rules.py`) are the bulk and compute
the 80% threshold; a narrow LLM check (`judge_llm.py`) is a small supplement for what rules
can't do (fair-interpretation, faithful news characterization, subtle misframing). Loop caps
at 2 iterations, then ships with a `confidence_warning` rather than hard-failing.

| Check | Verified how | Result |
|---|---|---|
| Rule checks — clean brief | Unit test, crafted clean paragraphs | 100%, no findings |
| Rule checks — dirty brief (fabricated numbers, `£120m`, invented headline, xG when none available, unattributed scout notes, verdict language) | Unit test | 0%, every check fired |
| Hard-fail gates (empty section, philosophy given but no fit score) | Unit test | Correctly forces `hard_fail=True` |
| Numeric grounding — false-positive control | Ran on real Haaland data | xG floats (`31.65`, `4.75`) correctly matched; "28" (news window) and headline numbers added to the known set to cut benign flags |
| LLM judge missing-headlines bug | Full run | Caught + fixed — it was concluding "no news data" and failing every news claim; now receives `articles` |
| Full CLI + UI run, normal player | Live | ~90-100% on iteration 1, PASSED, LLM surfaced genuine *minor* framing nuances (didn't block) |
| Confidence-warning rendering | Synthetic failing judge dict → `build_docx` | Bold warning at top of .docx + bulleted findings; data tables/signals unaffected |
| Persistent judge line in UI | Live | "Automated judge: 90.0% ... passed the threshold" shows near Signals |

## Report-content evals (Technical Vision doc, Section 6)

Note: B1 (factuality of the LLM-authored sections) is now partly enforced *in the pipeline* by
the judge's numeric-grounding + headline-grounding checks, not only spot-checked after.

## Not yet built
- Position-grouped scoring's own eval harness beyond the spot checks above
- Model tiering (Vision doc Section 5) — would let `judge_llm.py` use a cheaper model and
  unblock eval B7
- **A second defensive metric for the "defense" position group** (2026-09-21) — Track C2
  (`eval/TRACK_C2_REPORT.md`) found defense's Fit/Quality volatility comes from having only one
  shared stat (`defensive_actions_per90`), unlike attack/midfield's 3-4. Checked directly:
  `soccerdata`'s FBref reader only exposes 5 player-season stat types (`standard`, `shooting`,
  `playing_time`, `keeper`, `misc`) — no separate "Defensive Actions" table (blocks, clearances,
  tackles-by-third), and `misc`'s own columns (`CrdY/CrdR/Fls/Fld/Off/Crs/Int/TklW/PKwon/PKcon/OG`)
  have nothing else clean to add. Fixing this for real would mean scraping a league-wide
  defensive-actions HTML table directly (population-wide, not just the target player) — a new
  data-source integration, not a column addition. Deferred as out of scope for now.
- **Multi-season trend view** — show whether a player's Quality/Fit is trending up or down over
  the last 2-3 seasons, instead of a single-season snapshot. FBref already exposes season
  history on the same page fetched today, so the data access isn't the blocker — deferred to
  keep this round's scope to the comparison feature (below) and the Fit threshold work.
- **User-typed custom reference club for Fit** — generalize past the current 6 hardcoded
  philosophy combinations (`scoring.REFERENCE_CLUBS`) to any real club the scout names. Bigger
  lift than the fixed table: needs a name-resolution step against FBref/Understat squads
  instead of a lookup, and no eval coverage yet for arbitrary clubs the way the 6 fixed ones
  have from Track C2. Deferred for the same reason as the trend view.
