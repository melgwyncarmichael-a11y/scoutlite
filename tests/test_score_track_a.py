"""score_track_a's two summary functions are pure aggregation over already-labeled rows --
testable with synthetic CSV rows independent of whether real labeling has happened yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from score_track_a import score_position_survey, score_quality_spotcheck  # noqa: E402


def _pos_row(assigned, expected="", defensible=""):
    return {"assigned_group": assigned, "expected_group": expected, "defensible": defensible}


def test_position_survey_unlabeled():
    r = score_position_survey([_pos_row("attack"), _pos_row("defense")])
    assert r["labeled"] == 0
    assert r["exact_match_rate"] is None
    assert r["defensible_rate"] is None


def test_position_survey_exact_matches():
    rows = [
        {"player": "A", "assigned_group": "attack", "expected_group": "attack", "defensible": "y"},
        {"player": "B", "assigned_group": "defense", "expected_group": "midfield", "defensible": "y"},
    ]
    r = score_position_survey(rows)
    assert r["labeled"] == 2
    assert r["exact_match_rate"] == 0.5
    assert r["mismatched_players"] == ["B"]


def test_position_survey_defensible_is_separate_from_exact_match():
    # a mismatch can still be judged defensible -- that's the whole point of the column
    rows = [
        {"player": "De Bruyne", "assigned_group": "attack", "expected_group": "midfield", "defensible": "y"},
    ]
    r = score_position_survey(rows)
    assert r["exact_match_rate"] == 0.0
    assert r["defensible_rate"] == 1.0


def test_position_survey_case_insensitive():
    rows = [{"player": "A", "assigned_group": "Attack", "expected_group": "attack", "defensible": ""}]
    r = score_position_survey(rows)
    assert r["exact_match_rate"] == 1.0


def _qual_row(player, score="3", tier="", surprising=""):
    return {"player": player, "quality_score": score, "reputation_tier": tier, "surprising": surprising}


def test_quality_spotcheck_unlabeled():
    r = score_quality_spotcheck([_qual_row("A"), _qual_row("B")])
    assert r["scored"] == 2
    assert r["labeled"] == 0
    assert r["surprising_count"] == 0


def test_quality_spotcheck_only_scored_rows_count():
    rows = [_qual_row("A", score="3", tier="starter"), _qual_row("B", score="")]  # B has no score
    r = score_quality_spotcheck(rows)
    assert r["scored"] == 1
    assert r["total"] == 2


def test_quality_spotcheck_surprising_players_listed():
    rows = [
        _qual_row("Wan-Bissaka", score="5", tier="squad", surprising="y"),
        _qual_row("Haaland", score="5", tier="elite", surprising="n"),
    ]
    r = score_quality_spotcheck(rows)
    assert r["surprising_count"] == 1
    assert r["surprising_players"] == ["Wan-Bissaka"]
