# ScoutLite — Product Documentation

Companion to the code repo, per the PE6201 end-of-course checklist: persona, input, output,
high-level architecture, and metrics targeted vs. reached — in one place rather than scattered
across the other docs. This is a reference document, not the report — it states what the
product is and does; the reasoning, critique, and reflection live in the written report.

For depth beyond what's summarized here: `README.md` (usage), `NOTES.md` (full build log),
`EVAL_REPORT.md` + `eval/README.md` (eval methodology and results), `STATUS.md` (current state
snapshot), `FIT_SIGNAL_REFERENCE.md` (Fit label reference).

## Persona

**A football scout doing early-stage player research** — identification and shortlisting,
specifically (the first two stages of the standard four-stage scouting pipeline: identification
→ shortlisting → deep evaluation → reporting; see `TECHNICAL_VISION.md` §4a). Concretely:

- Needs a **consistent, standardized summary** for any player-season — well-known or obscure —
  rather than hunting across FBref, Understat, and news sites separately for each one.
- Wants **data as an additional input to their own judgment**, not a tool that tells them who to
  sign. ScoutLite explicitly never ranks, recommends, or reaches a verdict — every output is
  called a "research brief," never a "scouting report" or "report card." The judgment,
  interpretation, and final call stay entirely with the scout.
