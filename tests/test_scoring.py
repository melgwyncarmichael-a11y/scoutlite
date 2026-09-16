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


class _DummyFBrefReader:
    """Stands in for sd.FBref(...) so a test never touches soccerdata/network."""
    def read_player_season_stats(self, stat_type=None):
        return None


def test_compute_quality_signal_returns_none_when_understat_population_is_empty(monkeypatch):
    # Real bug, found via a real capture (Kylian Mbappe, 2026-2027, 4 games in): early in a
    # season nobody league-wide has crossed MIN_MINUTES_FOR_POPULATION yet, so the reference
    # population comes back genuinely empty. Before the fix, every attack component silently
    # fell back to percentile_rank's 50.0 "neutral" default, producing a fake-looking 3/5 that
    # was actually measuring nothing. It must return None instead, same as an uncovered league.
    monkeypatch.setattr(scoring, "fetch_league_players_safe", lambda *a, **k: [])
    stats = {"minutes": "360", "competition": "1. La Liga", "season": "2026-2027", "squad": "Real Madrid"}
    xg = {"goals": "4", "assists": "0", "xG": 6.71, "xA": 0.33, "minutes": "360", "key_passes": "4"}
    result = scoring.compute_quality_signal(
        "FW-MF", "1. La Liga", "2026-2027", "Kylian Mbappe", stats, None, None, xg,
    )
    assert result is None


def test_compute_quality_signal_drops_only_the_empty_component_not_the_whole_signal(monkeypatch):
    # The midfield group draws from TWO separate populations (Understat for creativity, FBref
    # misc for defensive actions) -- one being empty shouldn't zero out the other. A genuinely
    # mixed case: Understat's population is empty (e.g. early season), but FBref's misc
    # population has real data.
    monkeypatch.setattr(scoring, "fetch_league_players_safe", lambda *a, **k: [])
    monkeypatch.setattr(scoring.sd, "FBref", lambda *a, **k: _DummyFBrefReader())
    monkeypatch.setattr(scoring, "_fbref_misc_population_per90", lambda *a, **k: [2.0, 4.0, 6.0])

    stats = {"minutes": "900", "competition": "1. Premier League", "season": "2023-2024", "squad": "Arsenal"}
    xg = {"key_passes": "10", "assists": "2", "xG": 3.0, "xA": 1.5, "minutes": "900", "goals": "1"}
    misc = {"interceptions": "10", "tackles_won": "8"}
    result = scoring.compute_quality_signal(
        "MF", "1. Premier League", "2023-2024", "Some Midfielder", stats, misc, None, xg,
    )
    assert result is not None
    assert set(result["components"]) == {"defensive_actions_per90"}  # key_passes/xA dropped, not faked
