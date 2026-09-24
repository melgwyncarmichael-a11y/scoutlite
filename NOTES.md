# ScoutLite — Build Notes

## Track C3 result: 4/10, but every mismatch traces to one cause -- output volume vs. playing style (2026-09-25, later still)

Blind labels came back (`eval/track_c3_human_labelled.csv`). First real bug: the filled-in text
("Hand in glove fit", "Somewhat fits", "Completely different") doesn't exactly equal the tool's
own label strings -- the same class of issue as Track A/B's early full-sentence label-matching
bug. Added `normalize_label()` (keyword-based: "somewhat" / "completely...different" /
"hand"+"glove") to `score_track_c3.py`, tested against the exact messy strings actually
received, before scoring anything for real. Also split raw vs. normalized text in the output so
a genuinely unrecognized label would be visible, not silently dropped.

**Result: 4/10 matched** (worse than Track C2's already-imperfect 4/9) -- **3/5 on relatively
unknown players, 1/5 on known ones.** Pulled the raw component breakdown behind all 6
mismatches before writing anything up, rather than reporting the headline number alone
(`eval/TRACK_C3_REPORT.md` has the full detail). Every single mismatch turned out to share the
same root cause: the tool measures whether a player's *statistical output rate* matches a
squad's average, but a blind labeler's "fit" judgment draws on *playing style and role*
(pressing intensity, passing tempo, defensive engagement type) that no ScoutLite metric
measures at all. Concretely:
- Kean vs. Real Madrid (the single biggest gap, 50.5) came from one thin statistical season
  (goals_per90 at the 6.3rd percentile that specific year) -- the tool measured the season, the
  labeler evidently knew the player beyond it.
- Haaland vs. Dortmund (27.6) reproduces the *exact* mechanism Track C2 already found with
  Haaland vs. Man City: an elite scorer shows a real gap from any realistic squad average,
  including his own former club's, because the metric can't separate "elite output volume" from
  "fits the system's role."
- The other four mismatches (Guirassy, Rodri, Upamecano, Van Dijk) all show the same shape:
  counting-stat percentiles land reasonably close, but a labeler who knows the players' actual
  tactical roles perceives a bigger real gap than raw output-rate similarity shows.

**Deliberately not proposing a threshold change from this.** Unlike Track C2 (a genuine
miscalibration, fixed by moving one number), this finding is about what the metric can see at
all, not where the cutoff sits -- retuning 20/35 wouldn't touch the actual cause. Recommended
next step (not yet built): a second blind labeler on the same 10 cases, to check this isn't one
person's particular reading.

## Track C3 tooling built: Fit validation against blind human judgment, not self-graded cases (2026-09-25, later still)

Track C2 checked the 15/35 thresholds against 9 cases, but the "expected" label for each was
decided by construction (self-reference should read Hand-in-Glove, mismatch should read
Completely Different) -- reasoned out by the same person who built the tool. Discussed with the
project owner whether that counts as real evidence; agreed it's weaker than it looked, and
planned a successor round (Track C3) using genuinely independent, blind human labeling instead
-- someone judges each case from their own football knowledge, before ever seeing the tool's
output, per "don't grade your own homework."

**Tooling built, following Track B's already-proven three-stage shape** (capture -> build a
labeling sheet -> a human fills it in blind -> score) rather than inventing a new pattern:
- `eval/track_c3_capture.py` -- same deterministic capture as `track_c2_capture.py` (no LLM),
  but records no `expected_label` at all; the tool's own computed label is saved but never
  printed anywhere a labeler would see it before judging.
- `eval/build_track_c3_labeling_sheet.py` -- produces `eval/track_c3_labels.csv` with only
  neutral context (player, real club, competition, position group, fame tier, the reference
  club's real name, and the philosophy in plain English) -- deliberately no tool label, no
  `avg_abs_diff`, nothing that could bias a blind judgment. Two separate fill-in columns:
  `hand_label` (the real, blind evidence) and `your_guess` (an optional informal second opinion,
  explicitly documented as not independent evidence on its own, since whoever's guessing already
  knows how the tool works).
- `eval/score_track_c3.py` -- joins captures against filled-in blind labels, reports the honest
  match rate, and -- per the agreed plan -- flags every case whose `avg_abs_diff` sits within 3
  points of either cutoff (20, tuned by Track C2; 35, still never validated), since a boundary
  case is more informative than one sitting confidently mid-range regardless of match/mismatch.

**10 cases, agreed with the project owner across several rounds of back-and-forth:** 3
defenders, 3 midfielders, 3 attackers, 1 goalkeeper; 5 relatively famous / 5 relatively unknown;
rotated across all 6 `REFERENCE_CLUBS` entries. First draft was almost entirely Premier League
(8/10) -- flagged and rebalanced on request to 3 Premier League / 3 Bundesliga / 3 Serie A / 1
La Liga, spanning 4 of the 5 top-5 leagues instead of concentrating on one.

**Live-captured all 10, found two things only running it for real surfaced:**
1. "Rodri" alone matches **100** unrelated, mostly retired lower-league Spanish players on
   FBref and never surfaces the actual Manchester City Rodri within that cap -- his full legal
   name (Rodrigo Hernández Cascante) does. Pinned his exact URL
   (`fbref.com/en/players/6434f10d/Rodri`) rather than relying on the plain name.
2. Two cases' real 2023-2024 clubs (this eval's standard season, for consistency with every
   other track) predate transfers I assumed already happened: Guirassy was at Stuttgart, not
   Dortmund yet; Koné was at Gladbach, not Roma yet. Both still Bundesliga, so the league-
   diversity goal holds regardless -- corrected the case notes to say so rather than leave a
   description that no longer matched what the tool actually resolved.

Built `build_track_c3_labeling_sheet.py` and confirmed the resulting CSV contains zero tool
output -- spot-checked the raw file directly. Ran `score_track_c3.py` against the still-blank
sheet to confirm it degrades correctly (reports "10 not yet labeled," not an error) rather than
assuming that path works. One thing already visible before any human has labeled anything:
`score_track_c3.py`'s boundary check already flags `bastoni_vs_dortmund` (22.9) and
`van_dijk_vs_brighton` (22.3) as sitting close to the tuned 20-cutoff -- worth the blind
labeler's particular attention once labeling starts, though the actual match/mismatch verdict
still depends entirely on their independent judgment, not this observation.

232 tests passing (11 new: `_boundary_note`/`join_records`/`summarize` pure-logic coverage).

## Three planned error-handling gaps: timeouts, server errors, cache failures (2026-09-25)

Asked directly for a plan covering "if it doesn't run, server error, timeout, or others,"
before building anything. Investigated each concretely rather than guessing at what might be
wrong, then built all three once the plan was approved:

**1. DeepSeek's default request timeout was 10 minutes.** Checked the installed `openai`
package directly: `Timeout(connect=5.0, read=600, write=600, pool=600)` is the SDK's own
default when no `timeout=` is passed. A genuine hang (not an error, just DeepSeek never
responding) would leave a user staring at "Calling DeepSeek-V3..." for up to 10 minutes before
anything surfaced -- the eventual error message was already correct
(`friendly_error_message`'s `APITimeoutError` case), it just took far too long to fire. Set an
explicit `REQUEST_TIMEOUT_SECONDS = 90.0` on the shared client in `llm_client.py` -- generous
headroom over how long a real call actually takes (seconds, per this session's own live
testing) while failing fast enough to be noticed. The SDK's default `max_retries=2` for
transient errors (timeouts, connection errors, 5xx) already applies underneath this, unchanged.

**2. DeepSeek 5xx errors weren't distinguished from other API failures.** They fell into the
generic "the DeepSeek API request failed" bucket alongside genuinely different problems.
`openai.InternalServerError` (confirmed via its actual class hierarchy --
`InternalServerError -> APIStatusError -> APIError -> OpenAIError`) is now its own case in
`friendly_error_message()`, ahead of the generic `OpenAIError` fallback: "DeepSeek's servers
are having an issue right now -- not something wrong with your request."

**3. `cache.py` had zero error handling anywhere.** Confirmed directly (grepped the file for
`try`/`except` -- nothing). A disk-full, permissions, or corrupted-DB situation would have
crashed the entire pipeline over what's supposed to be a pure performance optimization, never
load-bearing for correctness. New `_fail_soft_on_db_error` decorator wraps all 8 public
functions (4 `get_cached_*`, 4 `set_cached_*`): on any exception, warns visibly
(`warnings.warn`, same pattern as `scoring.py`'s and `judge_llm.py`'s earlier fixes) and
returns `None` -- which is already every `get_cached_*()`'s own "not cached" value, so callers
need zero changes to treat a DB failure exactly like a cache miss and fetch live instead.
Confirmed a transient failure doesn't poison later calls -- the next call after a simulated DB
error just works normally again, since `get_conn()`'s lazy-reconnect logic isn't disturbed by
the decorator catching the failure one level up.

221 tests passing (11 new: 2 for the client timeout, 1 for the new `InternalServerError`
category, 3 for `_fail_soft_on_db_error`'s get/set/no-poisoning behavior, plus coverage
overlap). Live-verified the full pipeline still works end to end through all three changes at
once (a real CLI run against Erling Haaland, cache hits, DeepSeek calls, judge loop, saved
brief) -- confirming the new 90s timeout doesn't interfere with an actual working call, only a
stuck one.

## Unclear-labels audit: raw dict keys in the app, a pre-existing mangling bug in the docx (2026-09-24, later still)

Asked directly to check the Streamlit app for unclear labels. Read through every user-facing
string in `app.py` rather than skimming, and live-tested to confirm rather than trusting the
source alone. The clear, high-value finding: `st.table(bio)`, `st.table(stats)`,
`st.table(keeper)`, `st.table(misc)`, and `st.table(xg)` all passed raw dicts straight to
Streamlit, which uses dict keys as row labels verbatim -- so a scout saw `full_name`,
`matches_played`, `understat_matched_name`, `goals_plus_assists` etc. exactly as written in the
code, not a formatted label.

Checked `docx_report.py` before assuming the fix was app-only, since `_add_dict_table()` already
does *some* key formatting (`key.replace("_", " ").title()`) for the generated Word document --
and found that formatter has its own real, already-shipping bug: `"xG".title()` produces "Xg",
`"npxG".title()` produces "Npxg", `"gk_saves".replace("_"," ").title()` produces "Gk Saves" --
`str.title()` doesn't preserve internal capitals, so every football-stat abbreviation in every
brief generated so far has been silently mangled. Confirmed this live in Python before touching
any code, not assumed.

Fixed both with one shared formatter instead of two independent ones that could drift:
`format_label()` in `docx_report.py` maps snake_case keys to readable labels via a small
override table (`xg`->`xG`, `xa`->`xA`, `npxg`->`npxG`, `npxa`->`npxA`, `url`->`URL`, `gk`->`GK`,
`pct`->`%`) for known abbreviations, falling back to ordinary `.capitalize()` per word otherwise.
`format_dict_for_display()` wraps it for callers (app.py) that hand a whole dict to a different
rendering surface (`st.table`) instead of building a docx table cell by cell, and also absorbs
the same empty-value filtering `_add_dict_table()` already did. `_add_dict_table()` itself now
calls `format_label()` instead of the old raw `.title()`.

Live-verified in the browser: generated a real Haaland brief, confirmed every table now shows
"Full Name," "Matches Played," "Goals Plus Assists," "Understat Matched Name," "Understat URL,"
while "xG," "xA," and "npxG" render correctly unmangled -- not just that the code looked right,
but that the actual rendered page shows it. 215 tests passing (5 new, covering the abbreviation
preservation, ordinary title-casing, the url/pct overrides, and empty-value filtering).

Other labels reviewed and left alone as already clear: button/input labels, help text, status-
log lines during generation, the confidence-warning message, and section headers. One minor,
lower-priority item noted but not changed: "claim-grounding" (used in the automated-judge
caption) is fact-checking jargon a scout may not immediately parse -- flagged for a future pass,
not fixed now since it's a wording polish, not a functional-clarity gap like the raw keys were.

## "Fit: N/A" made to say why, after another real screenshot (2026-09-24, later still)

Prompted by a follow-up screenshot: a midfielder brief showed "Quality: World Class · Fit:
N/A" with no philosophy dropdown visible in the crop. Traced the actual condition rather than
assuming: `compute_fit_signal()` returns `None` for two genuinely different reasons -- no
philosophy given at all (`not (in_possession and out_of_possession)`), or a philosophy given
but the league/position isn't covered by the reference-club comparison -- and both `app.py`'s
top Signals line and `docx_report.py`'s equivalent (`build_docx` and `build_comparison_docx`)
collapsed both into one identical "N/A"/"not available", making "you didn't ask for this" look
exactly like "this genuinely failed."

The generation-time status log (`app.py`) and Section 4 of the single-player docx already made
this distinction correctly -- only the top-line summary and the comparison-doc's summary
table/per-candidate line didn't. Fixed all four sites (`app.py`'s top line,
`build_docx`'s top line, `build_comparison_docx`'s summary-table Fit column, and its
per-candidate Fit line) to the same 3-state logic: signal present / philosophy given but
unavailable / no philosophy given. `has_philosophy` was already computed later in `build_docx`
(Section 4) -- hoisted the computation earlier so the top Signals block can use it too, rather
than duplicating the check.

