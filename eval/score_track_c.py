#!/usr/bin/env python3
"""
Track C eval — Fit signal prose consistency (TESTS.md's B4, reworked for v3). Reads every run
track_c_repeat.py saved and reports, per player+philosophy group:

  1. Whether the fit_signal LABEL stayed identical across runs. As of v3 this is guaranteed by
     construction (compute_fit_signal has no LLM/randomness) -- a mismatch here would mean a
     real bug, not normal variance, and is reported as such.
  2. Whether the LLM's prose (fit_read) named the reference club it was actually compared
     against, every run. This is the part that still touches an LLM at temperature=0.3, so it's
     the one place residual variance could actually show up -- e.g. the write-up drifting into
     vague language that no longer ties back to the specific computed comparison.

Pure aggregation over already-captured JSON (no network, no LLM) -- covered by
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
    labels = [r["fit_signal"]["label"] if r.get("fit_signal") else None for r in records]
    reference_clubs = [r["fit_signal"]["reference_club"] if r.get("fit_signal") else None for r in records]
    club_named_in_prose = [
        bool(r.get("fit_signal")) and r["fit_signal"]["reference_club"].lower() in (r.get("fit_read") or "").lower()
        for r in records
    ]
    source_accuracies = [
        r.get("judge", {}).get("source_accuracy") for r in records if r.get("judge")
    ]
    distinct = sorted({s for s in labels if s is not None})
    return {
        "n_runs": len(records),
        "labels": labels,
        "distinct_labels": distinct,
        "label_stable": len(set(labels)) <= 1,
        "reference_club": reference_clubs[0] if reference_clubs else None,
        "club_named_in_prose": club_named_in_prose,
        "prose_consistent": all(club_named_in_prose) if club_named_in_prose else None,
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
        print(f"--- {player} [{phil_desc}] vs {result['reference_club']} -- {result['n_runs']} runs ---")
        print(f"  label per run: {result['labels']}")
        if result["label_stable"]:
            print(f"  LABEL STABLE (expected -- computed, not written by the model)")
        else:
            print(f"  LABEL NOT STABLE -- {result['distinct_labels']} -- investigate as a bug, not eval noise")
        print(f"  reference club named in prose, per run: {result['club_named_in_prose']}")
        if result["prose_consistent"] is False:
            print(f"  PROSE INCONSISTENT -- at least one run never named {result['reference_club']}")
        print(f"  source_accuracy per run: {result['source_accuracies']}")
        print()


if __name__ == "__main__":
    main()
