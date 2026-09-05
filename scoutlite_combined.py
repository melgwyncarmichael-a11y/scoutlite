#!/usr/bin/env python3
"""
ScoutLite combined pipeline: one player name -> FBref (stats + bio) + Understat (xG/xA, when
the league is covered) + NewsAPI (recent headlines, last 28 days) -> one DeepSeek-V3 call ->
one player research brief (a data/research layer for a scout, not a scouting verdict).

Reuses each source's already-proven functions rather than duplicating logic:
- scoutlite.py: fetch_player_page_html, extract_latest_season, extract_player_bio
- understat_xg.py: get_player_xg (returns None if the league isn't one Understat tracks)
- news_fetch.py: fetch_articles (returns [] if none found; genuinely recent only, not
  season-long -- NewsAPI's free tier caps lookback at ~1 month)

Understat access note: understat.com's robots.txt blanket-disallows all scraping. Fetching it
here is a deliberate, explicit override made by the project owner -- see NOTES.md.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

from docx_report import build_docx
from news_fetch import LOOKBACK_DAYS, fetch_articles
from scoutlite import (
    extract_keeper_stats,
    extract_latest_season,
    extract_misc_stats,
    extract_player_bio,
    fetch_player_page_html,
)
from scoring import compute_quality_signal
from understat_xg import get_player_xg

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

ROLE_NOTES_MAX_CHARS = 200  # short, adjective-style role notes -- not a full report


NEWS_MARKER = "###WHAT_PEOPLE_SAY###"
FIT_MARKER = "###SIGNALS_AND_FIT_READ###"


def build_prompt(
    player_name: str,
    stats: dict,
    xg: dict | None,
    articles: list[dict],
    misc: dict | None = None,
    keeper: dict | None = None,
    scout_notes: str | None = None,
    philosophy: dict | None = None,
) -> str:
    """Bio and stats are rendered as tables directly from data elsewhere -- no LLM restatement,
    no transcription risk. This prompt only asks for the two things that genuinely need
    synthesis: a read on recent news, and a fit signal against the club's philosophy."""
    stats_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in stats.items())
    sections = [f"Player: {player_name}", f"\nSeason stats ({stats.get('season', 'unknown season')}):\n{stats_lines}"]

    if keeper:
        keeper_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in keeper.items())
        sections.append(f"\nGoalkeeping stats (same season):\n{keeper_lines}")

    if misc:
        misc_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in misc.items())
        sections.append(f"\nDefensive/discipline stats (same season):\n{misc_lines}")

    if xg:
        xg_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in xg.items())
        sections.append(f"\nAdvanced stats (expected goals/assists, same season):\n{xg_lines}")
    else:
        sections.append(
            "\nAdvanced stats (xG/xA): not available -- Understat doesn't cover this player's league."
        )

    if articles:
        headlines = "\n".join(f"- {a.get('title', '')}" for a in articles[:8])
        sections.append(
            f"\nRecent news headlines (last {LOOKBACK_DAYS} days only -- NOT a full season of "
            f"coverage, do not treat as season-long context):\n{headlines}"
        )
    else:
        sections.append(f"\nRecent news (last {LOOKBACK_DAYS} days): none found.")

    if scout_notes and scout_notes.strip():
        notes = scout_notes.strip()[:ROLE_NOTES_MAX_CHARS]
        sections.append(
            "\nScout's own short role notes (subjective, capped free text from a human scout who "
            "has watched this player -- captures ROLE, e.g. how they're actually used on the pitch, "
            "which stats alone don't show; not verified data, do not fact-check or contradict it, "
            f"just incorporate it as the scout's observation):\n{notes}"
        )

    has_philosophy = philosophy and (philosophy.get("in_possession") or philosophy.get("out_of_possession"))
    if has_philosophy:
        style_desc = " / ".join(v for v in philosophy.values() if v)
        sections.append(f"\nClub philosophy to assess fit against: {style_desc}")

    instructions = [
        "You are ScoutLite, generating two short sections of a player research brief -- a "
        "data/research layer FOR a scout, not a scouting verdict. Using ONLY the information "
        "listed below, produce exactly two labeled sections, in this format:\n\n"
        f"{NEWS_MARKER}\n"
        "One short paragraph reading the recent news (last 28 days). If none is relevant, say so "
        "plainly rather than inventing significance. Do not treat this as season-long context.\n\n"
        f"{FIT_MARKER}\n"
    ]

    if has_philosophy:
        instructions.append(
            f"First line MUST be exactly \"Fit: X/5\" where X is your integer 1-5 fit signal for a "
            f"club playing {style_desc}, based ONLY on the stats already listed above (1 = poor fit, "
            f"3 = neutral/insufficient data to tell, 5 = excellent fit). Then, on a new paragraph, "
            f"explain that score using ONLY those stats (e.g. defensive actions relate to pressing "
            f"demands, key passes/crosses relate to possession play). Explicitly say when the "
            f"available stats aren't sufficient to judge a given aspect (e.g. no pace/sprint data "
            f"here, so speed-dependent transition fit can't be assessed) rather than guessing -- "
            f"when in doubt, score closer to 3, not a confident extreme. If the scout's role notes "
            f"are present, weave them into the explanation as the scout's own observation, clearly "
            f"attributed, not verified fact. This is a fit SIGNAL for the scout to weigh, never a "
            f"verdict."
        )
    else:
        instructions.append(
            "First line MUST be exactly \"Fit: not assessed\" (no club philosophy was specified). "
            "Then, on a new paragraph, note the scout's role notes if present, clearly attributed "
            "as the scout's own observation, not verified fact."
        )

    instructions.append(
        "\n\nDo not invent or infer any fact, stat, or event not listed below. Do not speculate "
        "about transfer value, potential, or future performance. Never present anything as a "
        "conclusion or verdict -- these are signals for the scout to weigh."
    )

    body = "\n".join(s for s in sections if s)
    return "".join(instructions) + "\n\n" + body


