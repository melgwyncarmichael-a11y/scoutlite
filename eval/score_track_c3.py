#!/usr/bin/env python3
"""
Track C3 eval — Fit label validation against independent, blind human judgment. Joins each
captured case's tool-computed label (eval/track_c3_samples/*.json) against the blind label a
human filled into eval/track_c3_labels.csv (built by build_track_c3_labeling_sheet.py), reports
the honest match rate -- no rounding up, no cherry-picking which mismatches to mention.

Per the agreed plan (2026-09-24/25), the two cutoffs in scoring.FIT_LABELS are reported
separately, not as one blended number: the 20-point Hand-in-Glove cutoff has real tuning
evidence behind it (Track C2); the 35-point Completely Different cutoff has none. Each case's
avg_abs_diff is checked against how close it sits to either cutoff -- a case near a boundary is
more informative about calibration than one sitting confidently in the middle of a range,
mismatch or not.

Usage:
    .venv/bin/python eval/score_track_c3.py
"""
import argparse
import csv
import json
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "track_c3_samples"
LABELS_CSV = Path(__file__).resolve().parent / "track_c3_labels.csv"

# Mirrors scoring.FIT_LABELS -- duplicated here deliberately rather than imported, since this
# script only ever reads already-captured JSON (no live import of scoring.py needed) and the
# cutoffs are exactly what's being validated, not something to silently follow if they change.
HAND_IN_GLOVE_CUTOFF = 20
COMPLETELY_DIFFERENT_CUTOFF = 35
NEAR_BOUNDARY_MARGIN = 3  # percentile points -- within this of a cutoff counts as "near it"


def normalize_label(raw: str | None) -> str | None:
    """Canonicalizes a human-typed label to the tool's exact string, tolerant of case/spacing/
    hyphen variation -- "Hand in glove fit", "hand-in-glove", "HAND IN GLOVE FIT" all mean
    "Hand-in-Glove Fit". Same class of bug as Track A/B's early full-sentence label-matching
    issue (score_track_a.py/score_track_b.py's history) -- an exact-string comparison would
    silently score every one of these as a mismatch even when the labeler's intent is clear.
    Returns None (not a guess) for genuinely unrecognized text."""
    if not raw:
        return None
    text = raw.strip().lower()
    if "somewhat" in text:
        return "Somewhat Fits"
    if "completely" in text and "different" in text:
        return "Completely Different"
    if "hand" in text and "glove" in text:
        return "Hand-in-Glove Fit"
    return None


def load_hand_labels(labels_csv: Path) -> dict[str, dict]:
    if not labels_csv.exists():
        return {}
    with labels_csv.open(newline="", encoding="utf-8") as f:
        return {row["slug"]: row for row in csv.DictReader(f)}


def load_captures(samples_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(samples_dir.glob("*.json"))]


def _boundary_note(avg_abs_diff: float | None) -> str:
    if avg_abs_diff is None:
        return ""
    near = []
    if abs(avg_abs_diff - HAND_IN_GLOVE_CUTOFF) <= NEAR_BOUNDARY_MARGIN:
        near.append(f"near the {HAND_IN_GLOVE_CUTOFF}-cutoff (tuned)")
    if abs(avg_abs_diff - COMPLETELY_DIFFERENT_CUTOFF) <= NEAR_BOUNDARY_MARGIN:
        near.append(f"near the {COMPLETELY_DIFFERENT_CUTOFF}-cutoff (untested)")
    return "; ".join(near)