One existing test (`test_fit_not_assessed_when_no_philosophy`) was actually asserting the OLD,
ambiguous behavior ("Fit: not available" for the no-philosophy case) -- updated to expect the
new, distinguishing text instead of just relaxing it to keep passing. Live-verified in the
browser: searched Erling Haaland, left the philosophy dropdown on "Not specified," generated a
real brief, confirmed the Signals line reads "Fit: N/A (no club philosophy selected)" --
matching the "No club philosophy was specified, so Fit is not assessed" text already in the Fit
Read section below it, so the two no longer contradict each other in tone.

210 tests passing.

## Candidate disambiguation table + reference-club-visible philosophy dropdown (2026-09-24, later still)

Prompted by a real user report with a screenshot: searching "Bruno Fernandes" in the app and
generating a brief showed "Fit: Completely Different vs. Manchester City" with suspicious
exact-0/100 percentiles everywhere, and the user (reasonably) asked why a Man United player was
being compared to Man City at all.

Investigated live rather than assuming either "bug" or "not a bug": ran the CLI's own search
for "Bruno Fernandes" and found FBref has **11 different real people** with that name --
several obscure, decades-inactive players alongside the real Manchester United one. Ran the
correct player directly by URL with the same philosophy and got smooth, sane percentiles
(69, 94, 43, 50), confirming the "Manchester City" comparison itself was correct (Fit compares
against the reference club for the chosen *philosophy*, not the player's own club -- working as
designed) but the exact-0/100 numbers in the screenshot pointed at the wrong candidate having
been picked from the app's ambiguous-match list, or an unusually thin data sample.

Built two fixes on request:

**1. Candidate selection is now a real table, not a cramped radio list.** The old UI crammed
name + alt name + nationality + years active + clubs into one long string per radio option --
with 11 near-identical-looking "Bruno Fernandes" entries, easy to misread which one has
"Manchester United" in its Clubs field. Replaced with `st.dataframe(..., on_select="rerun",
selection_mode="single-row")` -- a real sortable table with separate columns, click a row to
select it, confirm button shows the selected player's name. Verified the exact Streamlit
selection-state API live (`event.selection.rows`) by reading Streamlit 1.62's own source
(`elements/arrow.py`) rather than guessing, then confirmed it end-to-end in the browser:
searched "Bruno Fernandes," saw all 11 candidates in the table, correctly identified and
selected the row with "Manchester United" in Clubs, and it resolved to the right FBref URL.

**2. The two separate philosophy dropdowns became one, naming the reference club up front.**
Previously "club philosophy -- in possession" and "-- out of possession" were independent
selectboxes; you only discovered which real club Fit was comparing against after generating the
whole brief. Merged into a single dropdown built directly from `scoring.REFERENCE_CLUBS` (not a
hardcoded parallel list, so it can't drift out of sync with what `compute_fit_signal()` actually
uses) -- e.g. "Slow, methodical possession + High line, counter-press — compared to Manchester
City" is now one selectable option, all 6 combinations plus "Not specified" spelled out the same
way. Verified live: selected that exact option, generated a real brief, confirmed the Fit
signal correctly used Manchester City throughout.

Both required no changes to `scoring.py`/`scoutlite_combined.py`'s actual signal logic --
purely presentation. 210 tests still passing (no test changes needed; `app.py` has no unit
coverage by design, verified live in the browser as with every other change to this file).

## Three more error-handling gaps, fixed one by one (2026-09-24)

Follow-on from the app.py error-handling review below: asked "anything else I should be aware
of," traced the rest of the pipeline (not just app.py) for the same class of issue, found three
real gaps, fixed all three on request.

**1. `scoring.py`'s core population fetches had zero protection against a live failure.** Four
call sites (`sd.FBref(...).read_player_season_stats(...)` in both the goalkeeper and
misc/defense branches of `compute_quality_signal` and `compute_fit_signal`) had no try/except
at all -- a network blip or FBref rate-limiting mid-pull would crash the entire signal, and by
extension the entire brief, instead of degrading to "signal not available" the way every OTHER
"can't compute this" path in the same functions already does. New
`_safe_read_player_season_stats()` wraps the fetch, returns `None` on failure (this module's
existing "not available" convention) instead of raising, and always `warnings.warn()`s so the
failure is visible rather than silently indistinguishable from "league not covered." All 4 call
sites updated. `understat_xg.py` already did this correctly (narrow `except
(RequestException, ValueError)`, wrapped in a clear `UnderstatUnavailable`) -- this brings
FBref's population fetch in line with it. New tests confirm `compute_quality_signal`/
`compute_fit_signal` return `None` (not raise) when the fetch fails, with a warning issued.
One existing test's `_DummyFBrefReader` mock had to change (it returned `None` as its own
placeholder "I don't care about this" value, which collided with the new function's real
failure sentinel) -- fixed to return an opaque non-`None` object instead.

