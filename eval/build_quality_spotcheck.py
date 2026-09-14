#!/usr/bin/env python3
"""
Track A2 eval — the "Ronaldo test" (completes TESTS.md's B3). Reads every capture in
track_a_samples/ and lays out its Quality score next to a blank column for a quick, independent
reputation lookup -- pick each player's tier BEFORE looking at their score column, then compare.

This is a face-validity check, not a precision measurement: with ~10-15 players there's no
real statistic to compute, just "did anything land somewhere indefensible" (a squad player at
5/5, a genuinely elite player at 1/5). Wan-Bissaka's 5/5 in TESTS.md (Finding 1) is the
template for how a surprising score gets investigated and either explained or flagged, not
assumed to be a bug.

Usage:
    .venv/bin/python eval/build_quality_spotcheck.py
"""
import csv
import json
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "track_a_samples"
OUT_CSV = Path(__file__).resolve().parent / "track_a_quality_spotcheck.csv"

FIELDS = [
    "player", "position_group", "quality_score", "avg_percentile", "components",
    "reputation_tier",  # fill in BEFORE looking at quality_score: elite / starter / squad / fringe
    "surprising",       # fill in: y / n -- does quality_score clash with reputation_tier?
    "notes",            # fill in especially when surprising=y -- explained, or a real flag?
]


def build_rows() -> list[dict]:
    rows = []
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        quality = record.get("quality")
        components = ", ".join(
            f"{k.replace('_', ' ')}={v:.0f}%ile" for k, v in quality["components"].items()
        ) if quality else ""
        rows.append({
            "player": record.get("player", path.stem),
            "position_group": quality["position_group"] if quality else "(not available)",
            "quality_score": quality["score"] if quality else "",
            "avg_percentile": quality["avg_percentile"] if quality else "",
            "components": components,
            "reputation_tier": "",
            "surprising": "",
            "notes": "" if quality else "Quality signal not available for this player's league/position",
        })
    return rows


def main():
    rows = build_rows()
    if not rows:
        print(f"No captures found in {SAMPLES_DIR} -- run track_a_capture.py first.")
        return
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    scored = [r for r in rows if r["quality_score"] != ""]
    print(f"Wrote {len(rows)} players to {OUT_CSV} ({len(scored)} with a Quality score)")
    print("Pick a reputation_tier for each BEFORE looking at quality_score, then fill in "
          "surprising + notes.")


if __name__ == "__main__":
    main()
