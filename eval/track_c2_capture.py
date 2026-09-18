#!/usr/bin/env python3
"""
Track C2 eval — Fit label calibration. Track C (reworked 2026-09-18, see track_c_repeat.py)
confirmed the Fit LABEL can't vary run to run since compute_fit_signal() has no LLM/randomness
in its path -- but that never checked whether the label's actual 15/35 percentile-point
thresholds (scoring.FIT_LABELS) mean anything. Those were a first-pass guess, never validated
against anything (see scoring.py's own comment above FIT_LABELS).

No LLM or NewsAPI call needed here at all -- like track_a_capture.py, this checks a
deterministic signal directly, not a written section, so it's cheap and fast to re-run.

Method: a fixed set of hand-picked cases with an a-priori expected label, not a human-labeling
CSV -- picked so the "right answer" is knowable up front without anyone's subjective judgment:

  - SELF-REFERENCE cases: a player compared against the reference club he actually plays for.
    Expected: close to "Hand-in-Glove Fit", since he's part of the population the club's own
    average is drawn from. If this fails, it's real signal about the label's calibration (or
    about how much an individual outlier can differ from his own squad's positional average),
    not a subjective call.
  - MISMATCH cases: a player whose real playing style is the deliberate opposite of a given
    reference club's philosophy. Expected: "Completely Different".

Usage:
    .venv/bin/python eval/track_c2_capture.py            # run every case
    .venv/bin/python eval/track_c2_capture.py --only dias_vs_dortmund
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

OUT_DIR = Path(__file__).resolve().parent / "track_c2_samples"
SEASON = "2023-2024"  # matches every other eval track's convention

CASES = [
    # --- self-reference: expect Hand-in-Glove Fit -------------------------------------------
    {
        "slug": "adeyemi_dortmund", "player": "Karim Adeyemi", "category": "self_reference",
        "in_possession": "vertical", "out_of_possession": "high_line",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Dortmund attacker tested against Dortmund's own philosophy.",
    },
    {
        "slug": "valverde_real_madrid", "player": "Federico Valverde", "category": "self_reference",
        "in_possession": "vertical", "out_of_possession": "mid_block",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Real Madrid midfielder tested against Real Madrid's own philosophy.",
    },
    {
        "slug": "gimenez_atletico", "player": "Jose Maria Gimenez", "category": "self_reference",
        "player_url": "https://fbref.com/en/players/f0da930c/Jose-Maria-Gimenez",
        "in_possession": "vertical", "out_of_possession": "low_block",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Atletico Madrid defender tested against Atletico's own philosophy.",
    },
    {
        "slug": "haaland_man_city", "player": "Erling Haaland", "category": "self_reference",
        "in_possession": "possession", "out_of_possession": "high_line",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Man City attacker tested against Man City's own philosophy -- but he's a "
                "goal-scoring outlier even among City's own attackers, so this case doubles as "
                "a check on whether an elite individual can diverge from his own squad average.",
    },
    {
        "slug": "kimmich_bayern", "player": "Joshua Kimmich", "category": "self_reference",
        "in_possession": "possession", "out_of_possession": "mid_block",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Bayern Munich midfielder tested against Bayern's own philosophy.",
    },
    {
        "slug": "dunk_brighton", "player": "Lewis Dunk", "category": "self_reference",
        "in_possession": "possession", "out_of_possession": "low_block",
        "expected_label": "Hand-in-Glove Fit",
        "note": "Brighton defender tested against Brighton's own philosophy.",
    },
    # --- deliberate mismatch: expect Completely Different ------------------------------------
    {
        "slug": "traore_vs_man_city", "player": "Adama Traore", "category": "mismatch",
        "player_url": "https://fbref.com/en/players/9a28eba4/Adama-Traore",
        "in_possession": "possession", "out_of_possession": "high_line",
        "expected_label": "Completely Different",
        "note": "Winger known for weak end product (low goals/assists/xG/xA relative to his "
                "profile) vs. Man City's elite attacking output in this position.",
    },
    {
        "slug": "casemiro_vs_bayern", "player": "Casemiro", "category": "mismatch",
        "player_url": "https://fbref.com/en/players/4d224fe8/Casemiro",
        "in_possession": "possession", "out_of_possession": "mid_block",
        "expected_label": "Completely Different",
        "note": "Destroyer-type defensive midfielder, weak creative output, vs. Bayern's "
                "possession/creative midfield profile in the same position group.",
    },
    {
        "slug": "dias_vs_dortmund", "player": "Ruben Dias", "category": "mismatch",
        "player_url": "https://fbref.com/en/players/31c69ef1/Ruben-Dias",
        "in_possession": "vertical", "out_of_possession": "high_line",
        "expected_label": "Completely Different",
        "note": "Possession-dominant City defender (fewer raw defensive actions, reactive "
                "rather than proactive) vs. Dortmund's aggressive high-pressing profile -- also "
                "tests whether the PAdj possession-adjustment washes out a real stylistic "
                "difference, not just a possession-share difference.",
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
                + "; ".join(f"{c['name']} ({c['url']})" for c in candidates)
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
        "category": case["category"],
        "note": case["note"],
        "expected_label": case["expected_label"],
        "quality_position_group": quality["position_group"] if quality else None,
        "fit_signal": fit_signal,
        "actual_label": fit_signal["label"] if fit_signal else None,
        "match": (fit_signal["label"] == case["expected_label"]) if fit_signal else False,
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
        status = "MATCH" if record["match"] else "MISMATCH"
        print(f"  expected={record['expected_label']!r} actual={record['actual_label']!r} -- {status}")
        if record["fit_signal"]:
            print(f"  avg_abs_diff={record['fit_signal']['avg_abs_diff']}")
        print(f"  saved {out_path}")
        results.append(record)

    if len(results) > 1:
        matches = sum(1 for r in results if r["match"])
        print(f"\n{matches}/{len(results)} cases matched their expected label.")


if __name__ == "__main__":
    main()
