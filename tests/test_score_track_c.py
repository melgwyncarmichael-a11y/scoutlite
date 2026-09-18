"""score_track_c's analyze_runs() and group_id_for() are pure -- testable with synthetic
records independent of whether any real repeated runs have been captured yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_c import analyze_runs, group_id_for  # noqa: E402


def _rec(label, reference_club="Borussia Dortmund", fit_read=None, source_accuracy=90.0):
    fit_signal = {"label": label, "reference_club": reference_club} if label is not None else None
    if fit_read is None:
        fit_read = f"This player's profile compares well to {reference_club}'s squad." if fit_signal else ""
    return {"fit_signal": fit_signal, "fit_read": fit_read, "judge": {"source_accuracy": source_accuracy}}


def test_group_id_strips_run_suffix():
    assert group_id_for("erling_haaland__vertical_high_line__run1") == "erling_haaland__vertical_high_line"
    assert group_id_for("erling_haaland__vertical_high_line__run12") == "erling_haaland__vertical_high_line"
    assert group_id_for("casemiro") == "casemiro"  # no suffix -- unaffected


def test_label_stable_when_every_run_agrees():
    r = analyze_runs([_rec("Hand-in-Glove Fit"), _rec("Hand-in-Glove Fit"), _rec("Hand-in-Glove Fit")])
    assert r["label_stable"] is True
    assert r["n_runs"] == 3
    assert r["distinct_labels"] == ["Hand-in-Glove Fit"]


def test_label_not_stable_when_labels_differ():
    # Should never happen post-v3 (no LLM/randomness in the label's path) -- but the check
    # still needs to catch it as a real bug rather than silently averaging it away.
    r = analyze_runs([_rec("Somewhat Fits"), _rec("Hand-in-Glove Fit"), _rec("Hand-in-Glove Fit")])
    assert r["label_stable"] is False
    assert r["distinct_labels"] == ["Hand-in-Glove Fit", "Somewhat Fits"]


def test_none_labels_dont_count_as_a_distinct_value():
    # e.g. a run where the philosophy somehow didn't come through -- shouldn't silently count
    # "None" as a second "distinct" label alongside real ones.
    r = analyze_runs([_rec("Somewhat Fits"), _rec(None)])
    assert r["label_stable"] is False  # {"Somewhat Fits", None} -- correctly flagged, not hidden
    assert r["distinct_labels"] == ["Somewhat Fits"]  # None excluded from the distinct list


def test_single_run_is_trivially_stable():
    r = analyze_runs([_rec("Completely Different")])
    assert r["label_stable"] is True
    assert r["distinct_labels"] == ["Completely Different"]


def test_reference_club_reported_from_first_record():
    r = analyze_runs([_rec("Hand-in-Glove Fit", reference_club="Manchester City")])
    assert r["reference_club"] == "Manchester City"


def test_prose_consistent_when_every_run_names_the_club():
    r = analyze_runs([_rec("Hand-in-Glove Fit"), _rec("Hand-in-Glove Fit")])
    assert r["club_named_in_prose"] == [True, True]
    assert r["prose_consistent"] is True


def test_prose_inconsistent_when_a_run_omits_the_club():
    r = analyze_runs([
        _rec("Hand-in-Glove Fit"),
        _rec("Hand-in-Glove Fit", fit_read="A vague read that never names the comparison club."),
    ])
    assert r["club_named_in_prose"] == [True, False]
    assert r["prose_consistent"] is False


def test_no_philosophy_run_does_not_count_as_prose_inconsistent():
    r = analyze_runs([_rec(None, fit_read="")])
    assert r["club_named_in_prose"] == [False]
    assert r["prose_consistent"] is False  # honestly reflects "no signal to check", not silently True


def test_source_accuracies_collected_per_run():
    r = analyze_runs([_rec("Hand-in-Glove Fit", source_accuracy=90.0), _rec("Hand-in-Glove Fit", source_accuracy=65.0)])
    assert r["source_accuracies"] == [90.0, 65.0]


def test_missing_judge_is_skipped_not_a_crash():
    r = analyze_runs([_rec("Hand-in-Glove Fit"), {"fit_signal": None, "fit_read": "", "judge": None}])
    assert r["source_accuracies"] == [90.0]
