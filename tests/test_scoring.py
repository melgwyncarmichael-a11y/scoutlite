"""Pure scoring helpers -- no network."""
import pandas as pd
import pytest

import scoring


@pytest.mark.parametrize("pos,expected", [
    ("FW-MF", "attack"),
    ("FW", "attack"),
    ("DF (CB)", "defense"),
    ("DF-MF (CM-DM)", "midfield"),   # Rodri/Rice -- fixed 2026-09-17, see docstring
    ("DF-MF (FB, right)", "defense"),  # Wan-Bissaka/Trent -- genuine fullback, unaffected
    ("DF-MF (DM)", "midfield"),        # a single DM tag, not just the CM-DM pair
    ("MF (CM-DM)", "midfield"),        # Casemiro -- unchanged, the case the fix aligns to
    ("FW-MF (AM-CM-DM)", "attack"),    # Bruno Fernandes -- FW-MF stays first-code-wins
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


@pytest.mark.parametrize("components,expect_caveat", [
    ({"goals_per90": 100.0, "xG_per90": 99.0, "assists_per90": 56.0, "xA_per90": 53.0}, True),  # Haaland's real spread (47pts)
    ({"goals_per90": 60.0, "xG_per90": 55.0, "assists_per90": 50.0, "xA_per90": 45.0}, False),  # tight spread (15pts)
    ({"goals_per90": 91.0, "xG_per90": 50.0}, True),  # 41pt spread -- just over the threshold
    ({"defensive_actions_per90": 48.0}, False),  # single component -- nothing to spread
])
def test_specialist_caveat(components, expect_caveat):
    result = scoring._specialist_caveat(components)
    assert (result is not None) == expect_caveat


def test_specialist_caveat_boundary_is_strictly_greater_than():
    # exactly at the threshold should NOT trigger -- only a spread strictly wider than it
    assert scoring._specialist_caveat({"a": 70.0, "b": 30.0}) is None  # spread == 40
    assert scoring._specialist_caveat({"a": 70.1, "b": 30.0}) is not None  # spread > 40


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


@pytest.mark.parametrize("pct,label", [
    (5, "Below Rotation"), (19.9, "Below Rotation"),
    (20, "Depth Option"), (39.9, "Depth Option"),
    (40, "Solid Starter"), (59.9, "Solid Starter"),
    (60, "Strong Starter"), (79.9, "Strong Starter"),
    (80, "World Class"), (99, "World Class"),
])
def test_percentile_to_label(pct, label):
    assert scoring.percentile_to_label(pct) == label


def test_possession_adjust_scales_up_for_a_dominant_possession_team():
    # 65% possession -> opponent has 35% -> fewer defensive opportunities -> scale UP
    adjusted = scoring._possession_adjust(10.0, team_possession_pct=65.0, league_avg_possession_pct=50.0)
    assert adjusted > 10.0


def test_possession_adjust_scales_down_for_a_low_possession_team():
    # 35% possession -> opponent has 65% -> abundant defensive opportunities -> scale DOWN
    adjusted = scoring._possession_adjust(10.0, team_possession_pct=35.0, league_avg_possession_pct=50.0)
    assert adjusted < 10.0


def test_possession_adjust_neutral_at_league_average():
    # exactly 50/50 -> no adjustment either way
    adjusted = scoring._possession_adjust(10.0, team_possession_pct=50.0, league_avg_possession_pct=50.0)
    assert adjusted == pytest.approx(10.0)


def test_possession_adjust_guards_against_100_percent_possession():
    # opponent_possession would be 0 -> division by zero guarded, returns the value unchanged
    assert scoring._possession_adjust(10.0, team_possession_pct=100.0, league_avg_possession_pct=50.0) == 10.0


@pytest.mark.parametrize("diff,label", [
    (0, "Hand-in-Glove Fit"), (14.9, "Hand-in-Glove Fit"),
    (15, "Somewhat Fits"), (34.9, "Somewhat Fits"),
    (35, "Completely Different"), (80, "Completely Different"),
])
def test_fit_label(diff, label):
    assert scoring._fit_label(diff) == label


def test_understat_population_per90_team_filter():
    players = [
        {"position": "F", "time": "3000", "goals": "20", "team_title": "Manchester City"},
        {"position": "F", "time": "3000", "goals": "10", "team_title": "Liverpool"},
    ]
    all_pop = scoring._understat_population_per90(players, "attack", "goals")
    city_only = scoring._understat_population_per90(players, "attack", "goals", team_title="Manchester City")
    assert len(all_pop) == 2
    assert len(city_only) == 1


def _misc_df(rows):
    """rows: list of (team, player, pos, nineties, interceptions, tackles_won)."""
    index = pd.MultiIndex.from_tuples(
        [("ENG-Premier League", "2324", r[0], r[1]) for r in rows],
        names=["league", "season", "team", "player"],
    )
    return pd.DataFrame(
        {
            ("pos", ""): [r[2] for r in rows],
            ("90s", ""): [r[3] for r in rows],
            ("Performance", "Int"): [r[4] for r in rows],
            ("Performance", "TklW"): [r[5] for r in rows],
        },
        index=index,
    )


def test_fbref_misc_population_per90_squad_filter():
    df = _misc_df([
        ("Manchester City", "Rodri", "MF", 30.0, 30, 30),   # 2.0/90
        ("Liverpool", "Someone", "MF", 30.0, 15, 15),        # 1.0/90
    ])
    all_pop = scoring._fbref_misc_population_per90(df, "midfield")
    city_only = scoring._fbref_misc_population_per90(df, "midfield", squad="Manchester City")
    assert len(all_pop) == 2
    assert city_only == pytest.approx([2.0])


def _keeper_df(rows):
    """rows: list of (team, player, nineties, save_pct)."""
    index = pd.MultiIndex.from_tuples(
        [("ENG-Premier League", "2324", r[0], r[1]) for r in rows],
        names=["league", "season", "team", "player"],
    )
    return pd.DataFrame(
        {
            ("Playing Time", "90s"): [r[2] for r in rows],
            ("Performance", "Save%"): [r[3] for r in rows],
        },
        index=index,
    )


def test_fbref_keeper_population_squad_filter():
    df = _keeper_df([("Arsenal", "Raya", 30.0, 70.0), ("Chelsea", "Someone", 30.0, 65.0)])
    all_pop = scoring._fbref_keeper_population(df)
    arsenal_only = scoring._fbref_keeper_population(df, squad="Arsenal")
    assert len(all_pop) == 2
    assert arsenal_only == [70.0]


def _team_std_df(rows):
    """rows: list of (team, possession_pct)."""
    index = pd.MultiIndex.from_tuples(
        [("ENG-Premier League", "2324", r[0]) for r in rows], names=["league", "season", "team"]
    )
    return pd.DataFrame({("Poss", ""): [r[1] for r in rows]}, index=index)


class _DummyTeamReader:
    """Stands in for sd.FBref(...) -- handles both the team-level possession pull
    (_team_possession_map) and the player-level misc pull (compute_fit_signal's defense/
    midfield branch), since compute_fit_signal's PAdj step makes a second sd.FBref(...) call
    that hits the same monkeypatched lambda."""
    def __init__(self, team_df=None, misc_df=None):
        self._team_df = team_df
        self._misc_df = misc_df

    def read_team_season_stats(self, stat_type=None):
        return self._team_df

    def read_player_season_stats(self, stat_type=None):
        return self._misc_df


def test_team_possession_map(monkeypatch):
    df = _team_std_df([("Manchester City", 65.0), ("Burnley", 35.0)])
    monkeypatch.setattr(scoring.sd, "FBref", lambda *a, **k: _DummyTeamReader(team_df=df))
    result = scoring._team_possession_map("ENG-Premier League", "2023-2024")
    assert result["Manchester City"] == 65.0
    assert result["Burnley"] == 35.0
    assert result["__league_avg__"] == pytest.approx(50.0)


# --- compute_fit_signal ------------------------------------------------------------------

def test_compute_fit_signal_none_without_a_philosophy():
    result = scoring.compute_fit_signal(
        "FW-MF", "1. Bundesliga", "2023-2024", None, None,
        {"goals_per90": 80.0}, in_possession="", out_of_possession="",
    )
    assert result is None


def test_compute_fit_signal_none_without_target_components():
    result = scoring.compute_fit_signal(
        "FW-MF", "1. Bundesliga", "2023-2024", None, None,
        {}, in_possession="vertical", out_of_possession="high_line",
    )
    assert result is None


def test_compute_fit_signal_defense_group(monkeypatch):
    misc = _misc_df([
        ("Dortmund", "RefPlayer1", "DF", 30.0, 27, 27),   # 1.8/90
        ("Dortmund", "RefPlayer2", "DF", 30.0, 21, 21),   # 1.4/90 -> ref avg raw 1.6/90
        ("SomeOtherClub", "X", "DF", 30.0, 15, 15),        # 1.0/90 -- population
    ])
    team = _team_std_df([("Dortmund", 55.0), ("SomeOtherClub", 45.0)])
    monkeypatch.setattr(scoring.sd, "FBref", lambda *a, **k: _DummyTeamReader(team_df=team, misc_df=misc))
    # target's own components already computed elsewhere (as compute_quality_signal would produce)
    target_components = {"defensive_actions_per90": 90.0}
    result = scoring.compute_fit_signal(
        "DF (CB)", "1. Premier League", "2023-2024", None, None, target_components,
        in_possession="vertical", out_of_possession="high_line",
    )
    assert result is not None
    assert result["reference_club"] == "Borussia Dortmund"
    assert "defensive_actions_per90" in result["reference_components"]
    assert result["label"] in ("Hand-in-Glove Fit", "Somewhat Fits", "Completely Different")


def test_compute_fit_signal_none_when_no_shared_components(monkeypatch):
    # target_components only has a metric the reference profile never produces a value for
    monkeypatch.setattr(scoring.sd, "FBref", lambda *a, **k: _DummyTeamReader(misc_df=pd.DataFrame()))
    monkeypatch.setattr(scoring, "_fbref_misc_population_per90", lambda *a, **k: [])
    result = scoring.compute_fit_signal(
        "DF (CB)", "1. Premier League", "2023-2024", None, None,
        {"defensive_actions_per90": 50.0}, in_possession="vertical", out_of_possession="high_line",
    )
    assert result is None
