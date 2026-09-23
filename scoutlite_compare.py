#!/usr/bin/env python3
"""
ScoutLite comparison pipeline: 2+ player names -> the same single-player research pipeline
(scoutlite_combined.research_player) run once per candidate -> one comparison brief instead of
separate briefs per player.

Built for the real scouting workflow this project's single-player CLI didn't cover: comparing
a shortlist of candidates for the same role/philosophy side by side, not reading one player at
a time and holding the differences in your head.

Deliberately reuses research_player() rather than a parallel implementation -- every signal
(Quality, Fit, the judge loop) behaves exactly as it does for a single-player brief, just run
N times and laid out together by docx_report.build_comparison_docx().

Usage:
    .venv/bin/python scoutlite_compare.py "Erling Haaland" "Alexander Isak" "Ollie Watkins" \
        --season 2023-2024 --in-possession possession --out-of-possession high_line \
        --scout-notes "need a mobile penalty-box striker who can press from the front"

Ambiguous names (FBref search returns multiple matches) are skipped with a clear message
rather than guessing or aborting the whole comparison -- re-run that one player individually
via scoutlite_combined.py with --player-url, then compare the rest.
"""
import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from docx_report import build_comparison_docx
from scoutlite_combined import friendly_error_message, philosophy_from_keys, research_player

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def dedupe_players(players: list[str]) -> list[str]:
    """Case/whitespace-insensitive dedupe, preserving first-seen order and original casing.
    An accidental repeated name would otherwise re-run the entire pipeline for it -- FBref/
    Understat usually cache-hit, but NewsAPI and the DeepSeek synthesis+judge calls don't, so a
    literal duplicate wastes both for identical value (2026-09-22)."""
    seen = set()
    deduped = []
    for p in players:
        key = p.strip().lower()
        if key in seen:
            print(f"Skipping duplicate candidate: '{p}' (already in this comparison)")
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("players", nargs="+", help="2 or more player names to compare, e.g. \"Erling Haaland\" \"Ollie Watkins\"")
    parser.add_argument("--season", help="Specific season for every candidate, e.g. '2024-2025' (default: most recent)")
    parser.add_argument("--fresh", action="store_true", help="Skip the cache, always fetch live (still updates the cache afterward)")
    parser.add_argument("--scout-notes", help="Shared role notes applied to every candidate, e.g. what the scout is looking for in this role")
    parser.add_argument("--in-possession", choices=["vertical", "possession"], help="Club philosophy: in-possession axis")
    parser.add_argument("--out-of-possession", choices=["high_line", "low_block", "mid_block"], help="Club philosophy: out-of-possession axis")
    args = parser.parse_args()
    args.players = dedupe_players(args.players)

    if len(args.players) < 2:
        sys.exit("Need at least 2 distinct players to compare -- for one player, use scoutlite_combined.py instead.")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("DEEPSEEK_API_KEY is not set. Add it to .env in this project folder.")

    philosophy = philosophy_from_keys(args.in_possession, args.out_of_possession)

    results = []
    for i, player in enumerate(args.players, start=1):
        print(f"\n=== Candidate {i}/{len(args.players)}: {player} ===")
        try:
            data = research_player(
                player, None, args.season, args.fresh, args.scout_notes,
                args.in_possession or "", args.out_of_possession or "", philosophy,
            )
        except Exception as e:
            print(f"  SKIPPED -- {friendly_error_message(e, f'processing {player}')}")
            continue
        results.append(data)

    if not results:
        sys.exit("\nNo candidates could be resolved -- nothing to compare.")
    if len(results) < len(args.players):
        print(f"\n{len(results)}/{len(args.players)} candidates resolved -- continuing with those.")

    print("\n--- Summary ---")
    for r in results:
        q = r["quality"]["label"] if r["quality"] else "N/A"
        f = f"{r['fit_signal']['label']} vs {r['fit_signal']['reference_club']}" if r["fit_signal"] else "N/A"
        print(f"  {r['player_name']}: Quality={q}  Fit={f}")

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    slugs = [re.sub(r"[^a-z0-9]+", "_", r["player_name"].lower()).strip("_") for r in results]
    out_path = output_dir / f"comparison__{'_vs_'.join(slugs)}.docx"
    build_comparison_docx(results, philosophy, args.scout_notes, out_path)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.exit(friendly_error_message(e, "running the comparison"))
