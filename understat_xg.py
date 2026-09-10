#!/usr/bin/env python3
"""
Understat xG/xA lookup, by player name within a league+season.

IMPORTANT -- access note: understat.com's robots.txt is a blanket `Disallow: /` for every
user agent, no exceptions (checked 2026-08-22). This module fetches it anyway, on the
project owner's explicit direction after being shown that finding -- it is a deliberate
override, not an oversight. See NOTES.md for the full reasoning.

Mechanically this is simple: understat.com's league pages load their data from a JSON
endpoint (getLeagueData/<league>/<year>) rather than a static page. It needs a session
cookie from the league page first and a Referer header, but no browser automation, no
Cloudflare, no rate-limit wall was observed.

Coverage: only the 6 leagues Understat tracks (top 5 European leagues + Russian Premier
League). Players outside those leagues will not be found here.
"""
import unicodedata

import requests

import cache

UNDERSTAT_LEAGUES = {
    "premier league": "EPL",
    "la liga": "La liga",
    "bundesliga": "Bundesliga",
    "serie a": "Serie A",
    "ligue 1": "Ligue 1",
    "russian premier league": "RFPL",
}


def fbref_comp_to_understat_league(comp_level: str) -> str | None:
    """Map an FBref 'comp_level' string (e.g. '1. Premier League') to an Understat league slug."""
    name = comp_level.split(".", 1)[-1].strip().lower()
    return UNDERSTAT_LEAGUES.get(name)


def fbref_season_to_understat_year(season: str) -> str:
    """Map an FBref season string ('2025-2026' or '2026') to Understat's year param (start year)."""
    return season.split("-")[0]


def _normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().replace("-", " ").strip()


def _name_tokens(name: str) -> set[str]:
    return set(_normalize_name(name).split())


def fetch_league_players(league: str, year: str, force_refresh: bool = False) -> list[dict]:
    """Quick mode (default): serves a cached league-wide pull if within
    cache.UNDERSTAT_POPULATION_TTL_HOURS. Fresh mode: always fetches live, still updates the
    cache afterward. One flat TTL regardless of historical/current -- unlike FBref, this is a
    single cheap request with no ban risk, so the main value of caching it is avoiding
    redundant re-fetches of the same league within a short window, not protecting a rate limit."""
    cache_key = f"{league}:{year}"
    if not force_refresh:
        cached = cache.get_cached_understat_population(cache_key)
        if cached:
            players, fetched_at = cached
            if not cache.is_stale(fetched_at, cache.UNDERSTAT_POPULATION_TTL_HOURS):
                return players

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    league_url = f"https://understat.com/league/{league}"
    session.get(league_url, timeout=15)  # picks up session cookies

    api_url = f"https://understat.com/getLeagueData/{league}/{year}"
    response = session.get(
        api_url,
        headers={"Referer": league_url, "X-Requested-With": "XMLHttpRequest"},
        timeout=15,
    )
    response.raise_for_status()
    players = response.json().get("players", [])
    cache.set_cached_understat_population(cache_key, players)
    return players


def find_player_xg(players: list[dict], player_name: str, team_hint: str = "") -> dict | None:
    target = _normalize_name(player_name)
    team_target = _normalize_name(team_hint) if team_hint else ""

    candidates = [p for p in players if _normalize_name(p["player_name"]) == target]
    if not candidates:
        # Compound/extra surnames trip up an exact match -- e.g. FBref/common usage says
        # "Kylian Mbappe" but Understat lists "Kylian Mbappe-Lottin". Fall back to: every
        # word in the search name appears somewhere in the candidate's name (order-
        # independent, handles the extra surname component either source might add).
        search_tokens = _name_tokens(player_name)
        candidates = [
            p for p in players
            if search_tokens and search_tokens.issubset(_name_tokens(p["player_name"]))
        ]
    if not candidates:
        return None
    if len(candidates) > 1 and team_target:
        narrowed = [p for p in candidates if team_target in _normalize_name(p["team_title"])]
        if narrowed:
            candidates = narrowed

    p = candidates[0]
    return {
        "understat_matched_name": p["player_name"],  # verify this is really the searched player
        "understat_team": p["team_title"],
        "games": p["games"],
        "minutes": p["time"],
        "goals": p["goals"],
        "xG": round(float(p["xG"]), 2),
        "assists": p["assists"],
        "xA": round(float(p["xA"]), 2),
        "npxG": round(float(p["npxG"]), 2),
        "shots": p["shots"],
        "key_passes": p["key_passes"],
    }


class UnderstatUnavailable(Exception):
    """Understat couldn't be reached (timeout, connection error, bad response). xG/xA is
    optional data -- callers should degrade gracefully, not abort the whole brief."""


def get_player_xg(
    player_name: str, comp_level: str, season: str, team_hint: str = "", force_refresh: bool = False
) -> dict | None:
    """High-level lookup: FBref-style comp_level/season -> Understat xG data, or None if the
    league isn't covered by Understat or the player isn't found in it. A network failure
    reaching Understat also returns None (xG/xA is optional) rather than raising -- see
    fetch_league_players_safe."""
    league = fbref_comp_to_understat_league(comp_level)
    if league is None:
        return None
    year = fbref_season_to_understat_year(season)
    try:
        players = fetch_league_players(league, year, force_refresh=force_refresh)
    except (requests.RequestException, ValueError):
        return None
    return find_player_xg(players, player_name, team_hint)


def fetch_league_players_safe(league: str, year: str, force_refresh: bool = False) -> list[dict]:
    """Like fetch_league_players, but raises UnderstatUnavailable on any network/parse failure
    so a caller (e.g. the Quality signal) can distinguish 'Understat is down' from 'no players
    matched' and skip the affected score components instead of aborting."""
    try:
        return fetch_league_players(league, year, force_refresh=force_refresh)
    except (requests.RequestException, ValueError) as e:
        raise UnderstatUnavailable(str(e)) from e
