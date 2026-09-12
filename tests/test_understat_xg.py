"""Understat name-matching and mapping -- pure, no network."""
import pytest

import understat_xg as u


@pytest.mark.parametrize("comp,expected", [
    ("1. Premier League", "EPL"),
    ("1. La Liga", "La liga"),
    ("1. Bundesliga", "Bundesliga"),
    ("3. League One", None),
])
def test_comp_to_understat_league(comp, expected):
    assert u.fbref_comp_to_understat_league(comp) == expected


@pytest.mark.parametrize("season,year", [("2025-2026", "2025"), ("2023-2024", "2023"), ("2026", "2026")])
def test_season_to_understat_year(season, year):
    assert u.fbref_season_to_understat_year(season) == year


def test_normalize_name_strips_accents_and_hyphens():
    assert u._normalize_name("Vinícius Júnior") == "vinicius junior"
    assert u._normalize_name("Kylian Mbappé-Lottin") == "kylian mbappe lottin"


def _pop():
    return [
        {"id": "8260", "player_name": "Erling Haaland", "team_title": "Manchester City", "games": "31",
         "time": "2552", "goals": "27", "xG": "28.8", "assists": "5", "xA": "5.5",
         "npxG": "25.7", "shots": "122", "key_passes": "25"},
        {"id": "1234", "player_name": "Kylian Mbappe-Lottin", "team_title": "Real Madrid", "games": "30",
         "time": "2600", "goals": "25", "xG": "26.0", "assists": "6", "xA": "7.0",
         "npxG": "19.0", "shots": "140", "key_passes": "60"},
        {"id": "5555", "player_name": "Danny Ward", "team_title": "Leicester City", "games": "10",
         "time": "900", "goals": "0", "xG": "0", "assists": "0", "xA": "0",
         "npxG": "0", "shots": "0", "key_passes": "0"},
        {"id": "6666", "player_name": "Danny Ward", "team_title": "Huddersfield Town", "games": "12",
         "time": "1000", "goals": "1", "xG": "1", "assists": "1", "xA": "1",
         "npxG": "1", "shots": "5", "key_passes": "5"},
    ]


def test_exact_match():
    r = u.find_player_xg(_pop(), "Erling Haaland")
    assert r["understat_matched_name"] == "Erling Haaland"
    assert r["xG"] == 28.8
    assert r["understat_url"] == "https://understat.com/player/8260"


def test_missing_id_gives_no_url_not_a_crash():
    pop = [{"player_name": "No Id Guy", "team_title": "Some FC", "games": "1", "time": "90",
            "goals": "0", "xG": "0", "assists": "0", "xA": "0", "npxG": "0", "shots": "0", "key_passes": "0"}]
    r = u.find_player_xg(pop, "No Id Guy")
    assert r["understat_url"] is None


def test_compound_surname_fallback():
    # searched "Kylian Mbappe", Understat lists "Kylian Mbappe-Lottin" -- token-subset fallback
    r = u.find_player_xg(_pop(), "Kylian Mbappe")
    assert r is not None
    assert r["understat_matched_name"] == "Kylian Mbappe-Lottin"


def test_abbreviation_still_misses_documented_limitation():
    # "Jr" != "Junior" as a token -- neither exact nor subset match. Known, disclosed gap.
    pop = [{"player_name": "Vinicius Junior", "team_title": "Real Madrid", "games": "1", "time": "90",
            "goals": "0", "xG": "0", "assists": "0", "xA": "0", "npxG": "0", "shots": "0", "key_passes": "0"}]
    assert u.find_player_xg(pop, "Vinicius Jr") is None


def test_team_hint_disambiguates_same_name():
    r = u.find_player_xg(_pop(), "Danny Ward", team_hint="Huddersfield")
    assert r["understat_team"] == "Huddersfield Town"


def test_no_match_returns_none():
    assert u.find_player_xg(_pop(), "Zxqv Nonexistent") is None
