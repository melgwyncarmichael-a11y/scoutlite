#!/usr/bin/env python3
"""
Track C3 eval — Fit label validation against independent, blind human judgment. Track C2
(eval/TRACK_C2_REPORT.md) checked the 15/35 thresholds against 9 cases whose "expected" label
was decided by construction (self-reference should read Hand-in-Glove, deliberate mismatch
should read Completely Different) -- reasoned out by the same person who built the tool, not
independently judged. That's weaker evidence than it looked. Track C3 fixes that: a football-
literate labeler judges each case BLIND (before seeing the tool's output) using their own
knowledge of the player's real style, per the "don't grade your own homework" principle.

This script only does the capture half -- computing and saving the tool's own Fit signal for
each case, same as track_c2_capture.py, no LLM/NewsAPI needed. It deliberately does NOT print
or reveal the computed label anywhere the labeler could see it before judging (see
build_track_c3_labeling_sheet.py, which reads these captures but only ever writes the neutral
context columns to the labeling sheet, never the tool's own label). score_track_c3.py is what
later joins the two back together.

10 cases, agreed with the project owner (2026-09-24/25): 3 defenders, 3 midfielders, 3
attackers, 1 goalkeeper; 5 relatively famous / 5 relatively unknown; rotated across all 6
REFERENCE_CLUBS entries (Brighton x2, Atletico Madrid x2, Borussia Dortmund x2, Real Madrid x2,
Bayern Munich x1, Manchester City x1); deliberately spans 4 of the 5 top-5 leagues (Premier
League, Bundesliga, Serie A, La Liga) rather than concentrating on one, per direct request.

Usage:
    .venv/bin/python eval/track_c3_capture.py            # run every case
    .venv/bin/python eval/track_c3_capture.py --only rodri_vs_real_madrid
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring import compute_fit_signal, compute_quality_signal  # noqa: E402
from scoutlite import (  # noqa: E402
    extract_keeper_stats,
    extract_latest_season,
    extract_misc_stats,
    extract_player_bio,
    get_player_page,
    search_player,
)
from understat_xg import get_player_xg  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "track_c3_samples"
SEASON = "2023-2024"  # matches every other eval track's convention

CASES = [
    {
        "slug": "kobel_vs_brighton", "player": "Gregor Kobel", "position_group": "goalkeeper",
        "fame_tier": "unknown", "in_possession": "possession", "out_of_possession": "low_block",
        "note": "Dortmund's own keeper tested against Brighton's possession/low-block philosophy "
                "-- a genuine cross-club test, not a self-reference case.",
    },
    {
        "slug": "van_dijk_vs_brighton", "player": "Virgil van Dijk", "position_group": "defense",
        "fame_tier": "known", "in_possession": "possession", "out_of_possession": "low_block",
        "note": "Liverpool's high-line possession CB tested against Brighton's more compact, "
                "low-block possession style.",
    },
    {
        "slug": "upamecano_vs_atletico", "player": "Dayot Upamecano", "position_group": "defense",
        "fame_tier": "known", "in_possession": "vertical", "out_of_possession": "low_block",
        "note": "Bayern's possession-based CB tested against Atletico Madrid's physical, "
                "vertical low-block demands.",
    },
    {
        "slug": "bastoni_vs_dortmund", "player": "Alessandro Bastoni", "position_group": "defense",
        "fame_tier": "unknown", "in_possession": "vertical", "out_of_possession": "high_line",
        "note": "Inter's ball-playing CB tested against Dortmund's aggressive vertical/"
                "high-press philosophy.",
    },
    {
        "slug": "rodri_vs_real_madrid", "player": "Rodri", "position_group": "midfield",
        "fame_tier": "known",
        # Plain "Rodri" matches 100 unrelated lower-league Spanish players on FBref and never
        # surfaces the real Man City Rodri within that cap -- his full legal name does.
        "player_url": "https://fbref.com/en/players/6434f10d/Rodri",
        "in_possession": "vertical", "out_of_possession": "mid_block",
        "note": "Man City's deep-lying possession pivot tested against Real Madrid's more "
                "transition-heavy vertical/mid-block midfield demands.",
    },
    {
        "slug": "bellingham_vs_bayern", "player": "Jude Bellingham", "position_group": "midfield",
        "fame_tier": "known", "in_possession": "possession", "out_of_possession": "mid_block",
        "note": "Real Madrid's box-to-box, high-tempo midfielder tested against Bayern's more "
                "patient possession/mid-block demands.",
    },
    {
        "slug": "kone_vs_atletico", "player": "Manu Kone", "position_group": "midfield",
        "fame_tier": "unknown", "in_possession": "vertical", "out_of_possession": "low_block",
        # Season 2023-2024 (this eval's standard season) predates his move to Roma -- FBref
        # shows him at Gladbach for this season, confirmed live. Bundesliga either way.
        "note": "A Bundesliga box-to-box midfielder (Gladbach in 2023-2024) tested against "
                "Atletico Madrid's vertical/low-block philosophy.",
    },
    {
        "slug": "haaland_vs_dortmund", "player": "Erling Haaland", "position_group": "attack",
        "fame_tier": "known", "in_possession": "vertical", "out_of_possession": "high_line",
        "note": "Man City's striker tested against his actual former club's philosophy -- "
                "deliberately fresh territory (only ever tested against Man City itself before).",
    },
    {
        "slug": "guirassy_vs_man_city", "player": "Serhou Guirassy", "position_group": "attack",
        "fame_tier": "unknown",
        "in_possession": "possession", "out_of_possession": "high_line",
        # Season 2023-2024 (this eval's standard season) predates his move to Dortmund -- FBref
        # shows him at Stuttgart for this season, confirmed live. Bundesliga either way.
        "note": "A Bundesliga striker (Stuttgart in 2023-2024) tested against Manchester City's "
                "possession/high-line philosophy.",
    },
    {
        "slug": "kean_vs_real_madrid", "player": "Moise Kean", "position_group": "attack",
        "fame_tier": "unknown", "in_possession": "vertical", "out_of_possession": "mid_block",
        "note": "Fiorentina's direct, in-behind striker tested against Real Madrid's vertical/"
                "mid-block transition demands.",
    },
]


def capture_case(case: dict, force_refresh: bool = False) -> dict:
    player = case["player"]
    if case.get("player_url"):
        player_url = case["player_url"]
    else:
        candidates = search_player(player, force_refresh=force_refresh)
        if len(candidates) != 1:
            raise ValueError(
                f"'{player}' matched {len(candidates)} players -- "
                + "; ".join(f"{c['name']} ({c['url']})" for c in candidates[:15])
                + (" ..." if len(candidates) > 15 else "")
            )
        player_url = candidates[0]["url"]
    url, html = get_player_page(player_url, requested_season=SEASON, force_refresh=force_refresh)

    stats = extract_latest_season(html, SEASON)
    bio = extract_player_bio(html)
    misc = extract_misc_stats(html, SEASON)
    keeper = extract_keeper_stats(html, SEASON)
    xg = get_player_xg(player, stats["competition"], stats["season"], stats["squad"], force_refresh=force_refresh)

    quality = compute_quality_signal(
        bio["position"], stats["competition"], stats["season"], player, stats, misc, keeper, xg,
        force_refresh=force_refresh,
    )
    fit_signal = compute_fit_signal(
        bio["position"], stats["competition"], stats["season"], misc, xg,
        quality["components"] if quality else {},
        in_possession=case["in_possession"], out_of_possession=case["out_of_possession"],
        force_refresh=force_refresh,
    ) if quality else None

    return {
        "slug": case["slug"],
        "player": player,
        "fbref_url": url,
        "season": stats.get("season"),
        "squad": stats.get("squad"),
        "competition": stats.get("competition"),
        "expected_position_group": case["position_group"],
        "actual_position_group": quality["position_group"] if quality else None,
        "fame_tier": case["fame_tier"],
        "note": case["note"],
        "in_possession": case["in_possession"],
        "out_of_possession": case["out_of_possession"],
        "quality": quality,
        "fit_signal": fit_signal,
        "actual_label": fit_signal["label"] if fit_signal else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="Run a single case by slug instead of the full set")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    cases = [c for c in CASES if c["slug"] == args.only] if args.only else CASES
    if args.only and not cases:
        sys.exit(f"No case with slug '{args.only}' -- known slugs: {[c['slug'] for c in CASES]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        print(f"--- {case['slug']} ({case['player']}) ---")
        try:
            record = capture_case(case, force_refresh=args.fresh)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        out_path = OUT_DIR / f"{case['slug']}.json"
        out_path.write_text(json.dumps(record, indent=2, default=str))
        if record["expected_position_group"] != record["actual_position_group"]:
            print(
                f"  WARNING: expected position group {record['expected_position_group']!r}, "
                f"got {record['actual_position_group']!r} -- FBref's tag may not match assumption"
            )
        print(f"  resolved: {record['player']} -- {record['squad']} ({record['competition']}), season {record['season']}")
        if record["fit_signal"]:
            print(f"  actual_label={record['actual_label']!r} avg_abs_diff={record['fit_signal']['avg_abs_diff']} (hidden from the labeling sheet)")
        else:
            print("  fit_signal not available for this player/league/philosophy combination")
        print(f"  saved {out_path}")
        results.append(record)

    print(f"\n{len(results)}/{len(cases)} cases captured. Labels intentionally not compared here "
          "-- run build_track_c3_labeling_sheet.py next, then score_track_c3.py once the blind "
          "labels are filled in.")


if __name__ == "__main__":
    main()
