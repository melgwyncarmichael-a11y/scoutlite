#!/usr/bin/env python3
"""
Track A1 eval — position-group accuracy survey (completes TESTS.md's B5). Reads every capture
in track_a_samples/ and reports what classify_position_group() actually assigns, independent
of whether the Quality signal itself was computable (a non-covered league like Danny Ward's
League One or Langstaff's League Two still has a real FBref position string worth checking).

Not a pass/fail script -- classify_position_group() is fully deterministic and already has
unit tests (tests/test_scoring.py) for the mechanical rule itself ("first-listed code wins").
This is the judgment layer on top: given a REAL population of players, how often does that
mechanical rule actually land somewhere defensible? Fill in `expected_group` and `defensible`
by hand once you've looked at each row.

Usage:
    .venv/bin/python eval/build_position_survey.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring import classify_position_group  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parent / "track_a_samples"
OUT_CSV = Path(__file__).resolve().parent / "track_a_position_survey.csv"

FIELDS = [
    "player", "raw_position", "assigned_group",
    "expected_group",   # fill in: attack / midfield / defense / goalkeeper -- your own call
    "defensible",       # fill in: y / n -- is assigned_group defensible even if not your first guess?
    "notes",
]


def build_rows() -> list[dict]:
    rows = []
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        raw_position = record.get("bio", {}).get("position", "")
        assigned = classify_position_group(raw_position) or "(unclassified)"
        rows.append({
            "player": record.get("player", path.stem),
            "raw_position": raw_position,
            "assigned_group": assigned,
            "expected_group": "",
            "defensible": "",
            "notes": "",
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
    by_group = {}
    for r in rows:
        by_group.setdefault(r["assigned_group"], []).append(r["player"])
    print(f"Wrote {len(rows)} players to {OUT_CSV}")
    for group, players in sorted(by_group.items()):
        print(f"  {group:<16} {len(players)}  ({', '.join(players)})")
    print("Fill in expected_group + defensible for every row.")


if __name__ == "__main__":
    main()
