#!/usr/bin/env python3
"""
Track A eval — summarizes the two labeled CSVs once you've filled them in. Pure aggregation
over already-labeled rows (no network, no LLM), same pattern as score_track_b.py -- covered by
tests/test_score_track_a.py against synthetic data, independent of whether real labeling has
happened yet.

Usage:
    .venv/bin/python eval/score_track_a.py
"""
import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_POSITION_CSV = HERE / "track_a_position_survey.csv"
DEFAULT_QUALITY_CSV = HERE / "track_a_quality_spotcheck.csv"


def _truthy(v: str) -> bool:
    # A real labeler writes a full sentence ("Yes, same role, I think it's correct"), not a
    # bare "y" -- an exact-match check against "y"/"yes" silently reads every one of those as
    # false. Read intent off the first word instead: starts with y/true, or is bare "1".
    v = (v or "").strip().lower()
    return v.startswith("y") or v.startswith("true") or v == "1"


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def score_position_survey(rows: list[dict]) -> dict:
    labeled = [r for r in rows if r.get("expected_group", "").strip()]
    exact_matches = sum(
        1 for r in labeled
        if r["assigned_group"].strip().lower() == r["expected_group"].strip().lower()
    )
    defensible_labeled = [r for r in rows if r.get("defensible", "").strip()]
    defensible_count = sum(1 for r in defensible_labeled if _truthy(r["defensible"]))
    mismatches = [
        r["player"] for r in labeled
        if r["assigned_group"].strip().lower() != r["expected_group"].strip().lower()
    ]
    return {
        "total": len(rows),
        "labeled": len(labeled),
        "exact_match_rate": (exact_matches / len(labeled)) if labeled else None,
        "defensible_labeled": len(defensible_labeled),
        "defensible_rate": (defensible_count / len(defensible_labeled)) if defensible_labeled else None,
        "mismatched_players": mismatches,
    }


def score_quality_spotcheck(rows: list[dict]) -> dict:
    scored = [r for r in rows if r.get("quality_score", "").strip()]
    labeled = [r for r in scored if r.get("reputation_tier", "").strip()]
    surprising = [r for r in labeled if _truthy(r.get("surprising", ""))]
    return {
        "total": len(rows),
        "scored": len(scored),
        "labeled": len(labeled),
        "surprising_count": len(surprising),
        "surprising_players": [r["player"] for r in surprising],
    }


def _fmt_pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--position-csv", type=Path, default=DEFAULT_POSITION_CSV)
    parser.add_argument("--quality-csv", type=Path, default=DEFAULT_QUALITY_CSV)
    args = parser.parse_args()

    if args.position_csv.exists():
        p = score_position_survey(load_rows(args.position_csv))
        print(f"--- Position-group survey ({p['labeled']}/{p['total']} labeled) ---")
        print(f"  exact match to your expected_group: {_fmt_pct(p['exact_match_rate'])}")
        print(f"  defensible (your own call):          {_fmt_pct(p['defensible_rate'])} "
              f"of {p['defensible_labeled']} judged")
        if p["mismatched_players"]:
            print(f"  mismatches: {', '.join(p['mismatched_players'])}")
    else:
        print(f"{args.position_csv} not found -- run build_position_survey.py first.")

    print()

    if args.quality_csv.exists():
        q = score_quality_spotcheck(load_rows(args.quality_csv))
        print(f"--- Quality face-validity spot check ({q['labeled']}/{q['scored']} labeled) ---")
        print(f"  flagged surprising: {q['surprising_count']}")
        if q["surprising_players"]:
            print(f"  players: {', '.join(q['surprising_players'])} -- see notes column for why")
    else:
        print(f"{args.quality_csv} not found -- run build_quality_spotcheck.py first.")


if __name__ == "__main__":
    main()
