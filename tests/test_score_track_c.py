"""score_track_c's analyze_runs() and group_id_for() are pure -- testable with synthetic
records independent of whether any real repeated runs have been captured yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_c import analyze_runs, group_id_for  # noqa: E402


def _rec(fit_score, source_accuracy=90.0):
    return {"fit_score": fit_score, "judge": {"source_accuracy": source_accuracy}}


def test_group_id_strips_run_suffix():
    assert group_id_for("erling_haaland__vertical_high_line__run1") == "erling_haaland__vertical_high_line"
    assert group_id_for("erling_haaland__vertical_high_line__run12") == "erling_haaland__vertical_high_line"
    assert group_id_for("casemiro") == "casemiro"  # no suffix -- unaffected


def test_stable_when_every_run_agrees():
    r = analyze_runs([_rec(4), _rec(4), _rec(4)])
    assert r["stable"] is True
    assert r["n_runs"] == 3
    assert r["distinct_fit_scores"] == [4]


def test_not_stable_when_scores_differ():
    r = analyze_runs([_rec(2), _rec(4), _rec(4)])
    assert r["stable"] is False
    assert r["distinct_fit_scores"] == [2, 4]
    assert r["fit_score_range"] == (2, 4)


def test_none_fit_scores_dont_count_as_a_distinct_value():
    # e.g. a run where the philosophy somehow didn't come through -- shouldn't silently count
    # "None" as a second "distinct" score alongside real ones.
    r = analyze_runs([_rec(3), _rec(None)])
    assert r["stable"] is False  # {3, None} has 2 distinct raw values -- correctly flagged, not hidden
    assert r["distinct_fit_scores"] == [3]  # but None is excluded from the *range* calculation


def test_single_run_is_trivially_stable():
    r = analyze_runs([_rec(5)])
    assert r["stable"] is True
    assert r["fit_score_range"] == (5, 5)


def test_source_accuracies_collected_per_run():
    r = analyze_runs([_rec(3, source_accuracy=90.0), _rec(3, source_accuracy=65.0)])
    assert r["source_accuracies"] == [90.0, 65.0]


def test_missing_judge_is_skipped_not_a_crash():
    r = analyze_runs([_rec(3), {"fit_score": 3, "judge": None}])
    assert r["source_accuracies"] == [90.0]
