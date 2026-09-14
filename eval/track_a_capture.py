#!/usr/bin/env python3
"""
Track A eval — captures bio + stats + the Quality signal for one player, no LLM/NewsAPI
involved at all (Track A checks the deterministic signal, not the written sections). Cheaper
and faster than track_b_capture.py for exactly that reason.

Usage:
    .venv/bin/python eval/track_a_capture.py "Rodri" --season 2023-2024
    .venv/bin/python eval/track_a_capture.py "Rodri" --player-url https://fbref.com/en/players/...
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring import compute_quality_signal  # noqa: E402
from scoutlite import (  # noqa: E402
    extract_keeper_stats,
    extract_latest_season,
    extract_misc_stats,
    extract_player_bio,
    get_player_page,
    search_player,
)
from understat_xg import get_player_xg  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "track_a_samples"


def capture(
    player: str,
    season: str | None = None,
    player_url: str | None = None,
    force_refresh: bool = False,
) -> Path:
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
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_")
    out_path = OUT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(record, indent=2, default=str))
    print(f"Position: {bio.get('position')} -> group: "
          f"{quality['position_group'] if quality else '(quality unavailable)'}")
    print(f"Quality: {quality['score']}/5" if quality else "Quality: not available")
    print(f"Saved {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("player")
    parser.add_argument("--player-url")
    parser.add_argument("--season")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    try:
        capture(args.player, season=args.season, player_url=args.player_url, force_refresh=args.fresh)
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
