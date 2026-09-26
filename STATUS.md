# ScoutLite — Current Status

**Snapshot date: 2026-09-25. Latest pushed commit: `7786827` on `main` (one more commit —
Track C3's LLM-triangulation writeup — staged but not yet pushed as of this snapshot). 237
tests passing, working tree otherwise clean.** Written as a standalone handoff — for full
detail, the underlying docs are `README.md` (what it does, usage), `NOTES.md` (full build log),
`CHANGELOG.md` (user-facing changes), `EVAL_REPORT.md` (eval findings, synthesis across all
tracks), `FIT_SIGNAL_REFERENCE.md` (what each Fit label means), `TESTS.md` (test matrix +
deferred items).

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

## What changed since the last snapshot (2026-09-23), chronological

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
  — a full protocol exists in `NOTES.md`, never run.
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
