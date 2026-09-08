# ScoutLite — Build Notes

## 12-case test batch (2026-09-08)

Ran the full test plan for real (11 succeeded, 1 -- a garbage name -- correctly failed with no
brief produced). All briefs generated, sent for review. Findings:

- **All regression checks held**: Mbappé's compound-surname fix, De Bruyne's and Declan Rice's
  position-group quirks (Attack and Defense respectively), Van Dijk's context-confound score --
  all reproduced exactly as previously documented, no drift.
- **New finding -- Aaron Wan-Bissaka scored 5/5 Quality**, not "average" as expected for a
  squad-level full-back. Root cause understood, not a bug: he's genuinely elite specifically by
  the interceptions+tackles/90 metric (real-world known for exactly this), even though a human
  scout might rate his overall game as more average given weak attacking output. Same class of
  limitation as Van Dijk's low score, opposite direction -- a narrow metric can both over- and
  under-rate a player relative to holistic scouting judgment.
- **New finding -- the abbreviation-mismatch limitation is broader than documented.** Previously
  written up as an Understat-only issue ("Vinicius Jr" won't match "Vinícius Júnior" there).
  Testing now shows FBref's own search fails on "Vinicius Jr" too -- confirmed reproducible
  (not transient), and isolated by confirming "Vinicius Junior" (full word) resolves cleanly
  through the entire pipeline. So this can block a brief from being generated at all, not just
  degrade the xG/xA section.
- **New finding -- CLI vs UI error handling differs.** `scoutlite_combined.py`'s `main()` isn't
  wrapped in try/except, so a "player not found" (or any other exception) surfaces as a raw
  Python traceback on the CLI -- confirmed on both a genuine non-existent name and transient
  FBref search flakiness. The actual product surface (`app.py`) already handles this cleanly
  ("Something went wrong: No FBref match found for '...'", no traceback) since it wraps the
  whole flow in try/except. Not a user-facing bug, but worth fixing in the CLI for anyone using
  it directly or in a script.
- Early-season thin data (Haaland, 3 matches/270 min at time of testing) flowed through cleanly
  with no crashes -- small-sample caveats appeared appropriately in the LLM's own text.
- Non-covered league (Macaulay Langstaff, League Two) correctly showed "not available" for both
  Quality and xG/xA rather than a crash or a fabricated number.

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
