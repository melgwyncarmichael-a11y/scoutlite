#!/usr/bin/env python3
"""
Track C3 eval — turns every captured case (eval/track_c3_samples/*.json) into one labeling CSV
for a blind human judge. Deliberately does NOT include the tool's own computed label or
avg_abs_diff anywhere in this sheet -- the whole point of Track C3 is an independent judgment
made before seeing what ScoutLite decided, per the "don't grade your own homework" principle.
The labeler should judge from their own knowledge of each player's real style, not from any
number in this sheet.

Two fill-in columns, kept deliberately separate:
  - hand_label: the actual blind judgment (by someone other than whoever built the tool),
    filled in BEFORE looking at the tool's output. This is what score_track_c3.py compares
    against.
  - your_guess: an optional, informal second opinion (e.g. the project owner's own guess) --
    interesting to compare against both the tool and the blind label, but never treated as
    validating evidence on its own, since it isn't independent of having built the tool.

Re-running this after adding new captures is safe -- it always rebuilds the CSV from scratch
from track_c3_samples/, so don't hand-edit filled-in rows without saving a copy first.

Usage:
    .venv/bin/python eval/build_track_c3_labeling_sheet.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring import REFERENCE_CLUBS  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parent / "track_c3_samples"
OUT_CSV = Path(__file__).resolve().parent / "track_c3_labels.csv"

_IN_POSSESSION_LABELS = {"vertical": "vertical, fast transitions", "possession": "slow, methodical possession"}
_OUT_OF_POSSESSION_LABELS = {"high_line": "high line, counter-press", "low_block": "low block, counter", "mid_block": "mid block, hybrid"}

FIELDS = [
    "slug", "player", "squad", "competition", "position_group", "fame_tier",
    "reference_club", "philosophy",
    "hand_label",   # fill in, BLIND: "Hand-in-Glove Fit" / "Somewhat Fits" / "Completely Different"
    "your_guess",   # fill in, optional: an informal second opinion, not independent evidence
    "notes",        # fill in, optional: why you labeled it that way
]


def _philosophy_desc(in_key: str, out_key: str) -> str:
    return f"{_IN_POSSESSION_LABELS.get(in_key, in_key)} / {_OUT_OF_POSSESSION_LABELS.get(out_key, out_key)}"


def build_rows() -> list[dict]:
    rows = []
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        ref = REFERENCE_CLUBS.get((record.get("in_possession"), record.get("out_of_possession")))
        rows.append({
            "slug": record["slug"],
            "player": record["player"],
            "squad": record.get("squad", ""),
            "competition": record.get("competition", ""),
            "position_group": record.get("actual_position_group") or record.get("expected_position_group", ""),
            "fame_tier": record.get("fame_tier", ""),
            "reference_club": ref["display_name"] if ref else "(unknown -- check REFERENCE_CLUBS)",
            "philosophy": _philosophy_desc(record.get("in_possession"), record.get("out_of_possession")),
            "hand_label": "",
            "your_guess": "",
            "notes": "",
        })
    return rows


def main():
    rows = build_rows()
    if not rows:
        print(f"No captures found in {SAMPLES_DIR} -- run track_c3_capture.py first.")
        return
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} cases to {OUT_CSV}")
    print(
        "Open it in a spreadsheet. Have your blind labeler fill in hand_label for every row "
        "BEFORE anyone looks at the tool's own output -- exactly one of \"Hand-in-Glove Fit\", "
        "\"Somewhat Fits\", or \"Completely Different\" per row, judged from real knowledge of "
        "the player's style, not from anything in this sheet. your_guess/notes are optional."
    )


if __name__ == "__main__":
    main()
