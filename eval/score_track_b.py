#!/usr/bin/env python3
"""
Track B eval — once track_b_labels.csv has human_label + caught_by_judge filled in, this
computes what actually matters: does the automated judge's 80% threshold agree with a human?

- Recall per label category: of the sentences a human flagged as invented/overstated/
  verdict-language, what fraction did the judge already catch (caught_by_judge = y)?
- "grounded" sentences aren't a miss if the judge didn't flag them -- they're only counted for
  the false-positive check below.
- False-positive rate: of "grounded" sentences, how many did the judge flag anyway?

This is pure aggregation over the CSV -- no network, no LLM -- so it's covered by
tests/test_score_track_b.py against a small synthetic CSV, independent of whether any real
labeling has happened yet.

Usage:
    .venv/bin/python eval/score_track_b.py
    .venv/bin/python eval/score_track_b.py --csv path/to/other_labels.csv
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent / "track_b_labels.csv"
ISSUE_LABELS = {"invented", "overstated", "verdict-language"}


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def score(rows: list[dict]) -> dict:
    labeled = [r for r in rows if r.get("human_label", "").strip()]
    unlabeled_count = len(rows) - len(labeled)

    by_label = defaultdict(lambda: {"total": 0, "caught": 0})
    label_counts = Counter()

    for r in labeled:
        label = r["human_label"].strip().lower()
        caught = r.get("caught_by_judge", "").strip().lower() in ("y", "yes", "true", "1")
        label_counts[label] += 1
        if label in ISSUE_LABELS:
            by_label[label]["total"] += 1
            if caught:
                by_label[label]["caught"] += 1

    grounded_total = label_counts.get("grounded", 0)
    grounded_flagged = sum(
        1 for r in labeled
        if r["human_label"].strip().lower() == "grounded"
        and r.get("caught_by_judge", "").strip().lower() in ("y", "yes", "true", "1")
    )

    recall_by_category = {
        label: (stats["caught"] / stats["total"] if stats["total"] else None)
        for label, stats in by_label.items()
    }
    total_issues = sum(s["total"] for s in by_label.values())
    total_caught = sum(s["caught"] for s in by_label.values())

    return {
        "total_sentences": len(rows),
        "labeled_sentences": len(labeled),
        "unlabeled_sentences": unlabeled_count,
        "label_counts": dict(label_counts),
        "recall_by_category": recall_by_category,
        "overall_issue_recall": (total_caught / total_issues if total_issues else None),
        "false_positive_rate_on_grounded": (
            grounded_flagged / grounded_total if grounded_total else None
        ),
    }


def _fmt_pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found -- run build_labeling_sheet.py first.")

    rows = load_rows(args.csv)
    result = score(rows)

    print(f"{result['labeled_sentences']}/{result['total_sentences']} sentences labeled "
          f"({result['unlabeled_sentences']} still blank)")
    print(f"Label distribution: {result['label_counts']}")
    print()
    print("Judge recall by issue category (did the judge already catch what a human flagged?):")
    for label in sorted(ISSUE_LABELS):
        print(f"  {label:<16} {_fmt_pct(result['recall_by_category'].get(label))}")
    print(f"  {'overall':<16} {_fmt_pct(result['overall_issue_recall'])}")
    print()
    print(f"False-positive rate on grounded sentences: "
          f"{_fmt_pct(result['false_positive_rate_on_grounded'])} "
          "(judge flagged something a human called fine)")


if __name__ == "__main__":
    main()
