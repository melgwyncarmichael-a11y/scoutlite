"""score_track_c3's join_records()/summarize()/_boundary_note() are pure -- testable with
synthetic records independent of whether any real Track C3 captures or blind labels exist yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_c3 import _boundary_note, join_records, normalize_label, summarize  # noqa: E402


def _capture(slug, label, avg_abs_diff, fame_tier="known", position_group="attack"):
    return {
        "slug": slug, "player": slug, "fame_tier": fame_tier, "actual_position_group": position_group,
        "fit_signal": {"label": label, "avg_abs_diff": avg_abs_diff} if label else None,
    }


def _label_row(slug, hand_label="", your_guess=""):
    return {"slug": slug, "hand_label": hand_label, "your_guess": your_guess}


# --- normalize_label (2026-09-25) -- found needed the moment real human-typed labels came in:
# "Hand in glove fit", "Somewhat fits", "Completely different" don't exactly equal the tool's
# own "Hand-in-Glove Fit" / "Somewhat Fits" / "Completely Different" strings. Same class of bug
# as Track A/B's early full-sentence label-matching issue.

def test_normalize_label_tolerates_case_and_missing_hyphens():
    assert normalize_label("Hand in glove fit") == "Hand-in-Glove Fit"
    assert normalize_label("hand-in-glove") == "Hand-in-Glove Fit"
    assert normalize_label("HAND IN GLOVE FIT") == "Hand-in-Glove Fit"


def test_normalize_label_somewhat_fits():
    assert normalize_label("Somewhat fits") == "Somewhat Fits"
    assert normalize_label("somewhat") == "Somewhat Fits"


def test_normalize_label_completely_different():
    assert normalize_label("Completely different") == "Completely Different"
    assert normalize_label("completely different!") == "Completely Different"


def test_normalize_label_none_for_empty_or_unrecognized():
    assert normalize_label("") is None
    assert normalize_label(None) is None
    assert normalize_label("not sure") is None


def test_boundary_note_flags_near_hand_in_glove_cutoff():
    assert "20-cutoff" in _boundary_note(18.0)
    assert "20-cutoff" in _boundary_note(22.0)


def test_boundary_note_flags_near_completely_different_cutoff():
    assert "35-cutoff" in _boundary_note(33.5)


def test_boundary_note_empty_when_comfortably_clear_of_both():
    assert _boundary_note(9.0) == ""
    assert _boundary_note(27.0) == ""


def test_boundary_note_handles_none():
    assert _boundary_note(None) == ""


def test_join_records_normalizes_messy_real_world_label_text():
    # Exactly the shape of real filled-in labels this project actually received.
    rows = join_records(
        [_capture("a", "Somewhat Fits", 22.0)],
        {"a": _label_row("a", hand_label="Somewhat fits")},
    )
    assert rows[0]["hand_label"] == "Somewhat Fits"
    assert rows[0]["hand_label_raw"] == "Somewhat fits"
    assert rows[0]["match"] is True


def test_join_records_match_when_tool_and_hand_label_agree():
    rows = join_records(
        [_capture("a", "Hand-in-Glove Fit", 9.0)],
        {"a": _label_row("a", hand_label="Hand-in-Glove Fit")},
    )
    assert rows[0]["match"] is True


def test_join_records_mismatch_when_they_disagree():
    rows = join_records(
        [_capture("a", "Somewhat Fits", 22.0)],
        {"a": _label_row("a", hand_label="Completely Different")},
    )
    assert rows[0]["match"] is False


def test_join_records_none_when_not_yet_labeled():
    rows = join_records([_capture("a", "Somewhat Fits", 22.0)], {})
    assert rows[0]["hand_label"] is None
    assert rows[0]["match"] is None


def test_join_records_guess_tracked_separately_from_official_label():
    rows = join_records(
        [_capture("a", "Hand-in-Glove Fit", 9.0)],
        {"a": _label_row("a", hand_label="Completely Different", your_guess="Hand-in-Glove Fit")},
    )
    assert rows[0]["match"] is False  # official blind label disagrees with the tool
    assert rows[0]["guess_match"] is True  # but the informal guess happened to agree


def test_summarize_counts_only_labeled_rows_for_match_rate():
    rows = join_records(
        [_capture("a", "Hand-in-Glove Fit", 9.0), _capture("b", "Somewhat Fits", 22.0)],
        {"a": _label_row("a", hand_label="Hand-in-Glove Fit")},  # b left unlabeled
    )
    summary = summarize(rows)
    assert summary["n_total"] == 2
    assert summary["n_labeled"] == 1
    assert summary["n_unlabeled"] == 1
    assert summary["n_match"] == 1


def test_summarize_breaks_out_by_fame_tier():
    rows = join_records(
        [
            _capture("a", "Hand-in-Glove Fit", 9.0, fame_tier="known"),
            _capture("b", "Somewhat Fits", 22.0, fame_tier="unknown"),
        ],
        {
            "a": _label_row("a", hand_label="Hand-in-Glove Fit"),
            "b": _label_row("b", hand_label="Completely Different"),
        },
    )
    summary = summarize(rows)
    assert summary["by_fame_tier"]["known"] == {"n": 1, "n_match": 1}
    assert summary["by_fame_tier"]["unknown"] == {"n": 1, "n_match": 0}


def test_summarize_lists_near_boundary_cases():
    rows = join_records(
        [_capture("a", "Hand-in-Glove Fit", 18.0), _capture("b", "Somewhat Fits", 9.0)],
        {"a": _label_row("a", hand_label="Hand-in-Glove Fit"), "b": _label_row("b", hand_label="Somewhat Fits")},
    )
    summary = summarize(rows)
    assert summary["near_boundary_slugs"] == ["a"]
