"""score_track_b.score() is pure aggregation over already-labeled rows -- testable with a
small synthetic CSV independent of whether any real human labeling has happened yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_b import score  # noqa: E402


def _row(label, caught):
    return {"human_label": label, "caught_by_judge": caught}


def test_no_rows_labeled_yet():
    rows = [_row("", ""), _row("", "")]
    r = score(rows)
    assert r["labeled_sentences"] == 0
    assert r["overall_issue_recall"] is None
    assert r["false_positive_rate_on_grounded"] is None


def test_perfect_judge_recall():
    rows = [_row("invented", "y"), _row("overstated", "y"), _row("grounded", "n")]
    r = score(rows)
    assert r["recall_by_category"]["invented"] == 1.0
    assert r["recall_by_category"]["overstated"] == 1.0
    assert r["overall_issue_recall"] == 1.0
    assert r["false_positive_rate_on_grounded"] == 0.0


def test_judge_misses_are_counted():
    rows = [_row("invented", "y"), _row("invented", "n"), _row("verdict-language", "n")]
    r = score(rows)
    assert r["recall_by_category"]["invented"] == 0.5
    assert r["recall_by_category"]["verdict-language"] == 0.0
    assert r["overall_issue_recall"] == 1 / 3


def test_false_positive_on_grounded_sentence():
    rows = [_row("grounded", "y"), _row("grounded", "n"), _row("grounded", "n")]
    r = score(rows)
    assert r["false_positive_rate_on_grounded"] == 1 / 3
    # grounded isn't an "issue" category -- it must never appear in recall_by_category
    assert "grounded" not in r["recall_by_category"]


def test_category_with_zero_instances_is_none_not_zero():
    rows = [_row("invented", "y")]
    r = score(rows)
    assert r["recall_by_category"].get("overstated") is None or "overstated" not in r["recall_by_category"]


def test_partial_labeling_only_scores_labeled_rows():
    rows = [_row("invented", "y"), _row("", ""), _row("", "")]
    r = score(rows)
    assert r["labeled_sentences"] == 1
    assert r["unlabeled_sentences"] == 2
    assert r["overall_issue_recall"] == 1.0


def test_case_insensitive_and_alt_truthy_values():
    rows = [_row("Invented", "Yes"), _row("INVENTED", "1")]
    r = score(rows)
    assert r["recall_by_category"]["invented"] == 1.0


def test_full_sentence_labels_are_recognized_not_dropped():
    # Real labeling (Track A's first pass, 2026-09-16) came back as full sentences, not bare
    # category words -- e.g. "Yes, same role, I think it's correct" instead of "y". A labeler
    # answering the same way here must not have every row silently miscounted.
    rows = [
        _row("I think this claim was invented, no source supports it", "Yes, the judge flagged this one"),
        _row("This reads as overstated / hyped given the real numbers", "No I don't think so"),
        _row("Seems fine, fully grounded in the stats shown", "No"),
    ]
    r = score(rows)
    assert r["label_counts"] == {"invented": 1, "overstated": 1, "grounded": 1}
    assert r["recall_by_category"]["invented"] == 1.0
    assert r["recall_by_category"]["overstated"] == 0.0
    assert r["false_positive_rate_on_grounded"] == 0.0


def test_verdict_keyword_wins_over_grounded_in_an_ambiguous_sentence():
    # "grounded" and "verdict" both being mentioned shouldn't default to the harmless label --
    # verdict-language is checked first specifically so an ambiguous real sentence doesn't get
    # silently swallowed into "grounded".
    rows = [_row("The numbers are grounded but this reads as verdict language to me", "n")]
    r = score(rows)
    assert r["label_counts"] == {"verdict-language": 1}
