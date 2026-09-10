#!/usr/bin/env python3
"""
ScoutLite Quality signal (1-5): a non-AI, rule-based baseline per the Technical Vision doc --
percentile-rank the player's per-90 stats against a real reference population (same league +
season), average the percentiles for their position group, map to 1-5 via fixed cutoffs.
No LLM involved in this number at all; the LLM is reserved for the Fit signal and prose.

Position groups (revised from the original doc spec after verifying data availability --
progressive passes/carries and a true duel-success-rate are NOT available on free FBref pages,
confirmed against both FBref's own "On this page" table-of-contents and Understat's actual
getPlayerData API response, not just their page labels -- see NOTES.md):
  - Attack:     goals/90, assists/90, xG/90, xA/90                    (Understat population)
  - Midfield:   key_passes/90, xA/90, (interceptions+tackles_won)/90  (Understat + FBref misc)
  - Defense:    (interceptions+tackles_won)/90                       (FBref misc population)
  - Goalkeeper: save% (already a rate, no per-90 needed)              (FBref keeper population)

Each metric's percentile is computed against its own single source's full population --
deliberately avoids merging Understat and FBref player-by-player for the reference population
(that name-matching fragility is only worth accepting for OUR ONE target player, not for
every player in a 400+ player league population where a few mismatches would be invisible
noise anyway).
"""
import re

import soccerdata as sd

from understat_xg import (
    UnderstatUnavailable,
    fbref_comp_to_understat_league,
    fbref_season_to_understat_year,
    fetch_league_players_safe,
)

SOCCERDATA_LEAGUES = {
    "premier league": "ENG-Premier League",
    "la liga": "ESP-La Liga",
    "bundesliga": "GER-Bundesliga",
    "serie a": "ITA-Serie A",
    "ligue 1": "FRA-Ligue 1",
}

MIN_MINUTES_FOR_POPULATION = 450  # ~5 full matches -- excludes small-sample noise from the reference


def fbref_comp_to_soccerdata_league(comp_level: str) -> str | None:
    name = comp_level.split(".", 1)[-1].strip().lower()
    return SOCCERDATA_LEAGUES.get(name)


def classify_position_group(position: str) -> str | None:
    """FBref position strings look like 'FW-MF', 'DF (CB)', 'GK', 'MF'. Takes the first
    (primary) position code FBref lists."""
    if not position:
        return None
    code = re.split(r"[-\s(]", position.strip())[0].upper()
    return {"GK": "goalkeeper", "DF": "defense", "MF": "midfield", "FW": "attack"}.get(code)


def per90(count: float, minutes: float) -> float:
    if not minutes:
        return 0.0
    return count / (minutes / 90)


def percentile_rank(value: float, population: list[float]) -> float:
    """% of the population this value is greater than or equal to. 0 population -> 50 (neutral)."""
    population = [p for p in population if p is not None]
    if not population:
        return 50.0
    below_or_equal = sum(1 for p in population if p <= value)
    return 100 * below_or_equal / len(population)


def percentile_to_1_5(pct: float) -> int:
    if pct < 20:
        return 1
    if pct < 40:
        return 2
    if pct < 60:
        return 3
    if pct < 80:
        return 4
    return 5


def _understat_population_per90(players: list[dict], position_group: str, field: str) -> list[float]:
    """Understat's 'position' field is a space-separated set of every position a player
    appeared in this season (e.g. 'F M S'), not a single primary tag -- match by containment,
    not equality, or most players get excluded entirely."""
    group_code = {"attack": "F", "midfield": "M", "defense": "D", "goalkeeper": "GK"}[position_group]
    return [
        per90(float(p[field]), float(p["time"]))
        for p in players
        if group_code in p.get("position", "").split() and float(p["time"]) >= MIN_MINUTES_FOR_POPULATION
    ]


def _fbref_misc_population_per90(misc_df, position_group: str) -> list[float]:
    pos_prefix = {"midfield": "MF", "defense": "DF"}[position_group]
    rows = misc_df[misc_df[("pos", "")].astype(str).str.startswith(pos_prefix)]
    out = []
    min_nineties = MIN_MINUTES_FOR_POPULATION / 90
    for _, row in rows.iterrows():
        nineties = row[("90s", "")]
        if not nineties or nineties < min_nineties:
            continue
        interceptions = row[("Performance", "Int")] or 0
        tackles_won = row[("Performance", "TklW")] or 0
        out.append((float(interceptions) + float(tackles_won)) / float(nineties))
    return out


def _fbref_keeper_population(keeper_df) -> list[float]:
    min_nineties = MIN_MINUTES_FOR_POPULATION / 90
    rows = keeper_df[keeper_df[("Playing Time", "90s")] >= min_nineties]
    return [float(v) for v in rows[("Performance", "Save%")].dropna().tolist()]


