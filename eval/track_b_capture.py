#!/usr/bin/env python3
"""
Track B eval — captures everything a human needs to label a brief for hallucination/hype,
per the protocol in NOTES.md ("Sources in the brief + a planned human eval of the judge loop").

Reuses the exact same library calls scoutlite_combined.py's CLI does -- this is NOT a
different pipeline, just one that keeps the intermediate data (judge findings, raw articles
with URLs, the stats the LLM was given) instead of only rendering it into a .docx. Run once
per sample player; build_labeling_sheet.py then turns every captured JSON into one flat CSV.

Usage:
    .venv/bin/python eval/track_b_capture.py "Erling Haaland" --season 2023-2024
    .venv/bin/python eval/track_b_capture.py "Erling Haaland" --season 2023-2024 \
        --scout-notes "tall, direct runner" --in-possession vertical --out-of-possession high_line
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from news_fetch import fetch_articles  # noqa: E402
from scoring import compute_fit_signal, compute_quality_signal  # noqa: E402
from scoutlite import (  # noqa: E402
    extract_keeper_stats,
    extract_latest_season,
    extract_misc_stats,
    extract_player_bio,
    get_player_page,
    search_player,
)
from scoutlite_combined import summarize_combined  # noqa: E402
from understat_xg import get_player_xg  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "track_b_samples"


def capture(
    player: str,
    season: str | None = None,
    player_url: str | None = None,
    scout_notes: str | None = None,
    in_possession: str = "",
    out_of_possession: str = "",
    force_refresh: bool = False,
    out_dir: Path | None = None,
    out_name: str | None = None,
) -> Path:
    """out_dir/out_name let a caller (track_c_repeat.py) reuse this exact pipeline for a
    different purpose -- repeated runs of the SAME inputs -- without landing in
    track_b_samples/ or overwriting each other. Both default to Track B's normal behaviour."""
    philosophy = {
        "in_possession": {
            "vertical": "vertical, fast transitions",
            "possession": "slow, methodical possession",
        }.get(in_possession, ""),
        "out_of_possession": {
            "high_line": "high line, counter-press",
            "low_block": "low block, counter",
            "mid_block": "mid block, hybrid",
        }.get(out_of_possession, ""),
    }

    if player_url:
        url, html = get_player_page(player_url, requested_season=season, force_refresh=force_refresh)
    else:
        candidates = search_player(player, force_refresh=force_refresh)
        if len(candidates) != 1:
            urls = "\n".join(f"  - {c['name']}: {c['url']}" for c in candidates)
            raise SystemExit(
                f"'{player}' matched {len(candidates)} players -- pass --player-url:\n{urls}"
            )
        url, html = get_player_page(candidates[0]["url"], requested_season=season, force_refresh=force_refresh)

    stats = extract_latest_season(html, season)
    bio = extract_player_bio(html)
    misc = extract_misc_stats(html, season)
    keeper = extract_keeper_stats(html, season)

    xg = get_player_xg(
        player, stats["competition"], stats["season"], stats["squad"], force_refresh=force_refresh
    )
    quality = compute_quality_signal(
        bio["position"], stats["competition"], stats["season"], player, stats, misc, keeper, xg,
        force_refresh=force_refresh,
    )

    fit_signal = compute_fit_signal(
        bio["position"], stats["competition"], stats["season"], misc, xg,
        quality["components"] if quality else {},
        in_possession=in_possession, out_of_possession=out_of_possession,
        force_refresh=force_refresh,
    ) if quality else None

    articles = []
    newsapi_key = os.environ.get("NEWSAPI_KEY")
    if newsapi_key:
        try:
            articles = fetch_articles(player, newsapi_key, force_refresh=force_refresh)
        except requests.RequestException as e:
            print(f"NewsAPI request failed ({e}) -- continuing with no articles", file=sys.stderr)

    synthesis = summarize_combined(
        player, stats, xg, articles, misc, keeper, scout_notes, philosophy, fit_signal=fit_signal,
    )

    record = {
        "player": player,
        "fbref_url": url,
        "season": stats.get("season"),
        "bio": bio,
        "stats": stats,
        "misc": misc,
        "keeper": keeper,
        "xg": xg,
        "quality": quality,
        "articles": articles,
        "scout_notes": scout_notes,
        "philosophy": philosophy,
        "news_synthesis": synthesis["news_synthesis"],
        "fit_read": synthesis["fit_read"],
        "fit_signal": synthesis["fit_signal"],
        "judge": synthesis["judge"],
    }

    target_dir = out_dir or OUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    if out_name:
        slug = out_name
    else:
        slug = re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_")
        if in_possession or out_of_possession:
            # A philosophy-set capture is a genuinely different sample (it exercises the
            # Fit-score path a no-philosophy capture doesn't) -- suffix the slug so it lands
            # alongside the plain capture instead of silently overwriting it.
            phil_slug = "_".join(p for p in (in_possession, out_of_possession) if p)
            slug = f"{slug}__{phil_slug}"
    out_path = target_dir / f"{slug}.json"
    out_path.write_text(json.dumps(record, indent=2, default=str))
    print(f"Judge: {synthesis['judge']['source_accuracy']}% after {synthesis['judge']['iterations']} pass(es)")
    print(f"Saved {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("player")
    parser.add_argument("--player-url")
    parser.add_argument("--season")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--scout-notes")
    parser.add_argument("--in-possession", choices=["vertical", "possession"], default="")
    parser.add_argument("--out-of-possession", choices=["high_line", "low_block", "mid_block"], default="")
    args = parser.parse_args()

    try:
        capture(
            args.player, season=args.season, player_url=args.player_url,
            scout_notes=args.scout_notes, in_possession=args.in_possession,
            out_of_possession=args.out_of_possession, force_refresh=args.fresh,
        )
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