**2. `judge_llm.py`'s fact-checker failed completely silently.** Its `except Exception: return
{"findings": [], "has_major": False}` had zero visibility -- a real bug in this code (not just
an API hiccup) would produce the exact same "nothing to flag" result as a genuinely clean pass,
so a broken fact-checker and a working one were indistinguishable from the outside. Added
`warnings.warn()` with the actual exception before returning, same pattern as fix 1. New
`tests/test_judge_llm.py` (this module had no test coverage at all before) confirms the warning
fires on both an API-level failure and a malformed-JSON response, and that the fail-soft
contract (empty findings, not a raised exception) is unchanged either way.

**3. Both CLI entrypoints still dumped raw exception text**, the exact thing just fixed in
app.py three days ago but never extended to the CLI. Extracted the categorization logic out of
app.py's `_show_error()` into a new shared `friendly_error_message(e, context)` in
`scoutlite_combined.py` -- app.py, `scoutlite_combined.py`'s own `main()`, and
`scoutlite_compare.py` (both its per-candidate skip and its top-level handler) all call the
same function now, instead of three copies that could drift. `app.py`'s `openai`/
`WebDriverException` imports became unused once the categorization logic moved out and were
removed. New `tests/test_friendly_error_message.py` covers every category (RuntimeError,
`openai.AuthenticationError`/`RateLimitError`/`APIConnectionError`/generic `OpenAIError`,
`WebDriverException`, `requests.RequestException`, and the generic fallback). Live-verified via
the actual CLI: searching a nonexistent name now prints a clean "No FBref match found for 'X'"
with no "Error:" prefix clutter, and a real successful brief generation still works end to end
through all three fixes combined.

Also fixed in passing: `scoutlite_combined.py`'s own module docstring still listed
`fetch_player_page_html` among the functions it reuses from `scoutlite.py` -- that function was
deleted from `scoutlite.py` in the Red-tier crash fix days ago; the docstring just never got
updated. Corrected to the real function names (`search_player`, `get_player_page`).

210 tests passing (up from 202 before this entry).

## Streamlit app: first-open splash + categorized error handling (2026-09-23)

Requested directly: "bake in error handling for the user" and "a loading screen for the UI
when it loads." Asked which specifically was meant for the loading screen (a first-open splash
vs. tightening loading feedback throughout the existing flow) rather than guessing and building
the wrong scope -- answer was the first-open splash.

**Splash**: `st.session_state`-gated block right after `st.set_page_config()` -- shows a
centered "Loading ScoutLite..." screen via `st.empty()` + a deliberate `time.sleep(1.0)` (without
it the script runs faster than a human perceives, so the splash wouldn't actually be visible),
then clears itself and never reappears for the rest of that browser session (any button click
reruns the script, but `app_initialized` is already set by then). Verified live via the browser
preview: splash renders correctly in dark mode, transitions cleanly to the real form after ~1s.

**Error handling**: found and fixed a real bug while investigating, not just cosmetic --
`app.py`'s three `except Exception as e: st.error(f"Something went wrong: {e}")` blocks dumped
raw exception text regardless of type. Replaced with `_show_error(e, context)`, which
categorizes by actual exception type (not string-matching, which breaks silently if a library's
wording changes): `openai.AuthenticationError` / `RateLimitError` / `APIConnectionError` get
DeepSeek-specific guidance, `selenium.common.exceptions.WebDriverException` gets an
FBref-rate-limit-aware message, generic `requests.RequestException` gets a network-check
message, and anything else falls back to a plain "something went wrong while X" with the raw
exception tucked into a `st.expander("Technical details")` rather than either hidden or dumped
as the headline.

**A `RuntimeError` special case, found only by testing live, not by reading the code.** Assumed
`search_player()` returning an empty list was the zero-match case and added an
`elif len(candidates) == 0` branch in `app.py` for it -- wrong. Live-tested searching a
nonsense name in the actual running app (browser preview, not just unit tests) and got an
unstyled `st.error` instead. Traced it: `scoutlite.py:110` already raises
`RuntimeError(f"No FBref match found for '{player_name}'")` itself -- `search_player()` never
returns an empty list at all, so the branch I'd just written was dead code, silently
unreachable. Deleted it, and instead special-cased `RuntimeError` in `_show_error()` to render
as `st.warning` with no technical-details expander (it's an expected, actionable, user-facing
message `scoutlite.py` already wrote for exactly this situation, not a system failure) rather
than `st.error`. Re-verified live: the same nonsense-name search now shows a calm yellow
warning, not a red error box. A concrete reminder that reading the source is necessary but not
sufficient -- the live app itself is the only thing that told the truth about which branch
actually runs.

Also created `.claude/launch.json`... briefly. Discovered mid-task that a global
`~/.claude/launch.json` (from an earlier session, pointed at system Python rather than this
project's `.venv`) already defines a `scoutlite` preview config on port 8510 -- deleted the
redundant project-local one rather than leaving two configs to drift out of sync. Worth fixing
later: that global config's system-Python environment doesn't match `requirements.txt`'s pinned
versions at all, which is exactly the kind of environment drift the dependency audit flagged
as a risk in principle -- now confirmed as a real, existing instance of it, just not this
session's task to fix.

196 tests still passing (no test changes needed -- `app.py` has never had unit coverage, by
design, since it's a Streamlit script with top-level side effects; verified live in the browser
instead, consistent with how every other `app.py` change in this project has been checked).

## NewsAPI caching + compare-mode dedup, prompted by a direct question about repeat pulls (2026-09-22)

Asked directly whether pulling the same players repeatedly (across compare runs, or an
accidental duplicate within one) could cause a real problem. Traced the actual pipeline rather
than answering from general caching-hygiene instinct: FBref pages and Understat populations are
both already well-cached (24h TTL, or indefinite for a past season's page) -- but `news_fetch.py`
never touched `cache.py` at all. Every `research_player()` call re-fetched NewsAPI fresh, no
matter how recently the same player was already looked up, against a free tier capped at 100
requests/day. `scoutlite_compare.py` (built two days ago) makes this worse by construction --
one NewsAPI call per candidate per run, with no dedup on the input list, so a literal repeated
name would silently burn quota (and DeepSeek synthesis+judge calls) twice for identical output.

**Fixed both, not just one, since they compound:**

1. **NewsAPI results are now cached** (`cache.py`'s new `news_articles` table,
   `NEWS_TTL_HOURS = 4` -- short on purpose: long enough to absorb repeated/overlapping lookups
   in one scouting session, short enough that a 28-day lookback window never looks stale within
   a session). `fetch_articles()` gained a `force_refresh` param threaded through from all three
   real call sites (`scoutlite_combined.research_player()`, `app.py`, `eval/track_b_capture.py`)
   the same way FBref/Understat's `force_refresh` already works. Cache key is
   `f"{query.strip().lower()}::{limit}"` -- includes `limit` since a future caller requesting a
   different article count shouldn't silently get served a smaller/larger cached batch.
2. **`scoutlite_compare.py` now dedupes its candidate list** (`dedupe_players()`, extracted as
   a pure function so it's actually unit-testable, unlike the rest of that file's live-only
   orchestration) -- case/whitespace-insensitive, keeps first-seen casing and order, prints
   which name got skipped rather than silently dropping it.

Verified both live, not just via mocked tests: fetched Haaland's news once (0.57s, live), then
again immediately (0.000s, cache hit, confirmed identical result) -- and ran
`scoutlite_compare.py` with a real accidental duplicate ("Erling Haaland" / "erling haaland"),
confirming it printed the skip message, correctly ran only 2 candidates (not 3), and the
second candidate's Haaland-adjacent news reused the cache entry just warmed a moment earlier.

13 new tests (`tests/test_news_fetch.py`'s caching-decision logic with a mocked HTTP call plus
the existing temp-DB fixture pattern from `test_cache.py`; `tests/test_scoutlite_compare.py`
for `dedupe_players()`; two new roundtrip tests added to `test_cache.py` itself). 196 tests
passing overall. Noticed but didn't fix, out of scope for this task: `news_fetch.py`'s
`datetime.utcnow()` is deprecated in current Python and only now surfaced because this was the
first time that code path got unit-tested at all.

## Yellow-tier architecture/dependency fixes from the same audit (2026-09-21, later still)

Worked through the remaining, lower-severity findings from the same diagnostic pass (the two
Red/critical ones are the entry above). All four were genuinely fixed, not just noted:

**1. Unpinned dependencies.** `requirements.txt` had zero version pins across all 12 packages,
no lockfile. Pinned every direct dependency to its exact currently-installed, tested version
(`pip show` per package, not guessed), and added `requirements-lock.txt` (`pip freeze`'s full
transitive closure, 105 packages) for byte-for-byte reproducible installs. `pip check` still
clean after pinning.

**2. `build_docx()`'s 16-parameter signature.** Collapsed to `build_docx(data: dict,
output_path)`, where `data` is the exact same dict shape `research_player()` already returns --
removes the risk of two adjacent same-typed params (`misc`/`keeper`, both `dict | None`) being
silently transposed at a call site, which the old signature had no way to catch. Added
`philosophy` to `research_player()`'s returned dict so it's fully self-contained. Updated both
call sites (`scoutlite_combined.run()`, `app.py`) -- app.py's inline philosophy-dict
construction was also just a duplicate of `philosophy_from_keys()` (extracted from the earlier
refactor), so replaced it with the shared helper instead of leaving two copies of the same
mapping. `build_comparison_docx()` already took `list[dict]` from the start; `build_docx()` now
matches its own newer sibling's pattern instead of being the odd one out.

**3. Two `except Exception` blocks in `scoring.py`'s PAdj fallback that failed silently.**
Deliberately did NOT just narrow the exception types -- the actual failure modes come from a
live `soccerdata`/FBref fetch (`_team_possession_map`), and guessing at every possible library-
internal exception risked either missing a real one (crashing the whole signal) or being too
narrow to matter. Instead made the existing broad catch *visible*: both sites now
`warnings.warn(...)` with the actual exception before falling back, so a genuine bug can no
longer look identical to "no possession data this season" the way a bare fallback did. Confirmed
this actually surfaces something real: one existing test's incomplete mock (missing
`read_team_season_stats`) now visibly triggers the warning in test output, exactly the kind of
thing this fix is meant to catch, where it used to be entirely invisible.

**4. Three separate `OpenAI(...)` client instantiations** (`scoutlite.py` -- removed with the
dead code above, `scoutlite_combined.py`, `judge_llm.py`), each built fresh per call. New
`llm_client.py` -- a single lazy module-level singleton (`get_deepseek_client()`) both modules
now import instead of constructing their own. Lazy on purpose: importing either module still
doesn't require `DEEPSEEK_API_KEY` to be set, only actually calling the function does, so tests
that only exercise parsing/prompt-building are unaffected. Verified the singleton is real (same
object across calls) and re-ran the full CLI live afterward to confirm the synthesis + judge
loop still work end to end through the shared client, not just that imports resolve.

183 tests still passing throughout (the one new warning above is expected, not a failure).
Deliberately left the "split `scoring.py`/`scoutlite_combined.py` by responsibility" item alone
-- both are still comfortably-sized (553 and 470 lines) and this round's fixes didn't grow
either meaningfully; a bigger structural split stays a "when it actually gets bloated" call, not
a "why not now" one.

## Architecture/dependency audit: one confirmed crash, one confirmed latent race (2026-09-21, later still)

Ran a full dependency + architecture diagnostic across the codebase (import graph, exception
handling, parameter shapes, HTTP timeout coverage, secrets/git-history scan, file sizes). Two
findings were real, verified bugs rather than style opinions -- fixed both immediately:

**1. `scoutlite.py`'s legacy CLI called a function that no longer exists.** `main()` (the
project's original pre-v1 "MVP slice" -- one player name, one FBref fetch, one LLM paragraph,
long since superseded by `scoutlite_combined.py`) called `fetch_player_page_html()`, which was
renamed/replaced at some point (see the "Lookup confirmation step" entry below) without this
dead call site being updated. Confirmed via `grep` that the function is defined nowhere in the
codebase -- `python3 scoutlite.py "<name>"` would crash immediately with `NameError`. Zero test
coverage existed for this path, which is exactly why it was never caught. Fixed by deleting the
entire dead `summarize_with_llm()`/`main()`/`__main__` block rather than repairing it -- it
duplicated (worse) what `scoutlite_combined.py` already does properly, so fixing it forward
would just resurrect a redundant, unmaintained second pipeline. Removed the `argparse`, `sys`,
`os`, and `OpenAI` imports that were only used by the deleted code, and rewrote the module
docstring, which still described the file as the "MVP slice" rather than what it actually is
now: the shared FBref scraping/parsing layer both `scoutlite_combined.py` and `app.py` depend
on. `scoutlite.py` now only exports the real, actively-used functions.

**2. `cache.py`'s module-level SQLite connection had no thread-safety guard.** `get_conn()`
caches one `sqlite3.Connection` for the process's whole life, created with Python's default
`check_same_thread=True`. Streamlit's ScriptRunner can execute a session's script reruns on
different worker threads within the same process -- under concurrent access (two tabs, two
users) the first cross-thread cache hit would raise `sqlite3.ProgrammingError: SQLite objects
created in a thread can only be used in that same thread.` Verified this wasn't hypothetical:
reproduced the exact error with a minimal script using the old default, then confirmed
`check_same_thread=False` (safe here since WAL mode already serializes actual access) resolves
it with a real cross-thread read/write test, not just "tests still pass." Never hit in practice
so far since usage has been single-user/single-tab, but was a live crash waiting for concurrent
access -- plausible even in a course-demo setting.

183 tests still passing after both fixes (no test coverage change needed -- neither fix altered
any tested behavior, only removed dead code and hardened an untested concurrency path).

## Multi-candidate comparison feature; second defensive metric checked and deferred (2026-09-21)

Two feature ideas discussed after the judge fixes above: (1) a second defensive metric to fix
the Track C2-diagnosed defense-group Fit/Quality volatility, (2) a multi-candidate comparison
brief (a scout's actual workflow is usually "compare 2-3 targets for a role," not one player at
a time). Investigated #1 before committing to build it, per this project's own standard of
checking feasibility against real data before writing code:

**#1 checked, not buildable as scoped, deferred.** `soccerdata`'s FBref reader only exposes 5
player-season stat types (`standard`, `shooting`, `playing_time`, `keeper`, `misc`) -- no
separate "Defensive Actions" endpoint with blocks/clearances. Pulled `misc`'s actual columns
live to check: `CrdY, CrdR, 2CrdY, Fls, Fld, Off, Crs, Int, TklW, PKwon, PKcon, OG` -- nothing
else in there is a clean defensive-engagement metric (`Fls`, fouls, is the closest candidate and
a bad one -- conflates aggression with quality, and it's a discipline stat as much as a
defensive one).

**Initially only checked FBref -- caught later (2026-09-21, prompted by a direct question) that
Understat was never actually checked.** Fetched its live per-player data to confirm rather than
assume: full field set is `assists, games, goals, id, key_passes, npg, npxG, player_name,
position, red_cards, shots, team_title, time, xA, xG, xGBuildup, xGChain, yellow_cards` -- zero
defensive-action tracking, consistent with Understat being an xG/shots provider by design, not
an event-data source. `yellow_cards`/`red_cards` are the same bad discipline-not-quality proxy
as FBref's `Fls`; `xGChain`/`xGBuildup` measure attacking buildup involvement, not defending, so
neither helps here either. Conclusion unchanged, but now actually checked against both of the
project's real data sources instead of one. A real fix needs scraping a league-wide
defensive-actions HTML table directly, population-wide, which is closer to a new data-source
integration than a column addition.
Flagged to the project owner with this exact finding rather than silently downgrading scope;
deferred into `TESTS.md`'s "Not yet built" alongside two other explicitly-deferred ideas
(multi-season trend view, user-typed custom reference club).

**#2 built.** Refactored `scoutlite_combined.py`'s `run()`: extracted `research_player()` (and
a small `philosophy_from_keys()` helper) so the single-player pipeline is callable as a
function, not just inline CLI logic -- `run()` itself is now a thin wrapper, behavior unchanged
(176 -> 183 tests after this + the new comparison tests, plus a live re-run of the single-player
CLI to confirm the refactor changed nothing observable). New `scoutlite_compare.py` calls
`research_player()` once per candidate (an ambiguous name is skipped with a message, not
guessed or aborting the whole run) and hands the results to a new
`docx_report.build_comparison_docx()` -- deliberately a separate function from `build_docx()`
rather than a shared refactor, to keep zero risk to the existing, tested single-player output.
Renders a summary table (Player / Position / Quality / Fit / Confidence) up top, then each
candidate's full bio/stats/news/fit-read/sources, then one shared "Understanding the Signals"
glossary at the end rather than repeating it per candidate.

Live-tested end to end with a real 2-player comparison (Haaland vs. Watkins, both vs. Man
City's possession/high-line philosophy, one shared scout note) -- confirmed the summary table,
per-candidate confidence warnings, and shared glossary all render correctly by reading the
saved .docx back, not just by the script exiting cleanly. CLI only for this round; not wired
into the Streamlit app yet.

## Two judge_llm.py false positives, found by reading a sample brief's judge output (2026-09-18, later still)

Generated a fresh sample brief (Erling Haaland vs. Man City, post the threshold fix above) to
send as a demo. The judge's own LLM-fact-checker findings looked wrong on read-through, not
just noisy -- worth digging into rather than shrugging off as normal model caution.

**Bug 1: the fact-checker's own rendering of `fit_signal` disagreed with what the synthesis
model was given.** `build_prompt()` tells the writer each number is "vs. {club}'s players in
this position" (accurate -- `compute_fit_signal` always filters the reference squad to the same
position group). But `judge_llm.review()`'s comparison string just said "vs. {club} {number}",
dropping the qualifier -- so from the fact-checker's own vantage the comparison looked
team-wide, and it flagged the fit_read's correct, more specific phrasing as an unsupported
inference. Two renderings of the same data disagreeing with each other, not the model being
oversensitive. Fixed by making `judge_llm.py`'s string match `build_prompt()`'s wording exactly.

**Bug 2, found immediately after re-testing bug 1's fix: `judge_llm.review()` never received
`scout_notes` at all.** Same failure shape as the fit_signal bug from the v3 build (see above,
2026-09-17) -- the fact-checker flagged an accurate "the scout's own role notes describe
Haaland as..." sentence as inventing a source, because it was never shown the notes it was
supposed to be checking the attribution against. `review()`'s signature was simply missing the
parameter; the call site in `summarize_combined()` never passed it either. Fixed by adding
`scout_notes` to both the function signature and the `inputs` dict (mirroring how `fit_signal`
is already handled), and passing it through at the call site.

Re-ran the identical live case after both fixes: the two false-positive findings are gone from
the judge output, confirmed by reading the raw findings list, not just a score moving. One
finding remains (a NUMBERS check flagging derived per-90 figures for manual review) -- that one
looks legitimate, not a bug, and is working as designed ("may be legitimately derived; review
each," not a hard block). 176 tests still passing; no test coverage exists for `judge_llm.py`
directly since it needs a live API call, consistent with `judge_rules.py` carrying the
unit-tested hard gate and this module staying a soft, best-effort supplement.

## Track C2: does the 15/35 Fit label threshold mean anything? (2026-09-18, later still)

Reworking Track C (below) fixed its tooling and its question, but left the actual open item
from the v3 build untouched: `scoring.FIT_LABELS`' 15/35 percentile-point cutoffs were a
first-pass guess, explicitly flagged as "not eval-validated yet" in `scoring.py`'s own comment,
never checked against anything. Built as its own track (Track C2) rather than folded into
Track C, since it's a genuinely different question (is the threshold right, not does the number
move) -- discussed and agreed with the project owner before building.

No LLM/NewsAPI needed -- `eval/track_c2_capture.py` calls `compute_quality_signal` +
`compute_fit_signal` directly, same pattern as `track_a_capture.py`. 9 hand-picked cases, chosen
so the "right answer" doesn't need subjective human labeling: 6 self-reference cases (a player
vs. the actual club he plays for, expecting Hand-in-Glove Fit almost by definition) and 3
deliberate-mismatch cases (a player whose real style opposes a philosophy, expecting Completely
Different). Season 2023-2024 throughout, matching every other track.

Result: **2 of 9 matched their expected label.** Investigated why rather than treating this as
a flat "thresholds are wrong":

1. **Every defense-group case swung hard** (Valverde 35.2, Giménez 38.6, Dunk 41.9, Dias 16.0)
   vs. a much tighter spread for attack/midfield. Root cause is structural: `avg_abs_diff`
   averages the percentile gap across every *shared* component, and defense has exactly one
   (`defensive_actions_per90`) where attack has 4 and midfield has 2-3 -- so defense gets none
   of the smoothing averaging multiple metrics gives the other groups for free. Not a threshold
   problem; would need a second defensive metric to actually fix.
2. **Haaland vs. Man City and Kimmich vs. Bayern both landed "Somewhat Fits," not "Hand-in-
   Glove"** (17.1 and 16.0 -- both just past the 15 cutoff) despite being unambiguous standouts
   at their own clubs. This is the mechanism correctly measuring something real: a player who
   is *better* than his position's squad average -- which is exactly what makes him a standout
   -- will show a genuine gap from that average. The eval's own a-priori assumption
   ("self-reference should read Hand-in-Glove") was too strong for exactly the players most
   worth testing it on. Two multi-metric cases landing 1-2 points past the cutoff is a specific,
   actionable signal that 15 is probably too tight, not that the mechanism is broken.
3. **Casemiro vs. Bayern (`avg_abs_diff` 47.9, correctly "Completely Different")** shows the
   mechanism works as intended when a real, large, multi-dimensional gap exists across every
   shared metric -- the label response isn't broken, the boundary is just calibrated too
   aggressively at the low end.
4. **Adama Traoré vs. Man City landed "Hand-in-Glove," not the expected "Completely
   Different"** -- traced to a mistake in this eval's own case design, not the signal: the case
   was picked from his reputation as a weak-end-product winger rather than checked against his
   actual 2023-2024 numbers first, which turned out to show 100th-percentile assists and strong
   goals/xG that season. Disclosed plainly in the report rather than quietly swapped for a
   different player -- the same "verify against real data" principle this project applies
   everywhere else, turned on its own eval design this time.

Proposed in `eval/TRACK_C2_REPORT.md`, then applied the same day once flagged and confirmed:
raised the Hand-in-Glove cutoff from 15 to 20 in `scoring.FIT_LABELS`. Left the defense-group
volatility alone rather than special-casing its thresholds, since a second defensive metric
would be the real fix and that's a data-availability question, not a number to retune.

Re-ran all 9 Track C2 cases against the new threshold: **4/9 now match, up from 2/9** (Adeyemi,
Casemiro already matched; Haaland and Kimmich now join them). One case got worse in the
predicted direction: Rúben Dias vs. Dortmund moved from "Somewhat Fits" to "Hand-in-Glove Fit"
(his 16.0 diff now falls under the raised cutoff too), further from its expected "Completely
Different" -- the same structural defense-volatility issue (Finding 1) catching a case in that
same 16-17 band, exactly the tradeoff the report called out rather than a surprise. Test suite
updated (`tests/test_scoring.py`'s `_fit_label` boundary cases moved from 15/34.9 to 20/34.9),
176 tests passing.

## Track C reworked for the v3 architecture, and a real fabrication bug found by re-running it (2026-09-18)

The v3 rework (below) made Fit deterministic but never touched Track C's own tooling --
`eval/track_b_capture.py` still built its output record around a `fit_score` key that
`summarize_combined()` no longer returns at all (it returns `fit_signal` now). Caught before
any code changed: running `track_b_capture.py` with a philosophy set would have hard-crashed
with `KeyError: 'fit_score'`, and `track_c_repeat.py`/`score_track_c.py` layered on top of it
would have silently reported an always-`None` field, not stale data but no data.

Fixed the mechanical break: `track_b_capture.py` now calls `compute_fit_signal()` itself (same
call shape `scoutlite_combined.run()` uses) and records `fit_signal` in its JSON output.
`track_c_repeat.py`/`score_track_c.py` reworked around `fit_signal["label"]` instead of
`fit_score`, plus `tests/test_score_track_c.py` rewritten for the new record shape (168 -> 173
tests once the judge fix below is counted).

The bigger question was conceptual, not mechanical: Track C originally asked "does the LLM's
`fit_score` ever flip across identical reruns" -- a question that only makes sense when an LLM
picks the number. Fit is now pure math (`compute_fit_signal`, no LLM in its path at all), so
that question is resolved by construction, not by testing -- identical inputs are guaranteed
identical output every time. Reworked Track C to check the one thing that *can* still vary at
`temperature=0.3`: whether the LLM's prose explanation of the fixed label ever misrepresents it
(e.g. failing to name the actual reference club it was compared against).

Live-verified the reworked tooling with a 2-run smoke test (Erling Haaland, possession / high
line, vs. Manchester City) rather than trusting the unit tests alone -- consistent with how
every other v3 bug this project has found was caught by running the real pipeline, not by
imagining edge cases. Label came back stable both runs (expected) and the reference club was
named in the prose both times (expected) -- but the smoke test also surfaced a genuine live
bug: run 1's `fit_read` said *"The scout's own role notes frame this as a stylistic
question..."* despite no `--scout-notes` being passed at all. A real fabrication, not a
borderline judgment call.

Root cause: `build_prompt()`'s Fit instructions said "if the scout's role notes are present,
weave them into the explanation" -- phrased as a conditional for the *model* to evaluate,
rather than a fact the code already knows. The model apparently latched onto the genre
convention of scouting write-ups referencing role notes and invented some. Fixed by computing
`has_scout_notes` in code (the same boolean guard that already decides whether to include the
notes section in the prompt at all) and only including the "weave them in" sentence when notes
were actually given -- across all three Fit-instruction branches (signal computed, philosophy
given but signal unavailable, no philosophy). Also added a new deterministic
`judge_rules.py` HONESTY check (mirroring the existing "scout notes given but not attributed"
check, just inverted) that flags `fit_read` if it mentions "the scout's ... notes" when
`scout_notes` was never supplied -- defense in depth, in case this recurs in a different
phrasing the prompt fix doesn't happen to cover. Re-ran the same live case after the fix:
source_accuracy moved 64.3%/52.9% -> 73.3%/82.6%, and the fabricated sentence was gone from
both runs' `fit_read` text, confirmed by reading the raw JSON, not just by the judge score
moving.

`eval/TRACK_C_REPORT.md` got a 2026-09-18 addendum marking the original report as a historical
record of the pre-v3 mechanism (its finding -- 21/21 runs landed on `fit_score: 3` -- is
exactly what drove the v3 redesign) rather than rewriting it to pretend it was always about the
new architecture.

## v3: both Signals fully deterministic, reference-club Fit, a standing glossary (2026-09-17, later still)

The Tier 3 product redesign discussed after the v2 fixes -- Quality and Fit both now
deterministic, no LLM deciding either number. Design was worked out in conversation before any
code: possession-adjustment for Quality's team-context bias, a real reference club per
philosophy for Fit (replacing the LLM-judged number Track C found stuck at 3/5), qualitative
labels instead of bare 1-5s for both, and a standing "Understanding the Signals" glossary on
every brief.

**Quality (`scoring.py`):**
- **Possession-adjustment (PAdj)**, the standard sports-analytics fix for exactly the concern
  raised: a dominant-possession team's players face fewer defensive opportunities per match
  than an equal player at a team that defends more, so their raw defensive-action counts are
  naturally lower for reasons that have nothing to do with individual quality. New
  `_team_possession_map()` (team possession%, from a soccerdata call not previously used in
  this codebase -- verified live before writing any code) and `_possession_adjust()`. Applied
  only to `defensive_actions_per90` (attack output isn't adjusted -- PAdj is specifically an
  established correction for defensive volume, not a general one). Deliberately a simpler
  application than a full industry PAdj: only the individual value is adjusted, not the whole
  comparison population -- disclosed as a known simplification, not presented as fully
  rigorous. `compute_quality_signal()` now returns both `avg_percentile`/`label` (adjusted) and
  `raw_avg_percentile`/`raw_label` (unadjusted) side by side.
- **Verified live on the exact case that motivated this**: Rodri's defensive-actions percentile
  moved 57 (raw) -> 88 (PAdj) once corrected for how little Manchester City's dominant
  possession actually requires him to defend.
- **Labels replace the bare 1-5**: `percentile_to_label()`, same cutoffs as `percentile_to_1_5`
  -- Below Rotation / Depth Option / Solid Starter / Strong Starter / World Class.

**Fit (`scoring.py`, `scoutlite_combined.py`, `judge_rules.py`, `judge_llm.py`):**
- **`compute_fit_signal()`**: deterministic, not LLM-judged. Reuses Quality's own percentile
  components for the target player (no recomputation), builds a reference profile by
  percentile-ranking a real club's current squad (same position group, same metrics) against
  their own league's population, then compares. Output is a 3-tier label -- Hand-in-Glove Fit /
  Somewhat Fits / Completely Different -- from the average absolute percentile-point difference
  across shared metrics (first-pass thresholds, not eval-validated yet -- no labeled sample
  exists for this new mechanism).
- **`REFERENCE_CLUBS`**: one real club per philosophy combination, picked in conversation, not
  an abstract statistical template -- Borussia Dortmund (vertical/high-line), Real Madrid
  (vertical/mid-block), Atlético Madrid (vertical/low-block), Manchester City
  (possession/high-line), Bayern Munich (possession/mid-block), Brighton
  (possession/low-block). FBref and Understat don't always agree on a club's name (confirmed
  empirically) -- Dortmund is "Dortmund" on FBref, "Borussia Dortmund" on Understat; Atlético is
  accented on FBref, not on Understat -- so each entry carries both spellings.
- **The LLM's job narrows to explaining an already-decided label**, not producing one.
  `build_prompt()`'s Fit section now hands the model the exact percentile comparison and asks
  for one paragraph explaining it -- explicitly forbidden from inventing a different score or
  contradicting the given label. `parse_synthesis()` no longer parses a "Fit: X/5" line out of
  the response at all (there's nothing to parse -- the number never comes from the model).
  `judge_rules.check()`'s fit-score structural checks (was it a valid 1-5 int, was one produced
  without philosophy) are gone, since there's no LLM-invented number left to validate that way
  -- replaced with a new check verifying the fit_read actually names the reference club it was
  computed against.

**Two real bugs found via live smoke-testing** (not caught by the unit test suite, since
neither exercises the full pipeline end-to-end):
1. Forgot to import `compute_fit_signal` in `scoutlite_combined.py` -- caught on the very first
   live CLI run.
2. `judge_llm.review()` wasn't given the new `fit_signal` data at all, so its fact-checking call
   correctly-from-its-own-limited-view flagged a completely accurate, well-grounded fit_read's
   percentile comparisons as "fabricated" -- it had never been shown the numbers it was judging
   against. Fixed by passing `fit_signal` into `review()` and including its comparison in the
   fact-checker's own view of "the available data," with an explicit note that these numbers
   were computed by the tool, not invented by the model being checked.
3. A third, smaller issue from the same live runs: the new Fit instructions never told the
   model to actually name the player, and a generated brief came back with neither paragraph
   naming Haaland at all (triggering a real FOCUS finding). Fixed by explicitly requiring the
   player be named at least once in the Fit explanation.

None of these three were hypothetical edge cases -- all three surfaced from generating one real
brief and reading the output, the same "run it and look" pattern that found every other real
bug across this whole eval-and-fix arc.

**`docx_report.py`**: Signals block drops the old "Combined X/10" line entirely (doesn't mean
anything once Fit is categorical) in favor of "Quality: <label> · Fit: <label> vs. <club>".
Quality's raw vs. adjusted percentile shown side by side when they differ. Section 4 now shows
the exact reference-club comparison table alongside the LLM's prose. New **"6. Understanding
the Signals"** section -- static, identical on every brief, explaining what each signal
measures, the label scale, and the same pace/pressing caveat, with the actual reference club
for THIS brief's philosophy named where relevant. `FIT_SCOPE_CAVEAT`'s wording updated -- the
original (written for the old LLM-judged 3/5) no longer made sense once Fit could vary; the
underlying gap (no pace/pressing data, ever) is still fully real and still disclosed.

`app.py` mirrors every pipeline change (computes `fit_signal` before calling
`summarize_combined`, same Signals/comparison display as the docx). 168 tests total across the
suite (up from 132), covering the new scoring functions, prompt assembly, judge_rules'
replaced fit checks, and docx rendering of both new signal formats.

## Re-ran the eval set against v2, verified the fixes actually moved real data (2026-09-17, later same day)

Tier 2 item from EVAL_REPORT.md's recommendations, done immediately rather than left open. Not
a blind re-run of everything -- checked which of the 4 fixes actually touch a layer worth
re-testing, and skipped the rest rather than spend API calls for no new information:

- **Track B**: fix #4 (hype regex) changes what the judge FLAGS, not the brief TEXT itself, so
  re-ran `judge_rules.check()` against all 14 existing captures' already-saved text -- zero
  network calls needed. Result: no rule-based findings changed on any of the 14. The one real
  "overstated" miss from labeling (Haaland's "Headlines touch on his rivalry...") doesn't
  contain any of the new hype keywords, so this specific fix wouldn't have caught it -- honest
  finding, not the fix failing, just confirms hype detection needs the LLM supplement for
  subtler cases as already documented. (First comparison attempt was flawed -- compared the
  stored MERGED rule+LLM findings against a rule-only recheck, which made everything look
  different for the wrong reason; redone by filtering both sides to only rule-based findings
  by their category prefix before comparing.)
- **Track C**: none of the 4 fixes touch the LLM synthesis prompt or the Fit-score computation
  itself (only docx rendering and a separate judge check) -- re-running the full 21-run sweep
  would almost certainly reproduce `fit_score: 3` at real API cost for no new information.
  Skipped; the FIT_SCOPE_CAVEAT's rendering was already smoke-tested against real data when it
  was built.
- **Track A1**: refreshed `assigned_group` for all 15 real captures against the fixed
  `classify_position_group()`, keeping every human-judgment column (`expected_group`,
  `defensible`, `notes`) untouched and noting the mechanical change inline. **Exact-match rate:
  67% -> 80%** (10/15 -> 12/15) -- Rice and Rodri no longer mismatches; the remaining 3
  (Bruno Fernandes, De Bruyne, Ødegaard) are the attacking-mid cases already judged
  "defensible," unaffected by design.
- **Track A2**: re-captured Rice and Rodri (the only two players whose position group actually
  changed) via `track_a_capture.py` -- a real, substantively different Quality computation,
  not just a relabel, since they're now scored against midfield metrics (key passes + xA +
  defensive actions) instead of defense-only (defensive actions alone). Rodri: **3/5 -> 4/5**
  (avg percentile 48.3 -> 63.1), now including his 70th-percentile key-passing output --
  directly answers what the labeler flagged at the time ("defense isn't the only thing... city
  do have a lot of the ball"). Rice: stayed 4/5 but the number is now backed by three
  dimensions of his game instead of one. Updated `track_a_quality_spotcheck.csv` with the new
  numbers and a note; deliberately left `reputation_tier`/`surprising` for the labeler to
  reconsider given the metric set genuinely changed, not silently flipped.

## Post-eval v2: all 4 Tier 1 fixes from EVAL_REPORT.md (2026-09-17)

Planned as three tiers (Tier 1 = clear-cut, no design debate; Tier 2 = needs more eval data;
Tier 3 = bigger product calls, left for the project owner). Built all 4 Tier 1 items:

**1. Fixed `classify_position_group()`'s DF-MF ambiguity.** `DF-MF` with a `CM`/`DM` secondary
tag (Rodri, Declan Rice) now classifies Midfield instead of Defense; `DF-MF` with `FB`/`CB`/
`WB` (Wan-Bissaka, Trent Alexander-Arnold) is unaffected. Verified against all 15 real Track A
captures: exact-match rate against the labeler's own `expected_group` improved **67% → 80%**
(10/15 → 12/15). The 3 remaining mismatches (Bruno Fernandes, De Bruyne, Ødegaard -- all
`FW-MF` attacking mids) are exactly the ones already judged "defensible" during A1 labeling,
left untouched on purpose -- that's a coarse-but-honest simplification, not the bug this fix
targets. Left `eval/track_a_position_survey.csv` as the historical record of the eval that
found the bug rather than rewriting it post-fix.

**2. Added a "specialist" caveat to the Quality signal.** New pure function
`scoring._specialist_caveat(components)`: when a player's component percentiles spread more
than 40 points (Haaland's real case: 100th/99th on goals/xG vs. 56th/53rd on assists/xA), the
brief now says so explicitly instead of silently flattening a specialist's peak trait into an
average. Rendered in `docx_report.py` right after the existing component breakdown line.

**3. Added a permanent Fit-signal scope caveat.** Given Track C's evidence (21/21 runs across
all 6 philosophy combinations landed on 3/5), every brief with a philosophy assessed now
carries a fixed disclosure that Fit can't see pace/sprint/pressing data -- so a score at or
near 3 means "insufficient data," not "neutral fit." `docx_report.FIT_SCOPE_CAVEAT`.

**4. Added a hype-keyword detector to `judge_rules.py`.** New `_FORBIDDEN_HYPE` regex
(electric, generational, world-class, sensational, phenomenal, unstoppable, and similar)
joins the existing forbidden-content checks. Directly targets Track B's 50%-recall gap on
"overstated" -- won't solve tonal detection in general (nothing regex-based will), but raises
the floor on the most blatant, unambiguous cases the same way the existing checks catch their
own categories.

All 4 covered by new tests (`tests/test_scoring.py`, `tests/test_docx_report.py`,
`tests/test_judge_rules.py`) -- **132 tests total** across the suite, up from 113.

Tier 2 (grow Track B's sample before trusting its rates; re-run A1/A2 labeling after this fix
to get fresh numbers) and Tier 3 (should Fit stay numeric at all; is sourcing pace data worth
pursuing; a non-averaging Quality redesign) are still open, left for the project owner's call.

## Track C complete: 7 cases, all 6 philosophy combinations, a formal report (2026-09-16, later still)

Rounded Track C out to full coverage: added Casemiro (vertical/low-block), Rodri
(vertical/mid-block), and Virgil van Dijk (possession/high-line) -- the 3 philosophy
combinations the previous 4 cases hadn't touched, so every one of the 6 possible
(2 in-possession × 3 out-of-possession) combos has now been tested at least once. 7 cases, 3
runs each, 21 runs total. Result unchanged and now fully confirmed across the whole
combination space: every single run landed on `fit_score: 3`.

Van Dijk's first run is worth a specific mention: scored exactly 80% (the pass threshold, not
a clean 100%) and surfaced real findings before shipping -- a FOCUS gate (name missing from
the draft), a misleading headline reframe, comments wrongly attributed to a manager who
doesn't manage this club in the supplied data, and an unsupported stat inference. None of it
touched `fit_score`. Useful evidence for the writeup: the judge loop is doing real work in
these same captures, it's specifically the Fit number that never moves.

Wrote the whole thing up as a standalone document rather than another NOTES.md entry --
**`eval/TRACK_C_REPORT.md`** -- since this is a complete, citable finding now (methodology,
full 7-case results table, the cross-case evidence, the judge-findings supporting evidence,
interpretation, and a "what would actually change this" section), not something still in
progress. `eval/README.md`'s Track C section trimmed down to point at it instead of
duplicating the writeup inline.

## Track C: a real scope limitation, not just run-to-run instability (2026-09-16, later still)

Expanded Track C from 1 case (Haaland, 3 runs, previous entry) to 4 cases, 12 runs total:
De Bruyne (possession/mid-block), Wan-Bissaka (possession/low-block), and -- picked
specifically to be an on-paper mismatch -- Trent Alexander-Arnold (known for attacking output,
not recovery pace/defensive positioning) against `vertical, fast transitions / high line,
counter-press`, a philosophy that specifically punishes that profile.

Within-case stability held on all 4 (every run in a case matched every other run in that case,
prose reworded itself as expected from `temperature=0.3`) -- but the finding that actually
matters is across cases, not within them: **all 4 cases landed on `fit_score: 3`, zero
exceptions, 12 for 12 individual runs.** Not from boilerplate reasoning -- each `fit_read`
cites different real stats and reaches 3 by a different path. Trent's reasoning names the cause
directly: *"There is no pace or sprint data listed, so the speed-dependent transition fit
central to this club's philosophy cannot be assessed at all."*

Read plainly: ScoutLite's actual sources (FBref counting stats, Understat xG) never carry pace,
sprint, or pressing-volume data -- exactly what philosophy fit hinges on. The model is doing
the right thing by refusing to guess (`build_prompt()` explicitly tells it to lean toward 3
rather than a confident extreme when data's insufficient) -- but the consequence is that the
Fit signal may be structurally unable to ever move off neutral for ANY player against ANY
philosophy, given today's inputs. This is a real scope limitation to state plainly (matching
this project's other documented limitations), not something more reruns would resolve -- the
actual fix is sourcing pace/pressing data from somewhere, or being upfront in the product that
Fit is close to a fixed neutral until that happens.

## Mbappé empty-population bug fixed (2026-09-16, later same day)

The bug flagged in the previous entry ("still open, pending a decision on the fix") -- fixed.
`compute_quality_signal()` in `scoring.py` now only adds a component to the average when its
reference population is non-empty (checked at each of the 5 population-building call sites:
goalkeeper's save%, attack's 4 Understat metrics, midfield's 2 Understat + 1 FBref-misc metric,
defense's 1 FBref-misc metric). An entirely-empty population (Mbappé's exact case -- 4 games
into `2026-2027`, nobody league-wide had crossed `MIN_MINUTES_FOR_POPULATION` yet) now correctly
falls through to the existing `if not components: return None`, same as an uncovered league. A
*partially* empty case (only one of a midfield player's two source populations being empty)
now just drops that one component instead of losing the whole signal -- a genuine improvement,
not just a bug fix, since averaging in a fake 50 was never right even when other real
components existed alongside it.

Couldn't reproduce the original empty-population state live anymore -- more games have been
played since Mbappé's capture, so his real reference population is no longer empty. Verified
the fix two ways instead: (1) two new mocked-population tests in `tests/test_scoring.py`
(113 tests total) covering the all-empty case (returns `None`) and the partially-empty case
(drops just the empty component, keeps the real one); (2) re-ran Mbappé's actual capture against
today's live (now-populated) data -- **5/5**, `avg_percentile: 85.7`, driven by real
100th-percentile goals and xG per90, which is what a genuinely elite striker's profile should
look like, and matches the "World's Elite" tier the labeler picked before ever seeing the
(buggy) 3/5. `eval/track_a_quality_spotcheck.csv`'s Mbappé row updated with the corrected
numbers and a note explaining the change; deliberately left the `surprising` flag itself as the
labeler's own call to revisit rather than silently flipping it.

## Track B labeled and scored for real (2026-09-16)

First full labeling pass on `track_b_labels.csv` (all 70 sentences), plus the A2 quality
spotcheck (all 13). Two things came out of checking the results, before trusting the numbers:

**Scorer bug, same shape as the earlier judge_rules bug: found by actually running real data
through it.** The labeler filled in y/n columns as full sentences ("Yes, same role, I think
it's correct" / "No, I think Rodri should fall on the Casemiro line..."), not bare "y". Both
`score_track_a.py` and `score_track_b.py` did an exact-string match, so every thoughtful answer
was silently read as false -- reported 0% defensible on Track A when the real number was 87%,
and (once `human_label` also turned out to be free text, not an enum) a mechanically-forced
100% false-positive rate on Track B, since `caught_by_judge` had been uniformly "Y" across all
70 rows. Fixed: `_truthy()` reads intent off the first word now; `score_track_b.py` gained a
keyword-based `_normalize_label()` for the five human_label categories. Regression tests added
directly from the real labeled data in both test files (111 tests total across the suite).

**The real Track B result, once the numbers could be trusted:**
```
Judge recall on "overstated": 50% (1 of 2)
False-positive rate on grounded: 7% (5 of 68)
```
Lands on the hypothesis this eval was built to test: the rule-based judge catches factual
overreach reasonably well, misses plain narrative hype dressed as an ordinary sentence. Small
sample so far (2 real overstated cases) -- a first data point, not a verified rate.

Getting there required actually tracing a disagreement to the sentence level rather than
trusting either side: the labeler's first pick for Haaland's one real exaggeration and the
judge's own LLM-supplement findings pointed at three different sentences in the same brief.
Quoted each finding's exact text back to its source sentence to make it concrete -- final
call: the judge over-flagged two fine, honestly-hedged sentences (2 of the 5 total false
positives) and missed the real one (a genuine recall miss, not caught anywhere). Also relabeled
one Declan Rice sentence from "overstated" to "grounded" on the same principle used earlier in
this project (Haaland/Trent honestly disclosing an unrelated headline is correct behavior, not
hype) -- mentioning a Ballon d'Or nomination for an unrelated player, while explicitly noting
it isn't about Rice, isn't hallucination or exaggeration.

Mechanically corrected 62 more grounded rows where `caught_by_judge` said "Y" but no judge
finding's quoted text corresponded to that specific sentence at all (verified by literal text
overlap, not a judgment call) -- left the remaining 5 rows, where a finding's quoted text is a
100% verbatim match to the sentence, for the labeler's own confirmation, since that's a real
judgment call about whether the judge's flag was fair. Confirmed as fair (all 5 are judge
over-flagging fine hedging, i.e. real false positives) rather than relabeled.

`eval/track_a_quality_spotcheck.csv` also fully labeled (13/13) -- see the separate writeup
above/below for the three distinct findings that came out of it (averaging dilutes a
specialist's peak trait; position misclassification directly breaks the signal for
Rodri/Trent; an empty reference population early in a season silently produces a fake-looking
neutral score for Mbappé -- the last one still open, pending a decision on the fix).

## Track C scaffolded ahead of order, on request (2026-09-15)

Project owner asked to see Track C built before finishing B's/A's labeling, despite the
earlier B > A > C priority call -- fine, it's cheap and doesn't block the labeling work, which
is still open on both.

`track_b_capture.py`'s `capture()` gained two optional params, `out_dir` and `out_name`
(default `None`, fully backward-compatible -- Track B's own captures are unaffected). Rather
than duplicate the whole pipeline for "run the same inputs N times," `eval/track_c_repeat.py`
just calls `capture()` in a loop with those overridden, `force_refresh=False` throughout so
FBref/Understat data is fetched once and reused -- the only thing meant to vary run to run is
the LLM call itself. `eval/score_track_c.py` groups the resulting `track_c_samples/*__runN.json`
files by player+philosophy and reports whether `fit_score` stayed identical across them (pure
aggregation, `tests/test_score_track_c.py`, 108 tests total across the suite now).

**First real result:** Haaland, vertical/high-line, 3 runs -- `fit_score` landed on 3 every
time; `fit_read`'s wording visibly reworded itself run to run while citing the same stats and
reaching the same read. Exactly what B4's premise predicted (temperature drifts prose, not the
score), on the first case tried. One case, three runs -- not enough to call B4 "passed", just a
first data point pointing the expected direction.

## Track A scaffolded: position-group survey + Quality face-validity spot check (2026-09-14)

Built, under `eval/`: `track_a_capture.py` (bio + stats + Quality signal only -- no LLM, no
NewsAPI, so much cheaper than Track B's), `build_position_survey.py` (A1, completes `TESTS.md`
B5) and `build_quality_spotcheck.py` (A2, completes B3's "Ronaldo test"), plus
`score_track_a.py` with two pure aggregation functions covered by
`tests/test_score_track_a.py` (101 tests total across the whole suite now).

Sample: 11 of the 15 captures are reused directly from Track B's already-captured data (zero
extra FBref calls -- same bio/stats/quality fields Track B already saved). The other 4 were
added specifically to close a real gap: every single `FW-MF`/`DF-MF` player already in the
sample classifies as attack/defense (first-listed code wins), so there was no genuine
`midfield` case at all. Added Rodri, Martin Ødegaard, and Bruno Fernandes -- all confirmed
misclassified the same way (De Bruyne's known pattern, not a one-off) -- and Casemiro, the
first clean `MF`-primary case in the whole sample. Notably, Rodri -- a Ballon d'Or-level
defensive midfielder -- gets filed under **Defense**, not Midfield, since FBref lists him
`DF-MF (CM-DM)` with DF first. Worth stating plainly once A1 is actually labeled: the pattern
looks less like "occasional versatile-player edge case" and more like "any midfielder with
real attacking or defensive involvement doesn't stay classified as one."

Both CSVs (`track_a_position_survey.csv`, `track_a_quality_spotcheck.csv`) are built and ready
-- labeling (`expected_group`/`defensible` for A1, `reputation_tier`/`surprising` for A2) is
still open, same as Track B's CSV.

## Philosophy-set captures close out the Track B sample (2026-09-14)

The 11 batch captures all skipped the Fit-score path entirely -- no club philosophy was ever
set, so `Fit: X/5` and its reasoning had zero coverage. Added 3 more: Haaland (vertical, fast
transitions / high line, counter-press), De Bruyne (slow, methodical possession / mid block,
hybrid), Wan-Bissaka (slow, methodical possession / low block, counter) -- all reusing players
already in the sample rather than adding new ones, to keep FBref/NewsAPI calls low.

`track_b_capture.py`'s filename slug now appends the philosophy when one is set
(`<slug>__<philosophy>.json`), so these land alongside the plain no-philosophy capture for the
same player instead of overwriting it. That in turn meant `build_labeling_sheet.py` needed a
fix too -- it was grouping/counting by player NAME, so the two captures of e.g. Haaland were
indistinguishable in the CSV (and the printed "N briefs" count silently deduplicated them).
Added `capture_id` (the actual filename stem) and `philosophy` as their own CSV columns.

All 3 new captures scored 100% and landed `fit_score: 3` (neutral / insufficient signal) with
visibly hedged language ("stats offer limited signal for assessing fit..."). Flagged in
`eval/README.md` as specifically worth a labeler's judgment -- genuinely warranted caution
given how sparse the inputs are, or a safe-default score of 3 the model reaches for regardless
of input? Not something a regex can tell apart; exactly the kind of thing this eval exists for.

Sample is now 14 captures / 70 sentences, ready to label.

## Two real judge bugs, found by running the Track B batch for real (2026-09-12, later still)

Ran the Track B capture script (previous entry) across 10 of the 12-case batch's players
(Vinicius Jr and the garbage-name case are designed to fail before a brief exists, so skipped
-- see `eval/README.md`). This immediately paid for itself: Virgil van Dijk and Declan Rice
both scored far below the other cases (65% and 20%, vs. everyone else's 90%). Investigating
found two distinct bugs in `judge_rules.py`'s quote-extraction regex (`_QUOTED`) -- both false
positives, not real hallucination:

1. **A bare apostrophe read as an opening quote.** Rice's news read said "...a piece on Martin
   Ødegaard's resurgence..." -- the possessive apostrophe was misread as opening a quote, which
   then swallowed everything up to the next real quote mark as one giant "invented quote"
   spanning most of the paragraph. First fix: exclude bare apostrophes from the delimiter set
   entirely (only straight/curly double quotes delimit a quote now), allow apostrophes inside
   the quoted content instead of treating them as a boundary.
2. **Trivially short real quotes left their marks dangling.** Re-running Van Dijk after fix #1
   surfaced a second, subtler bug: real quotes shorter than the grounding check's own 15-char
   floor (a headline's single word "found", or "decision time") were skipped by the regex
   entirely at that length -- which meant their own quote marks never got consumed, and were
   free to pair up with each OTHER across the plain narrative in between, manufacturing one
   long fake quote out of real prose. Fix: the regex now pairs every quote mark in order
   regardless of length (with a generous upper cap against a malformed string); the 15-120 char
   floor is applied afterward, only to decide which real quotes are worth grounding-checking.

**Verified against the real data that found them**, not just synthetic cases: Rice went from
20% → 90% after fix #1 (fully explained by the bug -- the only remaining finding was a
legitimate, minor formatting one). Van Dijk went 65% → 90% after fix #1, then a fresh
regeneration (same inputs, new LLM call) hit bug #2 and dropped to 40% -- fixed, back to 90%.
Then swept all 11 captures' stored judge scores against a re-check with the fixed code: 4 more
were silently affected (David Raya 20→90, Kevin De Bruyne 23.3→90, Trent Alexander-Arnold
40→90, Vinicius Junior 20→90) -- all re-captured. 3 new regression tests added directly from
these real cases (`tests/test_judge_rules.py`, 94 tests total) rather than only from synthetic
examples, per this project's habit of turning a bug found on real output into a permanent test.

All 11 captures now score 90% on one pass -- the honest reading is that this is a real, correct
result (none of the 12-case batch ever set a club philosophy, and the resulting "no philosophy
given, but the fit read doesn't say 'not assessed'" formatting nit is the one finding every
capture shares), not evidence the judge is lenient. It does mean the current sample has zero
diversity on the pass/confidence-warning axis -- the planned philosophy-set additions
(`eval/README.md`) are now the only way to exercise that path at all.

## Eval scaffolding for Track B, priority order set (2026-09-12, later same day)

Discussed prioritizing the three eval tracks below: **Track B (hallucination/hype) matters
most, Track A (Quality signal validity) follows, Track C (Fit-signal consistency) is parked**
for whenever there's time to test it -- project owner's call. Scaffolded Track B accordingly;
Track A stays a written design for now (see `eval/README.md`), Track C untouched.

Built, under `eval/`:
- `track_b_capture.py` -- runs the same library calls `scoutlite_combined.py`'s CLI does, but
  keeps the intermediate data (judge findings, articles with real URLs, the exact stats the
  LLM saw) as JSON instead of only rendering a `.docx`.
- `build_labeling_sheet.py` -- flattens every captured JSON into one CSV, one row per sentence
  in "What People Say" + "Signals & Fit Read", pre-filled with that brief's judge findings for
  context. Automates the tedious part; the actual `human_label` judgment call stays manual.
- `score_track_b.py` -- once labeled, computes the judge's recall per issue category
  (invented/overstated/verdict-language) and its false-positive rate on sentences called
  grounded. Pure aggregation, covered by `tests/test_score_track_b.py` against a synthetic
  CSV so the scoring logic is verified independent of whether real labeling has happened yet.
- `eval/README.md` -- the full workflow, plus Track A's and Track C's plans.

Smoke-tested end to end on Erling Haaland (2023-2024, cached): capture → 5-sentence CSV →
scorer correctly reports "0/5 labeled, n/a" on the unlabeled sheet. One real, useful thing
surfaced by just running it once: the LLM's news synthesis explicitly declined to link an
unnamed-player headline to Haaland ("does not name Haaland") rather than assuming -- exactly
the caution this eval exists to check for, caught for free on the first sample.

Next: extend the sample by reusing the 12-case test batch's players (keeps NewsAPI/FBref calls
low) plus 2-3 new captures with a club philosophy set (that batch never exercised the Fit-score
path), then actually label and score it.

## Sources in the brief + a planned human eval of the judge loop (2026-09-12)

Prompted by planning where to eval the pipeline (Quality signal comparisons, and whether the
LLM-written sections hallucinate or hype). Two things came out of that discussion.

**Shipped: real sources in the .docx.** The brief claimed to be "a research brief a scout can
check," but couldn't actually be checked -- headlines were plain bulleted text (no link, no
publisher, no date), and neither the FBref stats page nor the Understat xG/xA page was linked
anywhere. Fixed:
- Each headline in "What People Say" is now a real hyperlink to its article, with publisher +
  date alongside (`docx_report.py` gained `_add_hyperlink` -- python-docx has no built-in
  hyperlink support, so this hand-builds the `<w:hyperlink>` OOXML run, the standard recipe).
- A new "5. Sources" section links the FBref profile the stats came from and the Understat
  profile the xG/xA came from.
- `understat_xg.find_player_xg` now also returns `understat_url` (Understat's league JSON
  actually includes a per-player `id` -- `understat.com/player/<id>` -- that just wasn't being
  captured before).
- `player_url` threaded through `scoutlite_combined.run()` and `app.py` into `build_docx`.
- `tests/test_docx_report.py` added (docx generation is deterministic given its inputs, so it
  fits the existing pure-layer suite) -- covers linked/unlinked headlines, the Sources section
  in both populated and empty states, and that the raw URL doesn't leak into the stats table
  as a junk row.

**Planned, not built: calibrate the judge against a human.** The rule-based judge's 80%
source-accuracy threshold has never been checked against actual human judgment -- we know what
it catches (numeric grounding, invented quotes, forbidden hype/verdict language, honesty
gates), but not its false-negative rate (real hype it lets through) or false-positive rate
(fine sentences it flags). This is the deferred eval-harness recommendation, and TESTS.md's
B3-B7 rows were never run. Protocol, when there's time to run it:
1. Sample ~15-20 real generated briefs spanning the edge cases: Understat-covered vs. -uncovered
   league, philosophy given vs. not, a thin-news week, an ambiguous FBref/Understat name match.
2. A human independently labels every sentence in "What People Say" and "Signals & Fit Read"
   against the underlying stats/xG/articles as grounded / invented / overstated (hype on a real
   fact) / verdict-language -- without looking at what the automated judge already flagged.
3. Score the judge's findings against those labels (precision/recall), which tells us whether
   80% is actually the right cut, not just a number that felt right.

Also worth noting for the Quality signal: it's an intra-league comparison only (same league +
season + position group, never cross-league or cross-position) -- see `scoring.py`'s own
docstring and `describe_quality()` for the exact stats compared per group. A 4/5 in Ligue 1 and
a 4/5 in the Premier League are not directly comparable in absolute terms, which is implicit
but easy to misread across players from different leagues.

## pytest suite + Understat graceful degradation (2026-09-11)

Two follow-ups from the "build recommendations" review, done together.

**Understat graceful degradation.** A timeout inside Understat was killing whole brief runs.
`understat_xg.py` now has an `UnderstatUnavailable` exception and a `fetch_league_players_safe`
wrapper; `get_player_xg` catches `(requests.RequestException, ValueError)` and returns `None`.
`scoring.py`'s Quality signal catches `UnderstatUnavailable` and drops just the Understat-based
components (still scores from FBref-misc / keeper data) instead of aborting. CLI and app now say
"xG/xA not available (league not covered, no name match, or Understat unreachable) — continuing
without it". Verified with a monkeypatched timeout: attacker path returns `None` cleanly, a
defender still scored from FBref data.

**Test suite (`tests/`, 77 tests, `pytest -q`, ~2s, no network).** Covers the pure layer:
`judge_rules` checks (the richest target — structure gates, numeric grounding, invented-quote
detection, honesty gates, forbidden-content regexes, player-focus), percentile / per-90 /
1–5 mapping math, position classification, FBref↔Understat name matching (incl. the compound-
surname fallback and the documented abbreviation gap), cache TTL + roundtrips (temp DB),
`build_prompt` assembly across the xG / articles / philosophy / scout-notes / prior-findings
branches, and `parse_synthesis` marker splitting. Plus offline HTML-extractor regression guards
against captured fixtures (`tests/fixtures/haaland_page.html`, `danny_ward_search.html`) — these
extractors have had real bugs (bio parsing, the search-item split), so they now have guards.

To make this testable, `parse_synthesis(text)` was extracted as a pure function out of
`_synthesize_once` in `scoutlite_combined.py` (no behaviour change; `_synthesize_once` now just
calls it). Two test-side bugs found and fixed while writing: a `_check` helper that couldn't
pass `xg=None` explicitly (needed a sentinel), and an over-broad substring assertion.

## LLM-as-judge loop (2026-09-10)

The Vision doc's judge concept, built -- but re-scoped once we discussed it: the LLM is a
*small* part, deterministic rules are the bulk. Rationale: trusting an LLM to check an LLM
shares blind spots; the verifiable stuff should be verified.

**`judge_rules.py` (the bulk)** -- deterministic checks on the two LLM-authored paragraphs
against the exact structured inputs, computing the source-accuracy % that actually gates the
loop (the Vision doc's 80% threshold, now *computed* not asked):
- Structure (hard gates): both marker sections present, `Fit: X/5` well-formed, non-empty,
  sane length, fit-score matches whether philosophy was given.
- Numeric grounding: every figure in the paragraphs must be in the input data (stats/misc/
  keeper/xg dicts, headline text, the fixed "28 days" window). Ungrounded numbers are *flagged
  for review*, not hard-failed -- they may be legitimately derived (per-game rates etc.).
- Headline grounding: quoted phrases in the news read must overlap a real provided headline.
- Honesty gates: no xG/xA figures if `xg` was None; "not assessed" present if no philosophy;
  scout notes attributed ("the scout notes...") if notes were provided.
- Forbidden content: transfer-value language, future-performance speculation, verdict language.
- Player focus: the target player's name appears somewhere in the two paragraphs.

**`judge_llm.py` (the small part)** -- one narrow structured call (DeepSeek for now; the
natural first place for model tiering) covering only what rules structurally can't: is a stat
interpretation a *fair* reading or an overreach, is the news characterization faithful, subtle
misframing. Returns severity-tagged findings; only a "major" one blocks. Fails soft (empty
findings on any API/parse error -- rules are the hard gate, this is a supplement).

**The loop (`summarize_combined`)**: synthesize -> rules + LLM judge -> if it clears 80% with
no hard-fail and no "major" LLM finding, ship. Otherwise revise with all findings as feedback,
max 2 iterations, then ship anyway with `judge['confidence_warning']` set and the outstanding
findings attached -- never hard-fail and hand the scout nothing (per the Vision doc).

**Bug caught during testing:** `judge_llm.review()` originally didn't receive the headlines,
so it concluded "no news data was provided" and flagged every news claim as unsupported --
a false-positive cascade that failed an otherwise-fine brief through both revision passes.
Fixed by passing `articles` in; also tightened the severity rubric so style nitpicks stay
"minor".

**Verified:** rule checks unit-tested (clean brief -> 100%, deliberately dirty brief -> 0%
with every check firing, hard-fail gates on empty/malformed sections); full CLI + UI runs on
a normal player pass at ~90-100% on iteration 1 with the LLM surfacing genuine *minor* framing
nuances; confidence-warning rendering verified in the .docx via a synthetic failing judge
result (bold warning at the top + bulleted findings, data tables unaffected); a persistent
"Automated judge: N% ... passed/below threshold" line shows near Signals in the app.

## SQLite staging cache (2026-09-10)

Concept 1 from the architecture discussion, built. Deliberately a plain SQLite table, not a
vector DB -- our data is structured/numeric (per-90 stats, player identity), which needs exact
lookups, not semantic retrieval. `cache.py`, three tables: `player_pages`, `understat_populations`,
`search_results`.

**Two lanes, one cache**, per the project owner's design: Quick mode (default) serves cached
data when fresh enough; Fresh mode (opt-in -- a checkbox in the UI, `--fresh` on the CLI) always
fetches live but still writes through to the cache afterward. This also wires into soccerdata's
own `no_cache` option, so Fresh mode is consistent across every source `scoring.py` touches, not
just our three tables.

**Freshness policy** differs by table, deliberately:
- `player_pages` gets the smart treatment: a cached page is served regardless of age if the
  season being asked for is provably NOT the latest one in that cached copy (immutable historical
  data, no TTL needed). Otherwise a flat 24h TTL applies. When no season is specified at all, the
  stale path conservatively re-fetches rather than guessing it's safe.
- `understat_populations` and `search_results` get a flat TTL each (24h, 7 days) -- simpler on
  purpose. Understat's pull is one cheap request with no ban risk, so the main value of caching
  it is avoiding same-session redundant re-fetches, not protecting a rate limit the way FBref's
  cache does.

**Verified live, not just unit-tested:**
- Cold fetch (`search_player` + `get_player_page`) for Haaland: ~23s. Same lookup again: 0.00s
  for both -- the single-match auto-redirect case caches the page directly inside
  `search_player` itself, so the follow-up `get_player_page` call never re-fetches at all.
- Fresh mode correctly bypassed a valid, freshly-cached entry and re-fetched live (~22s).
- Simulated a 25h-old ("stale") cache entry directly in the DB and confirmed all three branches:
  requesting a historical season served instantly (0.07s) despite the stale timestamp;
  requesting the current season correctly triggered a live re-fetch (~24s); requesting with no
  season specified also conservatively re-fetched rather than risk serving stale current data.
- Full CLI run for a cached player: 27.8s cold -> 4.3s warm (a ~6.5x speedup; the remaining
  4.3s is NewsAPI + the LLM call, unrelated to caching).
- Regression: the lookup-confirmation feature (Danny Ward multi-match) still fails cleanly and
  resolves correctly via `--player-url` with caching layered underneath.

`scoutlite_cache.db` (WAL mode, for more graceful behavior under the CLI+UI concurrent-access
pattern this project actually uses) is gitignored -- it's a local cache, not part of the repo.

## Lookup confirmation step (2026-09-10)

Architecture discussion led to three ideas: (1) a locally-cached "staging table" instead of
live lookups every time, (2) upload a player photo for visual identification, (3) show every
FBref search match and require explicit confirmation before proceeding, instead of silently
taking the first result. Decided: (2) is out of scope (identification would rely on an LLM's
ungrounded training-data memory of what public figures look like -- the one feature that
would be pure guessing with no source to check, plus real biometric/privacy weight, same
category of concern that already got Reddit dropped). (1) is being redesigned as a plain
SQLite cache (not a vector DB -- our data is structured/numeric, vector search is for
semantic retrieval over text, not looking up exact per-90 stats) -- not started yet. (3) is
built, this entry.

**What changed:** `scoutlite.py`'s `fetch_player_page_html` (which silently took the first
FBref search result -- the exact risk we'd been testing around with "Danny Ward" rather than
fixing) is replaced by `search_player()` (returns every candidate FBref found, with enough
info to disambiguate -- name, alt name, nationality, active years, clubs -- never auto-picks)
and `fetch_player_page_by_url()` (fetches a specific, already-confirmed URL). Single-match
FBref auto-redirects skip the confirmation step entirely (zero added friction for the common
case, since there's nothing to disambiguate) -- confirmation only appears when there's a real
choice to make.

- **`app.py`**: multi-match results now render as a radio selection with the disambiguating
  info, gated behind a "Confirm selection" button before Step 2 (season/notes/philosophy)
  appears.
- **`scoutlite_combined.py`**: multi-match now fails cleanly with the full candidate list and
  their FBref URLs printed, plus a new `--player-url` flag to specify the exact one directly
  (consistent with the CLI's design as a non-interactive/scriptable tool, and reusing last
  week's clean-error-message fix rather than a raw traceback).
- Verified all four paths live: CLI ambiguous name (clean listing + exit 1), CLI
  `--player-url` override (resolves the exact chosen candidate), UI ambiguous name (radio
  confirmation, correct resolution), UI unambiguous name (unchanged, no added friction).

## 12-case test batch (2026-09-08)

Ran the full test plan for real (11 succeeded, 1 -- a garbage name -- correctly failed with no
brief produced, as designed). Full matrix, per-case results, and the three findings (Wan-Bissaka's
5/5, the abbreviation-mismatch bug being broader than previously documented, and a CLI-vs-UI
error-handling gap) are tracked in **[TESTS.md](TESTS.md)**, not duplicated here.

## Bug found via a real generated brief (2026-09-01)

Mbappé's brief came back with Quality "not available" and xG/xA "not available -- Understat
doesn't cover this player's league" -- misleading, since La Liga *is* one of the 6 leagues
Understat tracks. Root cause: Understat lists him as **"Kylian Mbappe-Lottin"** (compound
surname, no accent); the search was "Kylian Mbappe" (no "Lottin"). Exact-match-after-
normalization legitimately found no match, because there genuinely wasn't one under that
exact string -- but the player was really there.

Fixed in `understat_xg.py`'s `find_player_xg`: when the exact match fails, fall back to a
token-subset match (every word in the search name present in the candidate's name, order-
independent, hyphens normalized to spaces first). Regression-tested against every previously-
verified exact-match case (Haaland, De Bruyne, Van Dijk) -- unchanged. Mbappé now resolves
correctly: Quality 5/5 (elite finisher, 25 goals from 25.8 xG), xG/xA populated.

This is the same "cross-source name matching is fragile" risk flagged multiple times earlier
in this project, now caught for real on an actual generated brief rather than in testing --
a good argument for periodically spot-checking real output, not just the players used during
development.

**Systematic follow-up check (same day):** pulled all 5 covered leagues' full Understat
populations (2,775 players) and checked every hyphenated name (74 found) plus several
"commonly-known-short-form" players (Vinícius Júnior, João Félix, etc.) against the fix.
Result: the compound-surname fix has zero regressions and zero false positives found. But it
does NOT catch abbreviation-style mismatches -- "Vinicius Jr" still fails to match "Vinícius
Júnior" ("jr" != "junior" as a token, no amount of subset-matching helps). Three other
apparent "misses" (João Félix, Neymar, Randal Kolo Muani) turned out to be invalid test
cases -- those players simply aren't in any of the 5 leagues' current squads, correctly
returning `None`, not a matching bug.

**Decision: stop engineering more name-matching edge cases, surface verification instead.**
Chasing every abbreviation/nickname variant is unbounded scope for diminishing return. Added
`understat_matched_name` to the `xg` dict (the literal name Understat matched against), and
surfaced it as an explicit ⚠️ warning -- in the Streamlit UI (`app.py`, next to the Advanced
Stats table) and in the `.docx` brief itself (`docx_report.py`, same location) -- so the
scout can eyeball whether the match is really who they meant, rather than trust a fuzzy match
silently. Consistent with the project's "fail visibly, don't silently guess" principle.

Running notes for the write-up, kept as decisions happen (per the original brief).

## Technical Vision doc (2026-08-22) — resolved open questions

- **"Years of interest" scope:** single season only, deliberately. Multi-season input risks the
  LLM conflating/hallucinating across years' stats -- not worth the risk for the accuracy gain.
  Matches the season-picker already built (defaults to most recent, user can pick an older one).
- **Word doc build approach:** built directly with `python-docx`, not LLM-drafted into a
  template. Bio and stats/performance sections are pure structured data -> rendered as real
  tables with zero LLM involvement (no transcription risk). LLM is reserved for the two
  sections that actually need synthesis: "what people say" (news read) and "signals & fit
  read" -- matches the doc's own stated division of labor (LLM for synthesis/judging only,
  deterministic pipeline for data).
- **Transfermarkt robots.txt discrepancy:** the vision doc says "exact scope not independently
  verified," but this session actually did pull real robots.txt content (via a Wayback Machine
  snapshot) and found specific rules -- wildcard `Allow: /` but named blocks on
  `ClaudeBot`/`anthropic-ai`/etc. Flagged to the project owner; doc phrasing left as their call.

## Quality/Fit scoring engine (`scoring.py`) — built 2026-08-30

**Position groups revised from the original doc spec** after confirming two of the planned
inputs don't exist on free data sources:
- Progressive passes/carries (Midfield) and a true duel-success-rate (Defense) are NOT on
  FBref's free pages -- confirmed via FBref's own "On this page" table-of-contents (lists only
  Standard/Shooting/Playing Time/Misc/Keeper, no Passing/Possession/Defensive Actions/GCA).
- Double-checked Understat too, one level deeper than the earlier xG/xA check: the individual
  player page's HTML template shows `touch90`/`int90`/`Pas90` column headers, but the actual
  `getPlayerData` API response behind that table never populates those fields (checked on a
  center-back specifically, where they'd matter most). Dead template labels, not real data.
- Revised groups, each metric's percentile computed against its own single source's full
  population (deliberately not merged player-by-player -- see scoring.py docstring for why):
  - Attack: goals/90, assists/90, xG/90, xA/90 (Understat)
  - Midfield: key_passes/90, xA/90 (Understat) + (interceptions+tackles_won)/90 (FBref misc)
  - Defense: (interceptions+tackles_won)/90 (FBref misc) -- substitutes for the unavailable
    duel-success-rate
  - Goalkeeper: save% (FBref keeper), already a rate, no per-90 needed

**Reference population source:** Understat's whole-league JSON pull (already built for xG/xA)
covers Attack/Midfield's Understat-sourced metrics in one fast request. FBref's misc/keeper
whole-league pulls use `soccerdata` (disk-cached after first fetch per league+season).

**Two real bugs caught and fixed during testing, not left for later:**
1. Understat's `position` field is a space-separated set of every position played that season
   (e.g. `"F M S"`), not a single primary tag -- an exact-match filter (`== "F"`) left only 2
   forwards in the entire league population instead of ~100+. Fixed to containment matching.
2. No minimum-minutes floor on any reference population meant small-sample players (a few
   minutes, one fluky stat) could dominate percentile rankings -- e.g. Haaland's real assists
   output landed at the 0th percentile before the fix. Added a 450-minute (~5 match) floor
   across all three populations.

**Known, disclosed (not silently corrected) limitations:**
- Position classification takes FBref's first-listed position code (e.g. "FW-MF" -> attack).
  For versatile players this doesn't always match football intuition -- Kevin De Bruyne is
  classified as Attack, not Midfield, because FBref lists FW first for him. This is the same
  "position vs. role" tension the doc's Section 4a already names; scout notes are the intended
  channel for role nuance the position-group score can't capture.
- Van Dijk (an elite CB) scored low (2/5) on the Defense group specifically because Liverpool's
  dominant possession means fewer defensive actions are required of him -- a live example of
  the doc's own named "context confound" (team game model), not a scoring bug. Not corrected
  for in v1, per the doc's own instruction to disclose rather than fix this.
- Only the 5 top-European leagues are covered (Understat's + `soccerdata`'s overlap); other
  leagues return `quality: None`, shown as "not available," never a fabricated number.

## Task 1 — Data source verification

### FBref — cleared, built against
- Scraping permitted, rate-limited: Sports Reference blocks sessions over 10 requests/minute,
  violations risk up to a 24h block.
- Sits behind Cloudflare's bot challenge (Turnstile). Plain `requests`/`curl`, `cloudscraper`,
  and standard headless/headed Playwright/Selenium are all blocked — Cloudflare flags the
  `navigator.webdriver` automation fingerprint itself. Only `seleniumbase` in UC mode
  (undetected Chrome driver) gets through reliably.
- Pacing implemented: 6.5s + up to 1.5s jitter before every request. Independently matches
  the maintained `soccerdata` FBref scraper's hardcoded `rate_limit = 7`.
- Verified live against 3 players: Erling Haaland (well-known), Danny Ward (ambiguous name,
  tests the multi-match disambiguation path), Macaulay Langstaff (obscure, thin sample size
  but accurate).

### Transfermarkt — off-limits (deliberate call)
- Direct fetch blocked by AWS WAF CAPTCHA (not attempted to bypass). Confirmed via a
  2026-02-03 Wayback Machine snapshot instead.
- `robots.txt`: wildcard (`User-agent: *`) technically allows generic crawling (`Allow: /`),
  but explicitly and by-name disallows `ClaudeBot`, `anthropic-ai`, `GPTBot`, `ChatGPT-User`,
  `PerplexityBot`, `CCBot`, `Omgilibot`, `wget`. `bingbot` explicitly allowed (3s crawl-delay).
  No path-level rules anywhere — it's all site-wide.
- Decision: treat as off-limits. Routing around the named block via a generic user-agent
  would go against the site's clearly expressed intent for AI agents specifically.

### FotMob — dropped (closed, not revisited)
- `robots.txt` disallows automated access to data endpoints (confirmed against
  `/api/data/playerData`).

### Reddit — scraping closed, official API (free tier) used instead
- `robots.txt`: blanket `Disallow: /` for `User-agent: *`, no exceptions. Stricter than
  Transfermarkt's case — total disallow, not a named-bot carve-out.
- Data API Terms (verified via archived snapshot, 2026-08-11, since live fetch of
  reddit.com/redditinc.com pages is blocked for this tool):
  - Must not misrepresent/mask user agent or OAuth identity (§2.8) — no UA-spoofing workaround.
  - Numeric rate limits live in Developer Documentation, not the legal terms (couldn't fetch
    that page). Third-party reports (unverified against primary docs): ~100 QPM per OAuth
    client, non-commercial free tier; self-service app approval closed in late 2025
    ("Responsible Builder Policy") — new apps go through manual review now.
  - §2.4 / §3.2 explicitly restrict using Reddit content "to train a machine learning or AI
    model" without rightsholder permission. Feeding scraped posts into a one-off LLM prompt
    isn't "training," but it's the same AI-hostile posture as the robots.txt block on
    ClaudeBot/anthropic-ai — worth flagging, not just a formality.
- Built: `reddit_sentiment.py` via PRAW, read-only OAuth (client_credentials-style, no
  user login needed). Needs a registered "script" app at reddit.com/prefs/apps.

### X/Twitter — off-limits
- `robots.txt` blanket-disallows all agents, same posture as Reddit.
- **Flag:** the file contains unusual prose comments arguing (via a misapplied RFC 9309
  citation) that `/i/api/` "stays crawlable" — but those `Allow` lines sit only inside the
  Googlebot/Bingbot/facebookexternalhit groups, not the wildcard group that actually governs
  a generic agent. Read as a probable injection attempt aimed at an AI parsing the file;
  not acted on.
- Paid-only API for any real read access beyond posting.

### NewsAPI — used for news headlines (v1 build)
- `robots.txt` disallows `/v1/` and `/v2/` from crawlers — standard index-avoidance for an
  API-first product, not a restriction on calling the API with a registered key.
- Developer (free) tier: 100 requests/day, **explicitly dev/test only — not licensed for
  production or internal production use**, 1-month article lookback, CORS limited to
  localhost.
- Built: `news_fetch.py` — title + description per article, VADER sentiment per headline.

## V2 build potential (not built, just noted)

- **Tavily, as an alternative/addition to NewsAPI for news**: free tier is 1,000
  credits/month (vs. NewsAPI's 100/day hard cap), no stated production restriction (vs.
  NewsAPI's explicit dev-only clause), and — most relevant — has an explicit `topic="news"`
  search mode described as tuned for "politics, sports, and major current events," plus an
  `include_raw_content` option that returns full extracted article text rather than just a
  title/snippet. Built for feeding LLM pipelines directly, which fits the eventual
  synthesis step better than NewsAPI's headline-only response. Deliberately not swapped in
  now — NewsAPI stays as the v1 choice; Tavily is flagged for whenever the news step moves
  from "list headlines" to "synthesize into the report."

## Architecture (current)

```
player name (CLI arg or Streamlit text box)
    │
    ▼
FBref search → player page   [seleniumbase UC-mode headless Chrome,
    │                          6.5s + jitter pacing before each request]
    ▼
parse "Standard Stats" table → most recent season row
    │
    ▼
one DeepSeek-V3 call → paragraph summary
    │
    ▼
console / Streamlit output + output/<slug>.txt
```

`reddit_sentiment.py` and `news_fetch.py` are standalone scripts (same CLI-arg pattern),
proven independently before any wiring into the main pipeline — not yet combined with
`scoutlite.py`/`app.py`.

## Status

| Piece | Built | Live-tested |
|---|---|---|
| `scoutlite.py` (FBref stats + bio, DeepSeek) | Yes | Scraping + bio parsing verified live (Haaland, De Bruyne); LLM call pending `DEEPSEEK_API_KEY` |
| `understat_xg.py` (xG/xA lookup) | Yes | Verified live (Haaland, De Bruyne); graceful `None` confirmed for non-covered leagues |
| `app.py` (Streamlit UI, wraps scoutlite.py) | Yes | Pending `DEEPSEEK_API_KEY` |
| `reddit_sentiment.py` | Yes | **Parked** (see below) |
| `news_fetch.py` | Yes | Pending `NEWSAPI_KEY` |

## Understat — built, access override is deliberate (2026-08-22)

`understat_xg.py` fetches understat.com despite its `robots.txt` being a blanket
`Disallow: /` for every agent (checked earlier same session) — no named-bot carve-out like
Transfermarkt, no official API like Reddit. This is a conscious override, made explicitly by
the project owner after being shown the finding and the Reddit/Twitter precedent of respecting
blanket disallows. Not an oversight or a "found a loophole" situation.

Mechanically: the site moved off the old "regex a `<script>` tag for embedded JSON" pattern
(what most public scraper tutorials describe) onto a real JSON endpoint —
`GET understat.com/getLeagueData/<league>/<year>` — that needs a session cookie from the
league page plus a `Referer` header, but no browser automation and no Cloudflare wall. Only
covers 6 leagues (top-5 European + Russian Premier League); players outside those return
`None` cleanly rather than erroring.

FBref's `#meta` block (player bio: full name, position, foot, height/weight, birth
date/place, nationality, club, contract expiry) is now also parsed in `scoutlite.py` — same
page fetch as the stats table, no new access question, just an added parser.

## Reddit — parked (2026-08-22)

Deprioritized, not removed. `reddit_sentiment.py` and the `REDDIT_*` `.env` entries stay in
place, but Reddit is off the active path for now.

Reasoning: getting a working integration requires Reddit's own consent, not just registering
a key — the "Responsible Builder Policy" closed self-service OAuth app signup in late 2025,
so every new app (free or paid) now sits in a manual approval queue with no guaranteed
turnaround. That's a meaningfully different (and more convoluted) dependency than FBref
(no approval, just pacing) or NewsAPI (instant free-tier signup). Combined with the Data API
Terms' AI-hostile posture already noted above, Reddit isn't worth the wait for a course-project
timeline. Revisit if/when an approved app is actually in hand.