def summarize_combined(
    player_name: str,
    stats: dict,
    xg: dict | None,
    articles: list[dict],
    misc: dict | None = None,
    keeper: dict | None = None,
    scout_notes: str | None = None,
    philosophy: dict | None = None,
) -> dict:
    """Returns {'news_synthesis': str, 'fit_read': str} -- the two sections that need LLM
    synthesis. Bio/stats/news-list are rendered as tables directly from data, not through here."""
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    prompt = build_prompt(player_name, stats, xg, articles, misc, keeper, scout_notes, philosophy)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    text = response.choices[0].message.content.strip()

    news_synthesis, fit_read = "", ""
    if NEWS_MARKER in text and FIT_MARKER in text:
        news_synthesis = text.split(NEWS_MARKER, 1)[1].split(FIT_MARKER, 1)[0].strip()
        fit_read = text.split(FIT_MARKER, 1)[1].strip()
    else:
        # Model didn't follow the marker format -- surface the raw text rather than lose it.
        news_synthesis = text

    fit_score = None
    fit_score_match = re.match(r"Fit:\s*(\d)/5", fit_read)
    if fit_score_match:
        fit_score = int(fit_score_match.group(1))
        fit_read = fit_read[fit_score_match.end():].strip()
    elif fit_read.lower().startswith("fit: not assessed"):
        fit_read = fit_read[len("Fit: not assessed"):].strip()

    return {"news_synthesis": news_synthesis, "fit_read": fit_read, "fit_score": fit_score}


def main():
    parser = argparse.ArgumentParser(
        description="Combined ScoutLite pipeline: FBref + Understat + NewsAPI -> one summary"
    )
    parser.add_argument("player", help="Player name, e.g. 'Erling Haaland'")
    parser.add_argument("--season", help="Specific season to report on, e.g. '2024-2025' (default: most recent)")
    parser.add_argument("--scout-notes", help="Your own short role notes (capped, adjective-style)")
    parser.add_argument("--in-possession", choices=["vertical", "possession"], help="Club philosophy: in-possession axis")
    parser.add_argument("--out-of-possession", choices=["high_line", "low_block", "mid_block"], help="Club philosophy: out-of-possession axis")
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("DEEPSEEK_API_KEY is not set. Add it to .env in this project folder.")

    philosophy = {
        "in_possession": {
            "vertical": "vertical, fast transitions",
            "possession": "slow, methodical possession",
        }.get(args.in_possession, ""),
        "out_of_possession": {
            "high_line": "high line, counter-press",
            "low_block": "low block, counter",
            "mid_block": "mid block, hybrid",
        }.get(args.out_of_possession, ""),
    }

    print(f"Fetching FBref data for '{args.player}'...")
    url, html = fetch_player_page_html(args.player)
    print(f"Resolved to: {url}")

    stats = extract_latest_season(html, args.season)
    bio = extract_player_bio(html)
    misc = extract_misc_stats(html, args.season)
    keeper = extract_keeper_stats(html, args.season)
    print(f"Season: {stats['season']} ({stats['squad']}, {stats['competition']})")
    print(f"Goalkeeping stats: {'found' if keeper else 'not applicable'}")

    print("Looking up Understat xG/xA...")
    xg = get_player_xg(args.player, stats["competition"], stats["season"], stats["squad"])
    print(f"xG/xA: {'found' if xg else 'not available for this league'}")

    print("Computing Quality signal (non-AI, percentile-based)...")
    quality = compute_quality_signal(
        bio["position"], stats["competition"], stats["season"], args.player, stats, misc, keeper, xg
    )
    print(f"Quality: {quality['score'] if quality else 'not available for this league/position'}")

    articles = []
    newsapi_key = os.environ.get("NEWSAPI_KEY")
    if newsapi_key:
        print(f"Fetching recent news (last {LOOKBACK_DAYS} days)...")
        try:
            articles = fetch_articles(args.player, newsapi_key)
            print(f"Found {len(articles)} articles")
        except requests.RequestException as e:
            print(f"NewsAPI request failed ({e}) -- continuing without news")
    else:
        print("NEWSAPI_KEY not set -- skipping news, continuing without it")

    print("Calling DeepSeek-V3 for the research brief...")
    synthesis = summarize_combined(
        args.player, stats, xg, articles, misc, keeper, args.scout_notes, philosophy
    )

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", args.player.lower()).strip("_")
    out_path = output_dir / f"{slug}_brief.docx"
    build_docx(
        args.player, bio, stats, xg, articles, misc, keeper,
        synthesis["news_synthesis"], synthesis["fit_read"],
        args.scout_notes, philosophy, out_path,
        quality=quality, fit_score=synthesis["fit_score"],
    )

    print(f"\nQuality: {quality['score'] if quality else 'N/A'}/5  ·  Fit: {synthesis['fit_score'] or 'N/A'}/5")
    print("\n--- What People Say ---")
    print(synthesis["news_synthesis"])
    print("\n--- Signals & Fit Read ---")
    print(synthesis["fit_read"])
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
