# ScoutLite — Current Status

**Snapshot date: 2026-09-28. Latest pushed commit: `008ad26` on `main`. 237 tests passing,
working tree clean.** Written as a standalone handoff — for full detail, the underlying docs are
`README.md` (what it does, usage), `NOTES.md` (full build log), `CHANGELOG.md` (user-facing
changes), `EVAL_REPORT.md` (eval findings, synthesis across all tracks), `FIT_SIGNAL_REFERENCE.md`
(what each Fit label means), `TECHNICAL_VISION.md` (fact-checked PE6201 technical companion doc,
not itself for submission), `TESTS.md` (test matrix + deferred items).

## What ScoutLite is

A PE6201 course-project tool that generates a football "player research brief" (deliberately
not a "scouting report" or "verdict") as a Word document. Pulls FBref (stats/bio), Understat
(xG/xA), and NewsAPI (headlines) into one DeepSeek-V3-assisted pipeline, with an automated
judge loop checking the AI-written sections against the source data before shipping.

## Architecture right now

A five-stage pipeline, shared by all three ways in:

1. **Entry points** — `scoutlite_combined.py` (single-player CLI), `scoutlite_compare.py`
   (multi-candidate CLI), `app.py` (Streamlit — the recommended entrypoint; still doesn't expose
   compare mode). All three call the same `research_player()` function and the same shared
   `friendly_error_message()` for categorized, actionable error text instead of raw exceptions.
2. **Data gathering** — `scoutlite.py` (FBref scrape/parse), `understat_xg.py` (xG/xA),
   `news_fetch.py` (headlines, cached 4h). All three read/write through `cache.py`'s shared
   SQLite cache, which now fails soft on any DB error (disk/permissions/corruption) instead of
   crashing the pipeline over what's meant to be a pure optimization.
3. **Deterministic signals** — `scoring.py`. Both **Quality** (1-5 label) and **Fit** (3-tier
   label, e.g. "Hand-in-Glove Fit" vs. a real reference club) are pure percentile math — no LLM
   in either number. All 4 of the module's live population-fetch call sites now degrade to
   "signal not available" on a fetch failure instead of crashing.
