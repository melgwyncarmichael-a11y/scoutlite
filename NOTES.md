# ScoutLite — Build Notes

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
