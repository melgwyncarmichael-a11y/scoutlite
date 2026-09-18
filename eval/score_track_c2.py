#!/usr/bin/env python3
"""
Track C2 eval — Fit label calibration. Reads every case track_c2_capture.py saved and reports
whether the computed label matched its a-priori expected label, broken out by category
(self-reference vs. deliberate mismatch). Pure aggregation over already-captured JSON (no
network, no LLM).

Usage:
    .venv/bin/python eval/score_track_c2.py
"""
import argparse
import json
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "track_c2_samples"


def load_records(samples_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(samples_dir.glob("*.json"))]


def summarize(records: list[dict]) -> dict:
    by_category: dict[str, list[dict]] = {}
    for r in records:
        by_category.setdefault(r["category"], []).append(r)
    return {
        "n_total": len(records),
        "n_match": sum(1 for r in records if r["match"]),
        "by_category": {
            cat: {"n": len(rs), "n_match": sum(1 for r in rs if r["match"])}
            for cat, rs in by_category.items()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    args = parser.parse_args()

    if not args.samples_dir.exists() or not any(args.samples_dir.glob("*.json")):
        print(f"No cases found in {args.samples_dir} -- run track_c2_capture.py first.")
        return

    records = load_records(args.samples_dir)
    for r in records:
        status = "MATCH" if r["match"] else "MISMATCH"
        diff = r["fit_signal"]["avg_abs_diff"] if r["fit_signal"] else "n/a"
        print(f"--- {r['slug']} ({r['player']}, {r['category']}) -- {status} ---")
        print(f"  expected={r['expected_label']!r} actual={r['actual_label']!r} avg_abs_diff={diff}")
        print(f"  {r['note']}")
        print()

    summary = summarize(records)
    print(f"Overall: {summary['n_match']}/{summary['n_total']} matched expected label")
    for cat, s in summary["by_category"].items():
        print(f"  {cat}: {s['n_match']}/{s['n']}")


if __name__ == "__main__":
    main()