4. **LLM synthesis + judge** — one DeepSeek-V3 call (90s timeout, was the SDK's 600s default)
   writes two paragraphs; `judge_rules.py` (deterministic) + `judge_llm.py` (narrow LLM
   fact-check, now warns visibly instead of failing silently) validate them, revising up to 2
   passes before shipping with a confidence warning if still below 80%.
5. **Output** — `docx_report.py` + `app.py`'s Streamlit tables — both now render readable
   labels ("Full Name," "Matches Played") via a shared `format_label()` instead of raw dict keys
   or (in the docx's older formatter) mangled abbreviations ("xG" → "Xg").

## What changed since the 2026-09-23 rewrite, chronological

1. **Streamlit UX pass**: a one-time splash screen on first open; categorized error messages
   (`friendly_error_message()`, shared by the app and both CLIs) instead of raw exception text;
   player disambiguation is now a real clickable table (`st.dataframe`) instead of a cramped
   radio list — prompted by a real user report where "Bruno Fernandes" (11 real FBref matches)
   picked the wrong obscure player; the two philosophy dropdowns merged into one that names the
   actual reference club per combination up front; "Fit: N/A" now distinguishes "no philosophy
   selected" from "genuinely not available," after another real report where the ambiguous
   wording looked like a failure.
2. **Label-clarity audit**: every `st.table()` in the app was showing raw snake_case dict keys;
   fixed with a shared `format_dict_for_display()`/`format_label()` that also fixed a
   pre-existing bug in the *generated Word doc* (`"xG"` was being mangled to `"Xg"` there too).
3. **Three planned, then built, reliability fixes**: DeepSeek's default 600s timeout cut to 90s;
   `openai.InternalServerError` (DeepSeek 5xx) now gets its own message instead of a generic
   one; `cache.py` (previously zero error handling at all) now fails soft on any DB error.
4. **`FIT_SIGNAL_REFERENCE.md`** — a quick-lookup doc for the three Fit tiers, which cutoff is
   actually validated (20, not 35), and the 6 reference clubs, sourced from `scoring.py`.
5. **Track C3 — the significant one.** Track C2's "expected" labels were decided by
   construction (self-graded, not independent evidence). Track C3 fixed that: 10 new cases (3
   defenders, 3 midfielders, 3 attackers, 1 goalkeeper; 5 known / 5 relatively unknown; spanning
   4 of the 5 top-5 leagues), each judged **blind** by a real person before ever seeing the
   tool's output. Tooling (`eval/track_c3_capture.py` → `build_track_c3_labeling_sheet.py` →
   `score_track_c3.py`) follows Track B's proven capture → label → score shape.
   - **Result: 4/10 matched** (worse than Track C2's 4/9) — but unlike C2, all 6 mismatches
     trace to *one* root cause once the raw numbers are read: the metric measures a player's
     statistical output rate, not playing style or tactical role, which no ScoutLite source
     measures. Haaland vs. Dortmund reproduces the exact "elite outlier diverges from any
     realistic squad average" mechanism Track C2 already found with Haaland vs. Man City.
   - **Explicitly reasoned through, not just reported:** does this mean deterministic Fit was
     the wrong design choice? No — the pre-v3 LLM-judged version had the *identical* blind spot
     (21/21 runs stuck at 3/5, honestly refusing to guess at pace/pressing data it also lacked).
     Swapping computation method over the same limited stats doesn't manufacture data that was
     never collected. No threshold change proposed from this finding; the actual fix would be
     sourcing real pace/pressing data, not re-litigating stats vs. judgment.
   - **Triangulation, same day:** since a second genuine blind human wasn't available yet, a
     completely fresh LLM session (zero access to this project's conversation or the tool's
     output, confirmed zero tool calls) judged the same 10 cases from its own football
     knowledge. It agreed with the human on 6/10 but the tool on only 3/10. Framed precisely,
     at the project owner's request: the tool is data/club-fit driven, the human's blind label
     is subjective football expertise, and the fresh LLM's read is closer to **aggregated
     public sentiment** about a player's reputation than either — not computed from data, not
     first-hand tactical judgment, but the dominant narrative repeated across football writing.
     That distinction explains why sentiment and expertise cluster together against pure stats,
     while still disagreeing with each other on 4/10 cases, since a repeated narrative and one
     expert's real judgment aren't the same thing. Full detail: `eval/TRACK_C3_REPORT.md`.
   - Also fixed before scoring anything: real human-typed labels ("Hand in glove fit") didn't
     exactly match the tool's own strings — same class of bug as Track A/B's early
     full-sentence label-matching issue. Added tested normalization first.

Every fix above was verified against the live pipeline or real data, not just the test suite —
this project's running principle has been "verify by running real cases," and essentially every
bug found across this whole build was actually caught that way, not by inspection alone.

## Since the 2026-09-25 snapshot

6. **`TECHNICAL_VISION.md` added, then fact-checked against the real codebase.** A companion
   session drafted a PE6201-facing technical writeup from an earlier version of this file.
   Reviewed line-by-line against the actual, verified build rather than accepted at face value —
   caught and corrected a fabricated-sounding claim ("FBref's Opta-sourced stats were deleted
   site-wide in January 2026 after a StatsPerform contract termination") that contradicted
   `scoring.py`'s own real, previously-documented reason (these metrics were simply never on
   FBref's free pages to begin with); two spots that still described the dropped
   transfer-value-based Quality validation as active, when Section 4/6 correctly say it was
   dropped before implementation; and an overstated "resolved" claim about season-input
   validation that doesn't actually exist in the code. Corrected wording applied directly to the
   file rather than left as a review comment, since this doc is headed toward an academic
   submission and an unverified claim there is a real risk, not just a style nit.
7. **Two real bugs found by actually driving the running app, not by re-reading code.** Asked
   directly "are there any error-handling / UI-testing gaps we've missed" — answered by testing
   the live Streamlit app in a browser rather than auditing the source again, and found two
   bugs neither prior review pass had caught:
   - The candidate-disambiguation table's selection state wasn't reset between searches (same
     `st.dataframe` widget key every time). Reproduced live: selecting a row in one ambiguous
     search, then running a brand-new search, silently carried the old row index into the new,
     differently-sized result list — auto-selecting the wrong player with zero user action — or,
     when the new list was shorter than the stale index, crashed outright with `IndexError: list
     index out of range`, a raw traceback shown to the user. Fixed by keying the table per-search
     (`f"candidate_table_{st.session_state.search_seq}"`); re-reproduced the exact same sequence
     afterward with no stale selection and no crash.
   - Downloading the generated brief made the whole report — Signals, stat tables, news,
     synthesis, and the download button itself — disappear from the screen. Root cause:
     everything was rendered inline inside `if generate:`, but `st.button()` (including
     `st.download_button()`) only returns `True` on the one script run right after it's clicked;
     clicking Download triggers its own rerun, on which `generate` is `False` again, so nothing
     (never stored anywhere) re-rendered. Getting the report back required regenerating the whole
     brief — a full re-scrape + DeepSeek call at real time/token cost — just to see something
     already sitting in memory a moment earlier. Fixed by storing the generated brief in
     `st.session_state` and rendering it from a new `_render_brief()` helper, independent of the
     `generate` button's transient state. Verified live end-to-end afterward (search → ambiguous
     candidate → confirm → generate with a philosophy selected → download) — confidence warning,
     signals, and every section stayed on screen after downloading, and the `.docx` itself
     returned `200 OK`.
   - Neither bug was reachable from the existing pytest suite (both are UI-integration issues,
     not unit-level logic) — 237 tests passed unchanged throughout both fixes, another reminder
     that this project's tests cover the deterministic layer well but the Streamlit surface still
     needs live testing to catch real bugs.
8. **Checked whether an MCP server could replace the custom FBref/Understat scraping.** A couple
   do exist (`kupsas/football-data-mcp` unifies FBref/Understat/SofaScore/Transfermarkt; a few
   Apify-hosted scraper wrappers also surface as "MCP servers") — more than expected, worth
   actually checking rather than assuming. Neither is a better fit: the closest match is a
   static, three-fixed-season dataset, not a live per-player/per-season lookup, and the
   commercial wrappers just move the same scraping to a third party rather than removing the
   "it's scraped data" caveat. More fundamentally, wiring one in would mean letting the LLM fetch
   data itself via tool calls at synthesis time — exactly the "AI-as-scraper" pattern already
   evaluated and rejected for being slower, costlier per-player, and non-deterministic.
   Documented as a checked-off item in `TECHNICAL_VISION.md` Section 8; confirmed the existing
   architecture rather than changing it.

Also ran a broader pre-submission audit (2026-09-27): no secrets in any tracked file, `.env`
correctly gitignored (only `.env.example` placeholders tracked), no accidentally-committed bulk
data, `pip check` clean, both CLI entrypoints parse, `app.py` imports without error, no leftover
TODO/FIXME markers or stray debug prints. `reddit_sentiment.py` looked like a loose end against
the "Reddit dropped from scope" claim at first glance, but it's a genuinely unwired, standalone
exploratory prototype (own docstring confirms it), consistent with that decision rather than
contradicting it.

## What's still open (known, not yet done)

- **Fit's upper cutoff (35 → "Completely Different") is still unvalidated** — Track C2 only
  produced evidence about the lower one; Track C3's finding wasn't about either cutoff being
  wrong, so this remains exactly as untested as before.
- **Track C3 used one blind human labeler.** The fresh-LLM triangulation is supplementary, not
  a substitute — a genuine second independent human labeling the same 10 cases blind is the
  natural next strengthening step, to check the pattern isn't one person's particular reading.
- **Defense-position Fit/Quality is still structurally noisier** than attack/midfield (a single
  shared metric vs. 3-4 for other groups). Confirmed directly that neither FBref (via
  `soccerdata`) nor Understat exposes a second defensive metric — a real fix needs a new
  scraper, deferred as out of scope.
- **The judge's 80% source-accuracy threshold has never been checked against a human labeler**
  — a full protocol exists in `NOTES.md`, never run. Independently corroborated (2026-09-28) by
  a "Judge LLM development vs. production" architecture pattern seen elsewhere — mapped against
  this project's actual build, it confirmed this exact calibration step (golden dataset + human
  annotations + judge-accuracy-vs-threshold check) is the missing piece, not a nice-to-have.
  Still not run — real human blind-labeling time, same shape as Track C3.
- **Comparison mode is still CLI-only** — not in the Streamlit app, the documented "recommended"
  entrypoint.
- **Quality's own external validation was discussed and deferred.** A "Quality vs. transfer
  value" ranking check was floated at one point and explicitly dropped — it conflicts with
  ScoutLite's own hardcoded rule against transfer-value language anywhere in a brief, and
  transfer value is a noisy proxy for on-pitch quality anyway (age, contract length, hype,
  position scarcity all confound it). No replacement external-validation method has been chosen.
- **Multi-season trend view** and **user-typed custom reference club for Fit** remain deferred
  (`TESTS.md`'s "Not yet built").
- No CI/CD — network/LLM-touching code has zero automated coverage by design; regressions there
  only surface via live testing, same as how every bug above was actually found.
