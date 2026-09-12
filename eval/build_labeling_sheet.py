#!/usr/bin/env python3
"""
Track B eval — turns every captured brief (eval/track_b_samples/*.json) into one flat CSV,
one row per sentence in "What People Say" + "Signals & Fit Read". Automates the tedious part
(splitting sentences, carrying over the automated judge's findings for context) so the human
labeler only has to make the actual judgment call: is this sentence grounded, invented,
overstated, or verdict-language creeping in.

Re-running this after adding new captures is safe -- it always rebuilds the CSV from scratch
from track_b_samples/, so don't hand-edit rows in a way you want to keep without also saving a
copy elsewhere first.

Usage:
    .venv/bin/python eval/build_labeling_sheet.py
"""
import csv
import json
import re
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "track_b_samples"
OUT_CSV = Path(__file__).resolve().parent / "track_b_labels.csv"

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

FIELDS = [
    "player", "section", "sentence",
    "human_label",          # fill in: grounded / invented / overstated / verdict-language / unclear
    "caught_by_judge",      # fill in: y / n -- did the automated judge already flag this sentence?
    "notes",                # fill in: why you labeled it that way
    "source_accuracy",      # context, auto-filled: this brief's overall judge score
    "judge_findings",       # context, auto-filled: every finding the judge raised on this brief
]


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def build_rows() -> list[dict]:
    rows = []
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        judge = record.get("judge") or {}
        findings = "; ".join(judge.get("findings", [])) or "(none raised)"
        sections = [
            ("news_synthesis", "What People Say"),
            ("fit_read", "Signals & Fit Read"),
        ]
        for field, label in sections:
            for sentence in split_sentences(record.get(field, "")):
                rows.append({
                    "player": record.get("player", path.stem),
                    "section": label,
                    "sentence": sentence,
                    "human_label": "",
                    "caught_by_judge": "",
                    "notes": "",
                    "source_accuracy": judge.get("source_accuracy", ""),
                    "judge_findings": findings,
                })
    return rows


def main():
    rows = build_rows()
    if not rows:
        print(f"No captures found in {SAMPLES_DIR} -- run track_b_capture.py first.")
        return
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    n_players = len(set(r["player"] for r in rows))
    print(f"Wrote {len(rows)} sentences from {n_players} briefs to {OUT_CSV}")
    print("Open it in a spreadsheet and fill in human_label + caught_by_judge for every row.")


if __name__ == "__main__":
    main()
