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

### Finding 3 — CLI vs UI error handling differs
`scoutlite_combined.py`'s `main()` isn't wrapped in try/except, so any exception (not-found
player, transient FBref flakiness) surfaces as a raw traceback on the CLI. The actual product
surface (`app.py`) already handles this cleanly — confirmed side-by-side on the same garbage
input. Not user-facing, but worth fixing for anyone using the CLI directly. **Not yet fixed.**

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

## Not yet built
- LLM judge loop (structure/source-matching check, 2-iteration cap, 80% threshold)
- Position-grouped scoring's own eval harness beyond the spot checks above
