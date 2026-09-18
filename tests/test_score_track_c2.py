"""score_track_c2's summarize() is pure -- testable with synthetic records independent of
whether any real Track C2 cases have been captured yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_c2 import summarize  # noqa: E402


def _rec(slug, category, match, avg_abs_diff=10.0):
    return {
        "slug": slug, "player": slug, "category": category, "match": match,
        "expected_label": "Hand-in-Glove Fit", "actual_label": "Hand-in-Glove Fit" if match else "Somewhat Fits",
        "fit_signal": {"avg_abs_diff": avg_abs_diff}, "note": "",
    }


def test_overall_counts():
    s = summarize([_rec("a", "self_reference", True), _rec("b", "self_reference", False)])
    assert s["n_total"] == 2
    assert s["n_match"] == 1


def test_breaks_out_by_category():
    s = summarize([
        _rec("a", "self_reference", True), _rec("b", "self_reference", True),
        _rec("c", "mismatch", False),
    ])
    assert s["by_category"]["self_reference"] == {"n": 2, "n_match": 2}
    assert s["by_category"]["mismatch"] == {"n": 1, "n_match": 0}


def test_empty_records():
    s = summarize([])
    assert s["n_total"] == 0
    assert s["n_match"] == 0
    assert s["by_category"] == {}
