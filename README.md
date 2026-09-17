# ScoutLite

**A player research brief for a scout to weigh — not a scouting verdict.**

ScoutLite pulls a football player's stats, background, and recent news into one Word document,
alongside a Quality signal (1-5) and a Fit signal (1-5) that a scout can weigh against their own
judgment. It's a research/data layer that accelerates a scout's homework — it doesn't replace
the scout's own call. Built as a course project for PE6201.

Try it instantly with no local setup: **[Open the Colab demo](ScoutLite_Colab_Demo.ipynb)** (run
it directly on [colab.research.google.com](https://colab.research.google.com) by uploading the
notebook, or opening this repo's copy there).

## What it does

```
player name (+ optional season, your own short role notes, club philosophy)
        │
        ▼
FBref: season stats, bio/background, defensive & goalkeeping stats
        │
        ▼
Understat: xG/xA (when the league is covered)
        │
        ▼
Quality signal (1-5) — non-AI, percentile-rank against real players
in the same league/season/position group. No LLM involved in this number.
        │
        ▼
NewsAPI: recent headlines (last 28 days)
        │
        ▼
One DeepSeek-V3 call — synthesizes only the two things that actually need
judgment: a read on the news, and a Fit signal (1-5) against your club's
philosophy + your role notes. Everything else is rendered straight from data.
        │
        ▼
Judge loop — deterministic rules check the two written paragraphs against
the exact inputs (every number grounded? quoted headlines real? no forbidden
verdict/transfer-value language?), plus one narrow LLM check for unfair
interpretation. Below 80% → revise, max 2 passes, then ship with a visible
confidence warning rather than hand back nothing.
        │
        ▼
Word document (.docx): Signals, Who He Is, Stats & Performance,
What People Say, Signals & Fit Read, Sources
```

Every headline in "What People Say" is a real hyperlink to its article (with publisher and
date); "Sources" at the end links back to the FBref profile and Understat profile the stats
came from — a scout can check any claim without leaving the document.

## Data sources and why each one is used the way it is

| Source | Used for | Access note |
|---|---|---|
| **FBref** | Season stats, bio, defensive/goalkeeping stats | Scraping permitted but rate-limited (paced ~6.5-8s/request); sits behind a Cloudflare bot-challenge that only an undetected-browser driver gets past |
| **Understat** | xG/xA, feeds the Quality signal | `robots.txt` blanket-disallows scraping — used here on an explicit, deliberate override; see `NOTES.md` |
| **NewsAPI** | Recent headlines (last 28 days only, free-tier limit) | Official API, free Developer tier (dev/test use) |
| Transfermarkt, FotMob, Reddit, X/Twitter | Not used | Each ruled out for a documented reason — see `NOTES.md` |

Full reasoning, every access decision, and every bug found along the way (with fixes) are in
**[NOTES.md](NOTES.md)** — kept as a running log through the whole build, not written after the fact.

## Setup

```bash
git clone <this-repo-url>
cd ScoutLite
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# then fill in .env: DEEPSEEK_API_KEY (required), NEWSAPI_KEY (optional -- runs fine without it)
```

Or just double-click **`Launch ScoutLite.command`** (macOS) — it bootstraps the venv on first run.

## Usage

**Streamlit app** (recommended — season picker, role notes, club philosophy dropdowns, live signals):
```bash
.venv/bin/streamlit run app.py
```

**CLI** (same pipeline, scriptable):
```bash
python3 scoutlite_combined.py "Erling Haaland" \
  --season "2025-2026" \
  --scout-notes "tall, can play as a 9 or 10, fast feet, gets in behind often" \
  --in-possession vertical --out-of-possession high_line
```

If a name matches more than one player (common names like "Danny Ward"), the CLI won't guess —
it prints every candidate with enough info to tell them apart and asks you to re-run with
`--player-url` pointing at the one you mean. The Streamlit app shows the same choice as a
selection step instead of failing.

## Caching — Quick vs. Fresh

Lookups are cached locally (SQLite, `cache.py`) so a repeat lookup for the same player is
near-instant instead of paying FBref's ~7-9s pacing cost again. Past-season data is cached
indefinitely (it can't change); the current season gets a 24h freshness window.

- **Quick mode (default):** serve cached data when it's fresh enough
- **Fresh mode (opt-in):** always pull live — a checkbox in the app, `--fresh` on the CLI —
  still updates the cache afterward either way

## Known, disclosed limitations

- Quality signal's position grouping takes FBref's first-listed position code — versatile players
  can land in an unexpected group (e.g. a box-to-box midfielder classified as Attack)
- A low Quality score can reflect a dominant team's system as much as individual quality (not
  corrected for — stated as a caveat directly in every generated brief)
- Name-matching between FBref and Understat handles compound surnames but not abbreviations
  ("Vinicius Jr" won't match "Vinícius Júnior") — the generated brief always shows exactly which
  name it matched, so this is visible and checkable, not silent
- Only the top-5 European leagues have a Quality signal (Understat + soccerdata's overlap)

## Tests

```bash
.venv/bin/python -m pytest -q
```

A `pytest` suite (`tests/`) covers the pure, deterministic layer — the rule-based judge checks,
percentile / per-90 math, position classification, FBref↔Understat name matching, cache TTL
logic, prompt assembly, and synthesis parsing — plus HTML-extractor regression guards run
offline against captured FBref fixtures (`tests/fixtures/`). No network or API keys needed.

See `NOTES.md` for the full build log, including bugs found and fixed, and every access decision
with its reasoning. See **[`EVAL_REPORT.md`](EVAL_REPORT.md)** for the evaluation results —
does the Quality signal mean what it claims, does the LLM hallucinate or hype, is the Fit
signal consistent — with the real numbers, bugs the eval process found and fixed, and what
would actually move each result further (full detail and raw data under `eval/`). See
**[`CHANGELOG.md`](CHANGELOG.md)** for a practical, non-technical summary of what changed and
what you'll actually notice in a generated brief, release by release.
