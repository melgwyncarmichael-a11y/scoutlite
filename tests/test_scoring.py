"""Pure scoring helpers -- no network."""
import pytest

import scoring


@pytest.mark.parametrize("pos,expected", [
    ("FW-MF", "attack"),
    ("FW", "attack"),
    ("DF (CB)", "defense"),
    ("DF-MF (CM-DM)", "defense"),   # documented quirk: first-listed code wins
    ("MF", "midfield"),
    ("GK", "goalkeeper"),
    ("", None),
    ("XX", None),
])
def test_classify_position_group(pos, expected):
    assert scoring.classify_position_group(pos) == expected


def test_per90():
    assert scoring.per90(9, 900) == pytest.approx(0.9)
    assert scoring.per90(9, 0) == 0.0
    assert scoring.per90(0, 900) == 0.0


def test_percentile_rank():
    pop = list(range(1, 11))  # 1..10
    assert scoring.percentile_rank(5, pop) == 50.0
    assert scoring.percentile_rank(10, pop) == 100.0
    assert scoring.percentile_rank(0, pop) == 0.0
    assert scoring.percentile_rank(5, []) == 50.0  # empty population -> neutral


@pytest.mark.parametrize("pct,score", [(5, 1), (19.9, 1), (20, 2), (45, 3), (65, 4), (80, 5), (99, 5)])
def test_percentile_to_1_5(pct, score):
    assert scoring.percentile_to_1_5(pct) == score


@pytest.mark.parametrize("comp,expected", [
    ("1. Premier League", "ENG-Premier League"),
    ("1. La Liga", "ESP-La Liga"),
    ("1. Serie A", "ITA-Serie A"),
    ("3. League One", None),
])
def test_fbref_comp_to_soccerdata_league(comp, expected):
    assert scoring.fbref_comp_to_soccerdata_league(comp) == expected


def test_describe_quality_is_mechanical_and_has_caveat():
    text = scoring.describe_quality("defense", "1. Premier League")
    assert "Evaluated as a defender" in text
    assert "Premier League" in text
    assert "450+ minutes" in text
    assert scoring.CONTEXT_CAVEAT in text  # the "doesn't account for team style" disclosure
    # must NOT name a specific team's tactics -- that's the whole point of option 1
    assert "possession football" not in text.lower()


def test_understat_population_filters_by_position_and_minutes():
    players = [
        {"position": "F M S", "time": "3000", "goals": "20", "assists": "5", "xG": "18", "xA": "4", "key_passes": "40"},
        {"position": "F S", "time": "100", "goals": "3", "assists": "0", "xG": "2", "xA": "0", "key_passes": "1"},   # too few minutes
        {"position": "D S", "time": "3000", "goals": "1", "assists": "0", "xG": "1", "xA": "0", "key_passes": "5"},  # not a forward
    ]
    pop = scoring._understat_population_per90(players, "attack", "goals")
    assert len(pop) == 1  # only the first player (forward, >= 450 min)