- Is comparing a specific player against a **specific tactical system** (their club's or a
  target club's playing style), not just asking "is this player good" in the abstract — hence
  the Fit signal against a real reference club, not just the Quality signal alone.
- Still does deep evaluation (video, live scouting) themselves — ScoutLite accelerates the
  research step that precedes that, it doesn't replace it.

## Input

| Field | Required? | Notes |
|---|---|---|
| Player name | Yes | Resolved against FBref; ambiguous names (e.g. "Bruno Fernandes," 11 real matches) surface a candidate table for explicit confirmation rather than guessing |
| Season | Yes | Picked from the seasons that actually exist on that player's real FBref page |
| Role notes | No (free text, capped at 200 chars) | Adjective-style, e.g. *"tall, can play as a 9 or 10, gets in behind often"* — captures **role**, which stats alone can't (see Persona); included as the scout's own observation, not treated as verified data |
| Club philosophy | No (two linked dropdowns) | In-possession (vertical/fast transitions vs. slow/methodical possession) × out-of-possession (high line/counter-press vs. mid block vs. low block/counter) → one of 6 fixed combinations, each tied to a real reference club (e.g. Manchester City for possession + high line) |

Available via the Streamlit app (`app.py`, recommended) or two CLIs (`scoutlite_combined.py` for
one player, `scoutlite_compare.py` for 2+ candidates side by side).

## Output

A **Word document (.docx)** — a player research brief, not a scouting report or verdict:

1. **Signals** (top) — Quality (1–5 label, e.g. "World Class") and Fit (3-tier label, e.g.
   "Hand-in-Glove Fit" vs. a named reference club), plus a verified-confidence score (e.g. "92%
   verified") shown on every brief
2. **Who He Is** — bio, background, club history
3. **Stats & Performance** — season stats, position-grouped, tables for defense/discipline and
   goalkeeping where applicable
4. **What People Say** — a synthesized read of recent news (last 28 days), every headline a real
   hyperlink to its article
5. **Signals & Fit Read** — the Quality/Fit signals explained in plain English alongside the
   evidence that produced them
6. **Sources** — links back to the exact FBref and Understat profiles the stats came from

The Streamlit app shows the same content inline before download, plus a candidate-disambiguation
table and live signal computation as each stage completes.

## High-level architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ INPUT (Streamlit app.py / CLI scoutlite_combined.py, scoutlite_compare.py)│
│ Player name · Season · Role notes (free text) · Club philosophy          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TOOLS — Deterministic data gathering                                     │
│ FBref scraper (scoutlite.py) · Understat scraper (understat_xg.py) ·     │
│ NewsAPI (news_fetch.py) · SQLite cache (cache.py, fails soft on error)   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TOOLS — Deterministic signals (scoring.py) — zero LLM involvement        │
│ Quality: 1–5 percentile label   │   Fit: 3-tier reference-club label     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL INTELLIGENCE — LLM synthesis (DeepSeek-V3, one call, llm_client)│
│ Writes "What People Say" + "Signals & Fit Read" prose only — never       │
│ decides the Quality/Fit numbers themselves                               │
└──────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TOOLS + EXTERNAL INTELLIGENCE — Judge loop                               │
│ judge_rules.py (deterministic: numeric grounding, quote-matching,        │
│ forbidden verdict/hype/transfer-value language) +                        │
│ judge_llm.py (narrow LLM fact-check: fair interpretation?) →             │
│ revise up to 2 passes; ship either way with a visible confidence score   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ OUTPUT — docx_report.py                                                  │
│ Word document (.docx): Signals · Who He Is · Stats & Performance ·       │
│ What People Say · Signals & Fit Read · Sources                          │
└────────────────────────────────────────────────────────────────────────┘
```

All three entry points (`app.py`, `scoutlite_combined.py`, `scoutlite_compare.py`) call the same
underlying `research_player()` function — one pipeline, three ways in.

## Metrics targeted vs. reached

Evaluated across 5 eval tracks (`eval/README.md`, `EVAL_REPORT.md`); numbers below are the real,
labeled results, not estimates. ✅ = target met, ⚠️ = partially met / honest gap disclosed, ❌ =
target not yet reached.

| What was targeted | Track | Metric reached | |
|---|---|---|---|
| Quality signal's position grouping matches real-world role | A1 | 80% exact match (up from 67% after a fix), 87% called defensible even where not exact | ✅ |
| Quality score passes face-validity ("the Ronaldo test") | A2 | 8 of 13 flagged surprising on first pass, all 3 root causes explained (metric averaging, position misclassification, one real bug — found and fixed) | ⚠️ |
| Fit signal doesn't flip run-to-run for the same input | C | 21/21 runs stable within-case | ✅ |
| Fit signal actually discriminates between players | C (pre-v3) | 21/21 runs landed on the same neutral score regardless of input — a real scope limitation (no pace/pressing data in any source), not a bug; fixed architecturally in v3 (deterministic percentile comparison, no longer LLM-judged) | ❌ → addressed by redesign |
| Fit label thresholds (15/35 percentile points) are calibrated, not guessed | C2 | Hand-in-Glove cutoff raised 15→20 on real evidence; match rate against a-priori expected labels improved 2/9 → 4/9. Upper cutoff (35) still unvalidated | ⚠️ |
| Fit label validated against independent, blind human judgment (not self-graded) | C3 | 4/10 matched; every mismatch traced to one diagnosed root cause (output-rate vs. playing style), not scattered noise. Triangulated same-day against a fresh, tool-blind LLM (agreed with the human 6/10, with the tool 3/10) | ⚠️ |
| Judge doesn't let the LLM hallucinate or oversell | B | 50% recall on hype/overstatement, 7% false-positive rate on honestly-written sentences (small sample — 2 real positive cases) | ⚠️ |
| Judge's 80% pass/revise threshold is itself calibrated against human judgment | — | Protocol written (`NOTES.md`), never run — disclosed as open, not claimed done | ❌ |
| Automated regression coverage on the deterministic layer | — | 237 tests passing (percentile math, position classification, judge rules, name-matching, cache TTL, prompt assembly, HTML extraction) | ✅ |
| Real bugs caught and fixed via evals/live testing, not just imagined upfront | all | 9 distinct bugs found this way across the build (quote-regex false positives, empty-population fallback, label-matching mismatches, 2 live-tested UI bugs, and others — see `EVAL_REPORT.md` and `NOTES.md`) | ✅ |

The honest pattern across the ⚠️/❌ rows: ScoutLite's deterministic and LLM-written components
are mostly behaving correctly and disclosing uncertainty rather than guessing — the recurring
gap is data availability (no pace/pressing/tactical-role data in any free source), not faulty
logic, and every instance of that gap is named explicitly in the product rather than hidden.
