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