GROUP_METRIC_DESCRIPTIONS = {
    "attack": "goals, assists, xG and xA per 90 minutes",
    "midfield": "key passes and xA per 90 (creativity) plus interceptions + tackles won per 90 (defensive work)",
    "defense": "interceptions + tackles won per 90 minutes",
    "goalkeeper": "save percentage",
}

CONTEXT_CAVEAT = (
    "Doesn't account for team style or opposition quality -- a low score can reflect a "
    "team's system as much as individual quality."
)


def describe_quality(group: str, comp_level: str) -> str:
    """One-line, fully mechanical explanation of what a Quality score is actually measuring --
    no team-specific claims (e.g. never asserts a team 'plays possession football'), since
    that's not something any of our sources tell us. See NOTES.md for the reasoning."""
    league = comp_level.split(".", 1)[-1].strip()
    role = {"attack": "an attacker", "midfield": "a midfielder", "defense": "a defender", "goalkeeper": "a goalkeeper"}[group]
    metrics = GROUP_METRIC_DESCRIPTIONS[group]
    return (
        f"Evaluated as {role}: {metrics}, ranked against {league} players in the same position "
        f"group with {MIN_MINUTES_FOR_POPULATION}+ minutes this season. {CONTEXT_CAVEAT}"
    )


def compute_quality_signal(
    position: str,
    comp_level: str,
    season: str,
    player_name: str,
    stats: dict,
    misc: dict | None,
    keeper: dict | None,
    xg: dict | None,
    force_refresh: bool = False,
) -> dict | None:
    """Returns {'score': 1-5, 'position_group': str, 'components': {metric: percentile}} or
    None if the league isn't covered or the position/data needed isn't available.

    force_refresh (Fresh mode) also bypasses soccerdata's own on-disk cache for the reference
    population pulls (its no_cache option), not just our Understat cache -- so Fresh mode is
    consistent across every data source this function touches."""
    group = classify_position_group(position)
    if group is None:
        return None

    understat_league = fbref_comp_to_understat_league(comp_level)
    soccerdata_league = fbref_comp_to_soccerdata_league(comp_level)
    components = {}

    if group == "goalkeeper":
        if soccerdata_league is None or keeper is None or not keeper.get("save_pct"):
            return None
        sd_reader = sd.FBref(leagues=soccerdata_league, seasons=season, no_cache=force_refresh)
        keeper_pop = _fbref_keeper_population(sd_reader.read_player_season_stats(stat_type="keeper"))
        components["save_pct"] = percentile_rank(float(keeper["save_pct"]), keeper_pop)

    else:
        minutes = float(str(stats.get("minutes", "0")).replace(",", "") or 0)
        if minutes == 0:
            return None

        if group in ("attack", "midfield") and understat_league and xg:
            year = fbref_season_to_understat_year(season)
            try:
                players = fetch_league_players_safe(understat_league, year, force_refresh=force_refresh)
            except UnderstatUnavailable:
                players = None  # skip the Understat-based components rather than abort
            if players is not None:
                if group == "attack":
                    for field, key in [("goals", "goals_per90"), ("assists", "assists_per90"), ("xG", "xG_per90"), ("xA", "xA_per90")]:
                        pop = _understat_population_per90(players, group, field)
                        components[key] = percentile_rank(per90(float(xg[field]), float(xg["minutes"])), pop)
                elif group == "midfield":
                    kp_pop = _understat_population_per90(players, group, "key_passes")
                    xa_pop = _understat_population_per90(players, group, "xA")
                    components["key_passes_per90"] = percentile_rank(per90(float(xg["key_passes"]), float(xg["minutes"])), kp_pop)
                    components["xA_per90"] = percentile_rank(per90(float(xg["xA"]), float(xg["minutes"])), xa_pop)

        if group in ("midfield", "defense") and soccerdata_league and misc:
            sd_reader = sd.FBref(leagues=soccerdata_league, seasons=season, no_cache=force_refresh)
            misc_df = sd_reader.read_player_season_stats(stat_type="misc")
            def_pop = _fbref_misc_population_per90(misc_df, group)
            def_value = per90(
                float(misc.get("interceptions", 0) or 0) + float(misc.get("tackles_won", 0) or 0), minutes
            )
            components["defensive_actions_per90"] = percentile_rank(def_value, def_pop)

    if not components:
        return None

    avg_pct = sum(components.values()) / len(components)
    return {
        "score": percentile_to_1_5(avg_pct),
        "position_group": group,
        "components": components,
        "avg_percentile": round(avg_pct, 1),
        "explanation": describe_quality(group, comp_level),
    }
