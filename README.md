# ScoutLite

**A player research brief for a scout to weigh — not a scouting verdict.**

ScoutLite pulls a football player's stats, background, and recent news into one Word document,
alongside a Quality signal and a Fit signal that a scout can weigh against their own judgment.
Both are fully deterministic (non-AI, percentile-based) as of v3 — the LLM never decides either
one, only explains it in prose. It's a research/data layer that accelerates a scout's
homework — it doesn't replace the scout's own call. Built as a course project for PE6201.

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
Quality signal (a label, e.g. "World Class") — non-AI, percentile-rank
against real players in the same league/season/position group, possession-
adjusted where relevant. No LLM involved in this number.
        │
        ▼
Fit signal (a label, e.g. "Hand-in-Glove Fit") — non-AI, compares this
player's percentile profile against a real reference club's current squad
for your chosen philosophy (e.g. Borussia Dortmund for vertical/high-line).
No LLM involved in this one either.
        │
        ▼
NewsAPI: recent headlines (last 28 days)
        │
        ▼
One DeepSeek-V3 call — synthesizes only the two things that actually need
judgment: a read on the news, and a plain-English explanation of the
already-computed Fit label. Everything else is rendered straight from data.
        │
        ▼
Judge loop — deterministic rules check the two written paragraphs against
the exact inputs (every number grounded? quoted headlines real? no forbidden
verdict/transfer-value/hype language?), plus one narrow LLM check for unfair
interpretation. Below 80% → revise, max 2 passes, then ship with a visible
confidence warning rather than hand back nothing.
        │
        ▼
Word document (.docx): Signals, Who He Is, Stats & Performance,
What People Say, Signals & Fit Read, Sources, Understanding the Signals
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

`requirements.txt` pins every direct dependency to the exact version this project is built and
tested against. For a byte-for-byte reproducible install (including every transitive
dependency), use `requirements-lock.txt` instead: `.venv/bin/pip install -r requirements-lock.txt`.

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

**Comparing candidates** (2+ players for the same role, one brief instead of several):
```bash
python3 scoutlite_compare.py "Erling Haaland" "Alexander Isak" "Ollie Watkins" \
  --season "2023-2024" --in-possession possession --out-of-possession high_line \
  --scout-notes "need a mobile penalty-box striker who can press from the front"
```
Runs the exact same pipeline (Quality, Fit, news, judge loop) once per candidate, then lays out
a summary table plus each candidate's full detail in one document. An ambiguous name is skipped
with a clear message rather than guessed — resolve it individually via `scoutlite_combined.py
--player-url` first, then compare the rest. CLI only for now; not yet in the Streamlit app.

## Caching — Quick vs. Fresh

Lookups are cached locally (SQLite, `cache.py`) so a repeat lookup for the same player is
near-instant instead of paying FBref's ~7-9s pacing cost again. Past-season data is cached
indefinitely (it can't change); the current season gets a 24h freshness window.

- **Quick mode (default):** serve cached data when it's fresh enough
- **Fresh mode (opt-in):** always pull live — a checkbox in the app, `--fresh` on the CLI —
  still updates the cache afterward either way

## Known, disclosed limitations

- Quality signal's position grouping takes FBref's first-listed position code — an attacking
  midfielder (`FW-MF`) still lands in Attack, a deliberate simplification found reasonable by
  eval labeling (`EVAL_REPORT.md`); the specific case that wasn't reasonable (`DF-MF` defensive
  midfielders landing in Defense instead of Midfield) is fixed as of v3
- Quality's possession-adjustment (PAdj) corrects for a dominant team's players facing fewer
  defensive opportunities, but only adjusts the individual value being scored, not the whole
  comparison population — a simpler application than a full industry PAdj, disclosed as such
  rather than presented as fully rigorous (`scoring._possession_adjust`)
- Fit compares a player's statistical profile against a real reference club's current squad —
  it measures whether the *shape* of the numbers matches, not tactical fit itself, since no
  ScoutLite source measures pace, sprint speed, or pressing intensity (every brief with a Fit
  result says so explicitly)
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
