# ScoutLite — Current Status

**Snapshot date: 2026-09-23. Latest commit: `041d3f7` on `main`. 196 tests passing, working tree
clean.** Written as a standalone handoff — for full detail, the underlying docs are
`README.md` (what it does, usage), `NOTES.md` (full build log), `CHANGELOG.md` (user-facing
changes), `EVAL_REPORT.md` (eval findings), `TESTS.md` (test matrix + deferred items).

## What ScoutLite is

A PE6201 course-project tool that generates a football "player research brief" (deliberately
not a "scouting report" or "verdict") as a Word document. Pulls FBref (stats/bio), Understat
(xG/xA), and NewsAPI (headlines) into one DeepSeek-V3-assisted pipeline, with an automated
judge loop checking the AI-written sections against the source data before shipping.

## Architecture right now

A five-stage pipeline, shared by all three ways in:

1. **Entry points** — `scoutlite_combined.py` (single-player CLI), `scoutlite_compare.py`
   (multi-candidate CLI, new this week), `app.py` (Streamlit — the recommended entrypoint, but
   does not yet expose compare mode). All three call the same `research_player()` function.
2. **Data gathering** — `scoutlite.py` (FBref scrape/parse), `understat_xg.py` (xG/xA),
   `news_fetch.py` (headlines). All three read/write through `cache.py`'s shared SQLite cache:
   24h TTL for FBref/Understat (indefinite once a season is provably historical), 4h for news
   (added this week specifically to protect NewsAPI's 100/day free-tier cap).
3. **Deterministic signals** — `scoring.py`. Both **Quality** (1-5 label, e.g. "World Class")
   and **Fit** (3-tier label, e.g. "Hand-in-Glove Fit" vs. a real reference club) are pure
   percentile math against real player populations — no LLM involved in either number, only in
   the prose explaining them.
4. **LLM synthesis + judge** — one DeepSeek-V3 call writes two short paragraphs (a news read,
   and an explanation of the pre-computed Fit label); `judge_rules.py` (deterministic checks:
   numeric grounding, quote fidelity, forbidden hype/verdict language, honesty gates) plus
   `judge_llm.py` (narrow LLM fact-check for unfair interpretation) validate them, revising up
   to 2 passes before shipping with a visible confidence warning if still below 80%.
5. **Output** — `docx_report.py`. `build_docx()` for one player, `build_comparison_docx()` for
   a shortlist (summary table + full per-candidate detail + one shared signal glossary).

Shared infra: `llm_client.py` (one lazy DeepSeek client singleton, not one per call).

## What changed this week (chronological)

1. **v3 — both signals made fully deterministic.** Fit used to be an LLM-judged 1-5 score;
   eval found it landed on exactly 3/5 in 21/21 test runs regardless of input. Replaced with a
   real percentile-profile comparison against 6 hardcoded reference clubs (one per
   in-possession × out-of-possession philosophy combo). Quality gained possession-adjustment
   (PAdj) so a dominant-possession team's defender isn't penalized for facing fewer defensive
   actions. Added a standing "Understanding the Signals" glossary to every brief.
2. **Track C reworked, Track C2 added.** The old Track C (does the LLM-judged Fit score ever
   flip) became meaningless once Fit was deterministic — reframed to check whether the LLM's
   *prose* ever misrepresents a fixed label. New Track C2 validated the Fit label's 15/35
   percentile-point thresholds against 9 hand-picked cases; found the Hand-in-Glove cutoff was
   too strict (two genuine standout players missed it by 1-2 points) and raised it from 15 to
   20 — re-tested, match rate went from 2/9 to 4/9.
3. **Two real judge_llm.py bugs fixed**, both found by reading actual generated-brief output,
   not by inspection: (a) the fact-checker's own copy of the Fit comparison data was missing
   the "in this position" qualifier the synthesis model was given, making an accurate
   positional comparison look team-wide and get flagged as an overreach; (b) the fact-checker
   never received the scout's own typed-in notes at all, so a correct attribution of them got
   flagged as a fabricated source.
4. **Multi-candidate comparison built** (`scoutlite_compare.py` + `build_comparison_docx()`).
   Refactored `research_player()` out of the CLI's `run()` so every entrypoint shares one
   pipeline implementation instead of three.
5. **Full dependency/architecture audit run**, two confirmed-real Red-tier bugs fixed:
   - `scoutlite.py` had a dead legacy CLI path calling a function that no longer existed
     (`NameError` on any invocation, zero test coverage, silently broken).
   - `cache.py`'s shared SQLite connection had no thread-safety guard — a real, reproduced
     crash risk under Streamlit's multi-threaded reruns (`check_same_thread=False` fixed it).
   Plus four Yellow-tier fixes: pinned all dependencies (`requirements.txt` + a full
   `requirements-lock.txt`), collapsed `build_docx()`'s 16-parameter signature into one cohesive
   dict, made two silent `except Exception` fallbacks in the Fit/Quality PAdj math visible via
   `warnings.warn()` instead of masking real bugs as data gaps, and consolidated three separate
   `OpenAI(...)` client instantiations into one shared singleton.
6. **NewsAPI caching + compare-mode dedup.** NewsAPI was never cached at all (unlike
   FBref/Understat) and `scoutlite_compare.py` didn't dedupe its candidate list — both fixed
   after being asked directly whether repeated player pulls could cause a real problem.

Every fix above was verified against the live pipeline, not just the test suite — this
project's running principle has been "eval/verify by running real cases, not imagining edge
cases," and every bug found this week was actually caught that way.

## What's still open (known, not yet done)

- **Fit's upper cutoff (35 → "Completely Different") is still unvalidated** — only the lower
  cutoff got eval evidence and got fixed.
- **Defense-position Fit/Quality is still structurally noisier** than attack/midfield (only one
  shared metric, `defensive_actions_per90`, vs. 3-4 for other groups). Checked both FBref (via
  `soccerdata`) and Understat directly for a second defensive metric — neither has one. A real
  fix needs a new scraper for a league-wide defensive-actions table; deferred as out of scope.
- **The judge's 80% source-accuracy threshold has never been checked against a human labeler**
  — a full protocol for this exists in `NOTES.md` but has never been run.
- **Comparison mode is CLI-only** — not yet in the Streamlit app, which is the documented
  "recommended" entrypoint.
- **Multi-season trend view** and **user-typed custom reference club for Fit** were both
  discussed and explicitly deferred (`TESTS.md`'s "Not yet built") in favor of the items above.
- No CI/CD — network/LLM-touching code (`judge_llm.py`, live scraping, `scoutlite_compare.py`)
  has zero automated coverage by design; regressions there only surface via live testing.