def join_records(captures: list[dict], hand_labels: dict[str, dict]) -> list[dict]:
    rows = []
    for c in captures:
        slug = c["slug"]
        label_row = hand_labels.get(slug, {})
        hand_label_raw = (label_row.get("hand_label") or "").strip()
        your_guess_raw = (label_row.get("your_guess") or "").strip()
        hand_label = normalize_label(hand_label_raw)
        your_guess = normalize_label(your_guess_raw)
        fit_signal = c.get("fit_signal")
        actual_label = fit_signal["label"] if fit_signal else None
        avg_abs_diff = fit_signal["avg_abs_diff"] if fit_signal else None
        rows.append({
            "slug": slug,
            "player": c["player"],
            "fame_tier": c.get("fame_tier"),
            "position_group": c.get("actual_position_group"),
            "actual_label": actual_label,
            "avg_abs_diff": avg_abs_diff,
            "hand_label": hand_label,
            "hand_label_raw": hand_label_raw or None,
            "your_guess": your_guess,
            "your_guess_raw": your_guess_raw or None,
            "match": (actual_label == hand_label) if (actual_label and hand_label) else None,
            "guess_match": (actual_label == your_guess) if (actual_label and your_guess) else None,
            "boundary_note": _boundary_note(avg_abs_diff),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    """Pure aggregation -- unit-tested against synthetic rows independent of real captures."""
    labeled = [r for r in rows if r["hand_label"] is not None and r["actual_label"] is not None]
    unlabeled = [r for r in rows if r not in labeled]
    matches = [r for r in labeled if r["match"]]
    near_boundary = [r for r in rows if r["boundary_note"]]
    by_fame: dict[str, dict] = {}
    for r in labeled:
        tier = r["fame_tier"] or "unknown"
        by_fame.setdefault(tier, {"n": 0, "n_match": 0})
        by_fame[tier]["n"] += 1
        if r["match"]:
            by_fame[tier]["n_match"] += 1
    return {
        "n_total": len(rows),
        "n_labeled": len(labeled),
        "n_unlabeled": len(unlabeled),
        "n_match": len(matches),
        "by_fame_tier": by_fame,
        "near_boundary_slugs": [r["slug"] for r in near_boundary],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    parser.add_argument("--labels-csv", type=Path, default=LABELS_CSV)
    args = parser.parse_args()

    if not args.samples_dir.exists() or not any(args.samples_dir.glob("*.json")):
        print(f"No captures found in {args.samples_dir} -- run track_c3_capture.py first.")
        return

    hand_labels = load_hand_labels(args.labels_csv)
    if not hand_labels:
        print(
            f"No hand labels found in {args.labels_csv} -- run build_track_c3_labeling_sheet.py "
            "and have your blind labeler fill in hand_label for every row first."
        )
        return

    captures = load_captures(args.samples_dir)
    rows = join_records(captures, hand_labels)

    for r in rows:
        if r["hand_label"] is None:
            if r["hand_label_raw"]:
                print(f"--- {r['slug']} ({r['player']}) -- UNRECOGNIZED LABEL {r['hand_label_raw']!r}, skipped ---")
            else:
                print(f"--- {r['slug']} ({r['player']}) -- NOT YET LABELED, skipped ---")
            continue
        status = "MATCH" if r["match"] else "MISMATCH"
        print(f"--- {r['slug']} ({r['player']}, {r['fame_tier']}, {r['position_group']}) -- {status} ---")
        print(f"  tool={r['actual_label']!r}  blind_hand_label={r['hand_label']!r} (typed as {r['hand_label_raw']!r})  avg_abs_diff={r['avg_abs_diff']}")
        if r["your_guess"]:
            guess_status = "matched tool" if r["guess_match"] else "did not match tool"
            print(f"  your_guess={r['your_guess']!r} ({guess_status}, informal only -- not independent evidence)")
        if r["boundary_note"]:
            print(f"  BOUNDARY: {r['boundary_note']}")
        print()

    summary = summarize(rows)
    print(f"Overall: {summary['n_match']}/{summary['n_labeled']} matched the blind hand label"
          + (f" ({summary['n_unlabeled']} not yet labeled)" if summary["n_unlabeled"] else ""))
    for tier, s in summary["by_fame_tier"].items():
        print(f"  {tier}: {s['n_match']}/{s['n']}")
    if summary["near_boundary_slugs"]:
        print(f"Cases near a cutoff boundary (most informative for calibration): {', '.join(summary['near_boundary_slugs'])}")


if __name__ == "__main__":
    main()
