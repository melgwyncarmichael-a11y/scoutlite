#!/usr/bin/env python3
"""
Track C eval — Fit-signal consistency (TESTS.md's B4). Runs the exact same inputs (player,
season, philosophy, scout notes) through the pipeline N times and saves each run separately,
so score_track_c.py can check whether fit_score itself ever flips.

Reuses track_b_capture.capture() directly rather than duplicating the pipeline -- the only
difference from a normal Track B capture is where the file lands (track_c_samples/, one file
per run) and that FBref/Understat data is fetched once and reused across runs (only the LLM
call should vary run to run; re-scraping N times would just burn rate-limit budget for no
reason, since the whole point is holding every input fixed except the model's own sampling).

Usage:
    .venv/bin/python eval/track_c_repeat.py "Erling Haaland" --season 2023-2024 \
        --in-possession vertical --out-of-possession high_line --runs 5
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from track_b_capture import capture  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "track_c_samples"


def repeat(
    player: str,
    runs: int,
    season: str | None = None,
    player_url: str | None = None,
    scout_notes: str | None = None,
    in_possession: str = "",
    out_of_possession: str = "",
) -> str:
    base_slug = re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_")
    phil_parts = [p for p in (in_possession, out_of_possession) if p]
    group_id = f"{base_slug}__{'_'.join(phil_parts)}" if phil_parts else base_slug

    fit_scores = []
    for i in range(1, runs + 1):
        print(f"--- run {i}/{runs} ---")
        # Only the first run needs force_refresh awareness -- every run after reuses whatever
        # FBref/Understat cache the first one populated (or that was already warm), same
        # season/player, so there's nothing new to fetch. force_refresh stays False throughout:
        # the point of this eval is variance from the LLM call alone, not from re-scraped data.
        path = capture(
            player, season=season, player_url=player_url, scout_notes=scout_notes,
            in_possession=in_possession, out_of_possession=out_of_possession,
            force_refresh=False, out_dir=OUT_DIR, out_name=f"{group_id}__run{i}",
        )
        record = json.loads(path.read_text())
        fit_scores.append(record.get("fit_score"))

    print(f"\nfit_score across {runs} runs: {fit_scores}")
    if len(set(fit_scores)) == 1:
        print("Stable -- identical fit_score every run.")
    else:
        print("NOT stable -- fit_score varied across runs. See score_track_c.py for detail.")
    return group_id


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("player")
    parser.add_argument("--player-url")
    parser.add_argument("--season")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--scout-notes")
    parser.add_argument("--in-possession", choices=["vertical", "possession"], default="")
    parser.add_argument("--out-of-possession", choices=["high_line", "low_block", "mid_block"], default="")
    args = parser.parse_args()

    try:
        repeat(
            args.player, args.runs, season=args.season, player_url=args.player_url,
            scout_notes=args.scout_notes, in_possession=args.in_possession,
            out_of_possession=args.out_of_possession,
        )
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
