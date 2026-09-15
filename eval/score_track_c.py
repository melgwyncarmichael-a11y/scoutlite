#!/usr/bin/env python3
"""
Track C eval — Fit-signal consistency (TESTS.md's B4). Reads every run track_c_repeat.py saved
and reports, per player+philosophy group, whether fit_score stayed stable across runs. Pure
aggregation over already-captured JSON (no network, no LLM) -- covered by
tests/test_score_track_c.py against synthetic records.

Usage:
    .venv/bin/python eval/score_track_c.py
"""
import argparse
import json
import re
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "track_c_samples"
_RUN_SUFFIX = re.compile(r"__run\d+$")


def group_id_for(stem: str) -> str:
    return _RUN_SUFFIX.sub("", stem)


def analyze_runs(records: list[dict]) -> dict:
    """records: the parsed JSON of every run in one player+philosophy group, in any order."""
    fit_scores = [r.get("fit_score") for r in records]
    source_accuracies = [
        r.get("judge", {}).get("source_accuracy") for r in records if r.get("judge")
    ]
    distinct = sorted({s for s in fit_scores if s is not None}, key=lambda x: x)
    return {
        "n_runs": len(records),
        "fit_scores": fit_scores,
        "distinct_fit_scores": distinct,
        "stable": len(set(fit_scores)) <= 1,
        "fit_score_range": (min(distinct), max(distinct)) if distinct else None,
        "source_accuracies": source_accuracies,
    }


def load_groups(samples_dir: Path) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for path in sorted(samples_dir.glob("*.json")):
        gid = group_id_for(path.stem)
        groups.setdefault(gid, []).append(json.loads(path.read_text()))
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    args = parser.parse_args()

    if not args.samples_dir.exists() or not any(args.samples_dir.glob("*.json")):
        print(f"No runs found in {args.samples_dir} -- run track_c_repeat.py first.")
        return

    for group_id, records in sorted(load_groups(args.samples_dir).items()):
        result = analyze_runs(records)
        player = records[0].get("player", group_id)
        philosophy = records[0].get("philosophy") or {}
        phil_desc = " / ".join(v for v in philosophy.values() if v) or "(no philosophy)"
        print(f"--- {player} [{phil_desc}] -- {result['n_runs']} runs ---")
        print(f"  fit_score per run: {result['fit_scores']}")
        if result["stable"]:
            print(f"  STABLE -- every run scored {result['distinct_fit_scores'][0] if result['distinct_fit_scores'] else 'N/A'}")
        else:
            lo, hi = result["fit_score_range"]
            print(f"  NOT STABLE -- ranged {lo}-{hi} across identical inputs")
        print(f"  source_accuracy per run: {result['source_accuracies']}")
        print()


if __name__ == "__main__":
    main()
