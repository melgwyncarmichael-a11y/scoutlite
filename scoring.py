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
import warnings

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
    (primary) position code FBref lists -- with one documented exception, found via the
    Track A eval (2026-09-16): 'DF-MF' with a central/defensive-mid secondary tag (CM/DM) is
    treated as midfield, not defense. Rodri and Declan Rice, both genuine defensive
    midfielders tagged 'DF-MF (CM-DM)', were landing in Defense purely because FBref lists DF
    first -- while Casemiro, the same role tagged plain 'MF (CM-DM)', correctly landed in
    Midfield. A genuine fullback tagged 'DF-MF (FB, right)' (Wan-Bissaka, Trent
    Alexander-Arnold) is unaffected -- the secondary tag is what actually distinguishes the
    two roles, not just which code FBref lists first."""
    if not position:
        return None
    match = re.match(r"([A-Z-]+)(?:\s*\(([^)]*)\))?", position.strip().upper())
    if not match:
        return None
    primary, detail = match.group(1), match.group(2) or ""

    if primary == "DF-MF" and set(re.split(r"[^A-Z]+", detail)) & {"CM", "DM"}:
        return "midfield"

    code = re.split(r"[-\s]", primary)[0]
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


# Same cutoffs as percentile_to_1_5 -- a label reads more honestly than a number that implies
# precision the underlying data doesn't have ("3.4 rounds to a 3"), per user feedback
# (2026-09-17). Word choice matters here: these are what a scout actually reads and reacts to.
QUALITY_LABELS = [
    (20, "Below Rotation"),
    (40, "Depth Option"),
    (60, "Solid Starter"),
    (80, "Strong Starter"),
    (101, "World Class"),
]


def percentile_to_label(pct: float) -> str:
    for cutoff, label in QUALITY_LABELS:
        if pct < cutoff:
            return label
    return QUALITY_LABELS[-1][1]


def _understat_population_per90(
    players: list[dict], position_group: str, field: str, team_title: str | None = None
) -> list[float]:
    """Understat's 'position' field is a space-separated set of every position a player
    appeared in this season (e.g. 'F M S'), not a single primary tag -- match by containment,
    not equality, or most players get excluded entirely.

    team_title (optional): restrict to one squad's players instead of the whole league -- used
    by compute_fit_signal to pull a reference club's own raw values out of the same league pull
    already used to build the population, rather than a second fetch."""
    group_code = {"attack": "F", "midfield": "M", "defense": "D", "goalkeeper": "GK"}[position_group]
    return [
        per90(float(p[field]), float(p["time"]))
        for p in players
        if group_code in p.get("position", "").split()
        and float(p["time"]) >= MIN_MINUTES_FOR_POPULATION
        and (team_title is None or p.get("team_title") == team_title)
    ]


def _fbref_misc_population_per90(misc_df, position_group: str, squad: str | None = None) -> list[float]:
    """squad (optional): restrict to one team's rows -- see _understat_population_per90's
    docstring for why (same reuse pattern, Fit reference-club pull instead of a second fetch)."""
    pos_prefix = {"midfield": "MF", "defense": "DF"}[position_group]
    rows = misc_df[misc_df[("pos", "")].astype(str).str.startswith(pos_prefix)]
    if squad is not None:
        rows = rows[rows.index.get_level_values("team") == squad]
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


def _fbref_keeper_population(keeper_df, squad: str | None = None) -> list[float]:
    min_nineties = MIN_MINUTES_FOR_POPULATION / 90
    rows = keeper_df[keeper_df[("Playing Time", "90s")] >= min_nineties]
    if squad is not None:
        rows = rows[rows.index.get_level_values("team") == squad]
    return [float(v) for v in rows[("Performance", "Save%")].dropna().tolist()]


def _safe_read_player_season_stats(soccerdata_league: str, season: str, stat_type: str, force_refresh: bool):
    """Wraps a live soccerdata/FBref population fetch -- returns None (this module's existing
    'signal not available' convention) rather than crashing the whole Quality/Fit computation
    if the fetch itself fails (network blip, FBref rate-limiting, a soccerdata-internal error).
    Every OTHER 'can't compute this' path in compute_quality_signal/compute_fit_signal already
    degrades gracefully (uncovered league, missing minutes, empty population) -- this brings the
    population fetch itself in line with that, instead of being the one place a transient
    failure took the whole brief down with it (found in a follow-up error-handling review,
    2026-09-24). Always visible via warnings.warn(), same as the PAdj fallback below -- never
    silent the way a bare `except: return None` would be."""
    try:
        sd_reader = sd.FBref(leagues=soccerdata_league, seasons=season, no_cache=force_refresh)
        return sd_reader.read_player_season_stats(stat_type=stat_type)
    except Exception as e:
        warnings.warn(
            f"Couldn't fetch {stat_type!r} population data for {soccerdata_league} {season} "
            f"({e!r}) -- treating this component as unavailable rather than failing the whole signal.",
            RuntimeWarning, stacklevel=2,
        )
        return None


def _team_possession_map(soccerdata_league: str, season: str, force_refresh: bool = False) -> dict[str, float]:
    """squad name -> that team's own-ball possession % for the season, plus a
    '__league_avg__' key for the league-wide average. Backing data for _possession_adjust()."""
    sd_reader = sd.FBref(leagues=soccerdata_league, seasons=season, no_cache=force_refresh)
    team_df = sd_reader.read_team_season_stats(stat_type="standard")
    poss = team_df[("Poss", "")]
    result = {team: float(v) for team, v in zip(team_df.index.get_level_values("team"), poss)}
    result["__league_avg__"] = float(poss.mean())
    return result


def _possession_adjust(value: float, team_possession_pct: float, league_avg_possession_pct: float) -> float:
    """Possession-adjusted (PAdj) defensive volume -- the standard sports-analytics correction
    for a real confound: a dominant-possession team's players face fewer defensive
    opportunities per match than an equal player at a team that spends more time without the
    ball, so their raw defensive counts are naturally lower for reasons that have nothing to do
    with individual quality (found via user feedback on the Quality signal, 2026-09-17).
    Scales by the ratio of league-average opponent-possession to this team's own actual
    opponent-possession (100 - the team's own possession%): a team that dominates the ball
    faces a low-possession opponent, so its players' raw counts scale UP to correct for having
    fewer chances to make a defensive play; a team with little of the ball faces a
    high-possession opponent and scales DOWN, since its raw counts are inflated by sheer
    opportunity volume rather than necessarily individual quality.

    Deliberately a simpler application than a full industry PAdj: only the individual value
    being evaluated is adjusted here, not the whole comparison population -- see
    compute_quality_signal's and compute_fit_signal's docstrings for why that's disclosed as a
    known simplification rather than presented as fully rigorous."""
    opponent_possession = 100.0 - team_possession_pct
    if opponent_possession <= 0:
        return value
    return value * (league_avg_possession_pct / opponent_possession)


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

# Percentile-point spread beyond which averaging is judged to be hiding more than it reveals.
# Found via the Track A2 eval (2026-09-16): Haaland's components were 100th/99th percentile on
# goals/xG but only 56th/53rd on assists/xA -- averaged to 77, just under the cutoff for 5/5,
# understating the one thing (finishing) that actually makes him elite. A single blended number
# can't distinguish "genuinely average all-round" from "a specialist whose off-trait drags the
# average down" -- this doesn't fix the math, it just says so when the gap is wide enough to
# matter.
SPECIALIST_SPREAD_THRESHOLD = 40


def _specialist_caveat(components: dict) -> str | None:
    """Pure function: given the computed percentile components, decide whether their spread is
    wide enough to warrant flagging that the composite score may be masking a specialist's
    peak trait. None below the threshold or with fewer than 2 components (nothing to spread)."""
    if len(components) < 2:
        return None
    spread = max(components.values()) - min(components.values())
    if spread <= SPECIALIST_SPREAD_THRESHOLD:
        return None
    return (
        f"This player's individual metrics vary widely (a {spread:.0f}-percentile-point "
        "spread) -- the composite score above may understate whichever specific trait they're "
        "actually best known for."
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
    raw_components = {}  # identical to components except defensive_actions_per90, pre-PAdj

    # A component is only added when its reference population is non-empty. percentile_rank()
    # returns 50.0 ("neutral") for an empty population -- fine as a fallback for THAT function,
    # but silently averaging one or more of those into the signal produces a real-looking score
    # built on zero actual data. Found via a real capture: early in a season (a handful of games
    # in), essentially no player league-wide has crossed MIN_MINUTES_FOR_POPULATION yet, so the
    # WHOLE population comes back empty -- every component fell back to exactly 50.0, and the
    # signal reported a normal-looking "3/5" that was actually measuring nothing (Kylian Mbappe,
    # 2026-2027, 4 games in -- see NOTES.md). Skipping empty-population components here means
    # the final `if not components: return None` below now catches that case correctly, the
    # same way it already catches an uncovered league or missing data.
    if group == "goalkeeper":
        if soccerdata_league is None or keeper is None or not keeper.get("save_pct"):
            return None
        keeper_df = _safe_read_player_season_stats(soccerdata_league, season, "keeper", force_refresh)
        if keeper_df is not None:
            keeper_pop = _fbref_keeper_population(keeper_df)
            if keeper_pop:
                components["save_pct"] = percentile_rank(float(keeper["save_pct"]), keeper_pop)
                raw_components["save_pct"] = components["save_pct"]  # save% isn't possession-volume-driven, no PAdj

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
                        if pop:
                            components[key] = percentile_rank(per90(float(xg[field]), float(xg["minutes"])), pop)
                            raw_components[key] = components[key]  # attacking output isn't PAdj'd -- see _possession_adjust
                elif group == "midfield":
                    kp_pop = _understat_population_per90(players, group, "key_passes")
                    xa_pop = _understat_population_per90(players, group, "xA")
                    if kp_pop:
                        components["key_passes_per90"] = percentile_rank(per90(float(xg["key_passes"]), float(xg["minutes"])), kp_pop)
                        raw_components["key_passes_per90"] = components["key_passes_per90"]
                    if xa_pop:
                        components["xA_per90"] = percentile_rank(per90(float(xg["xA"]), float(xg["minutes"])), xa_pop)
                        raw_components["xA_per90"] = components["xA_per90"]

        if group in ("midfield", "defense") and soccerdata_league and misc:
            misc_df = _safe_read_player_season_stats(soccerdata_league, season, "misc", force_refresh)
            def_pop = _fbref_misc_population_per90(misc_df, group) if misc_df is not None else []
            if def_pop:
                def_value = per90(
                    float(misc.get("interceptions", 0) or 0) + float(misc.get("tackles_won", 0) or 0), minutes
                )
                raw_components["defensive_actions_per90"] = percentile_rank(def_value, def_pop)
                # PAdj (possession-adjusted): scale this player's own raw value by their team's
                # own-ball possession share before ranking it against the (unadjusted)
                # population -- see _possession_adjust()'s docstring for the mechanism and the
                # disclosed simplification (only the individual value is adjusted, not the
                # whole population). Falls back to the raw percentile if team possession data
                # isn't available for any reason, rather than failing the whole signal over it.
                try:
                    poss_map = _team_possession_map(soccerdata_league, season, force_refresh=force_refresh)
                    team_poss = poss_map.get(stats.get("squad", ""))
                    if team_poss is not None:
                        adjusted_value = _possession_adjust(def_value, team_poss, poss_map["__league_avg__"])
                        components["defensive_actions_per90"] = percentile_rank(adjusted_value, def_pop)
                    else:
                        components["defensive_actions_per90"] = raw_components["defensive_actions_per90"]
                except Exception as e:
                    # Deliberately still a broad catch (team-possession data comes from a live
                    # soccerdata/FBref fetch, whose failure modes aren't fully enumerable from
                    # here) -- but always surfaced via warnings.warn rather than swallowed
                    # silently, so a genuine bug doesn't look identical to "no possession data
                    # this season" the way a bare `except: pass` would (found in a dependency/
                    # architecture audit, 2026-09-21).
                    warnings.warn(
                        f"Possession adjustment unavailable for {stats.get('squad', 'unknown squad')} "
                        f"({e!r}) -- falling back to the unadjusted defensive percentile.",
                        RuntimeWarning, stacklevel=2,
                    )
                    components["defensive_actions_per90"] = raw_components["defensive_actions_per90"]

    if not components:
        return None

    avg_pct = sum(components.values()) / len(components)
    raw_avg_pct = sum(raw_components.values()) / len(raw_components) if raw_components else avg_pct
    return {
        "score": percentile_to_1_5(avg_pct),
        "label": percentile_to_label(avg_pct),
        "position_group": group,
        "components": components,
        "raw_components": raw_components,
        "avg_percentile": round(avg_pct, 1),
        "raw_avg_percentile": round(raw_avg_pct, 1),
        "raw_label": percentile_to_label(raw_avg_pct),
        "explanation": describe_quality(group, comp_level),
        "specialist_caveat": _specialist_caveat(components),
    }


# ============================================================================================
# Fit signal (v3, 2026-09-17) -- deterministic, not LLM-judged. Previously the LLM produced a
# numeric "Fit: X/5" by reasoning from a text description of the club philosophy; the Track C
# eval (2026-09-16) found this landed on exactly 3/5 in 21 of 21 test runs across every
# possible philosophy combination -- the model correctly refusing to guess at pace/pressing
# data no ScoutLite source has, but the consequence was a signal that never actually moved.
#
# Redesigned around a different question: not "is this player good" (that's Quality's job),
# but "does this player's statistical SHAPE resemble the players who already play this club's
# system" -- a real club's current squad, in the same position group, as the reference point.
# Close resemblance -> Hand-in-Glove Fit; distant -> Completely Different. The LLM's job
# narrows to explaining the comparison in prose, not deciding the number.
# ============================================================================================

# One real, named club per philosophy combination -- a deliberate choice over an abstract
# statistical template, so the brief can say "compared to Dortmund's attackers" instead of
# "compared to a vertical/high-line archetype." fbref_squad and understat_team differ because
# the two sites don't always agree on a club's name (confirmed empirically, 2026-09-17):
# FBref's team-season tables say "Dortmund" and "Atlético Madrid" (accented); Understat's
# player data says "Borussia Dortmund" and "Atletico Madrid" (unaccented). comp_level is in
# the same "N. League Name" format used everywhere else in this codebase, reusing
# fbref_comp_to_understat_league/fbref_comp_to_soccerdata_league rather than a new mapping.
REFERENCE_CLUBS = {
    ("vertical", "high_line"): {
        "display_name": "Borussia Dortmund", "fbref_squad": "Dortmund",
        "understat_team": "Borussia Dortmund", "comp_level": "1. Bundesliga",
    },
    ("vertical", "mid_block"): {
        "display_name": "Real Madrid", "fbref_squad": "Real Madrid",
        "understat_team": "Real Madrid", "comp_level": "1. La Liga",
    },
    ("vertical", "low_block"): {
        "display_name": "Atlético Madrid", "fbref_squad": "Atlético Madrid",
        "understat_team": "Atletico Madrid", "comp_level": "1. La Liga",
    },
    ("possession", "high_line"): {
        "display_name": "Manchester City", "fbref_squad": "Manchester City",
        "understat_team": "Manchester City", "comp_level": "1. Premier League",
    },
    ("possession", "mid_block"): {
        "display_name": "Bayern Munich", "fbref_squad": "Bayern Munich",
        "understat_team": "Bayern Munich", "comp_level": "1. Bundesliga",
    },
    ("possession", "low_block"): {
        "display_name": "Brighton", "fbref_squad": "Brighton",
        "understat_team": "Brighton", "comp_level": "1. Premier League",
    },
}

# Average absolute percentile-point difference between the target's profile and the reference
# club's average profile, per shared component. Hand-in-Glove cutoff raised 15 -> 20 after
# Track C2 (eval/TRACK_C2_REPORT.md, 2026-09-18): two genuine standout players (Haaland vs.
# Man City, Kimmich vs. Bayern) landed just past the old 15 cutoff at 16.0-17.1, even though
# comparing a standout against his own squad's positional average -- which includes weaker
# depth -- will always show some real gap. 35 is left alone; Track C2 found the volatility on
# the low side, not evidence either way about the high cutoff. Still a first pass past this
# point, not a fully tuned scale.
FIT_LABELS = [
    (20, "Hand-in-Glove Fit"),
    (35, "Somewhat Fits"),
]


def _fit_label(avg_abs_diff: float) -> str:
    for cutoff, label in FIT_LABELS:
        if avg_abs_diff < cutoff:
            return label
    return "Completely Different"


def compute_fit_signal(
    position: str,
    comp_level: str,
    season: str,
    misc: dict | None,
    xg: dict | None,
    target_components: dict,
    in_possession: str,
    out_of_possession: str,
    force_refresh: bool = False,
) -> dict | None:
    """Deterministic Fit signal. target_components is compute_quality_signal's own 'components'
    dict for this same player -- Fit reuses it rather than recomputing, since it's already the
    player's percentile profile. Returns None if no philosophy was given, the position/league
    isn't covered, or there's no shared metric to compare on -- 'fail visibly' rather than
    fabricate, same convention as compute_quality_signal."""
    group = classify_position_group(position)
    if group is None or not target_components or not (in_possession and out_of_possession):
        return None
    ref = REFERENCE_CLUBS.get((in_possession, out_of_possession))
    if ref is None:
        return None

    ref_components: dict[str, float] = {}

    if group == "goalkeeper":
        ref_league = fbref_comp_to_soccerdata_league(ref["comp_level"])
        if ref_league is None:
            return None
        keeper_df = _safe_read_player_season_stats(ref_league, season, "keeper", force_refresh)
        if keeper_df is not None:
            population = _fbref_keeper_population(keeper_df)
            ref_values = _fbref_keeper_population(keeper_df, squad=ref["fbref_squad"])
            if population and ref_values:
                ref_components["save_pct"] = sum(percentile_rank(v, population) for v in ref_values) / len(ref_values)

    else:
        ref_understat_league = fbref_comp_to_understat_league(ref["comp_level"])
        ref_soccerdata_league = fbref_comp_to_soccerdata_league(ref["comp_level"])
        ref_year = fbref_season_to_understat_year(season)

        if group in ("attack", "midfield") and ref_understat_league:
            try:
                players = fetch_league_players_safe(ref_understat_league, ref_year, force_refresh=force_refresh)
            except UnderstatUnavailable:
                players = None
            if players is not None:
                fields = (
                    [("goals", "goals_per90"), ("assists", "assists_per90"), ("xG", "xG_per90"), ("xA", "xA_per90")]
                    if group == "attack" else
                    [("key_passes", "key_passes_per90"), ("xA", "xA_per90")]
                )
                for field, key in fields:
                    population = _understat_population_per90(players, group, field)
                    ref_values = _understat_population_per90(players, group, field, team_title=ref["understat_team"])
                    if population and ref_values:
                        ref_components[key] = sum(percentile_rank(v, population) for v in ref_values) / len(ref_values)

        if group in ("midfield", "defense") and ref_soccerdata_league:
            misc_df = _safe_read_player_season_stats(ref_soccerdata_league, season, "misc", force_refresh)
            population = _fbref_misc_population_per90(misc_df, group) if misc_df is not None else []
            ref_values = _fbref_misc_population_per90(misc_df, group, squad=ref["fbref_squad"]) if misc_df is not None else []
            if population and ref_values:
                # Same PAdj treatment as compute_quality_signal's defensive component: adjust
                # each reference player's raw value by the reference CLUB's own possession
                # share (one factor, since they all play for the same team) before ranking
                # against the (unadjusted) population.
                try:
                    poss_map = _team_possession_map(ref_soccerdata_league, season, force_refresh=force_refresh)
                    team_poss = poss_map.get(ref["fbref_squad"])
                    if team_poss is not None:
                        ref_values = [
                            _possession_adjust(v, team_poss, poss_map["__league_avg__"]) for v in ref_values
                        ]
                except Exception as e:
                    # Same deliberate-but-visible tradeoff as compute_quality_signal's PAdj
                    # fallback above -- fall back to unadjusted reference values rather than
                    # fail the whole Fit signal, but never silently (2026-09-21 audit).
                    warnings.warn(
                        f"Possession adjustment unavailable for reference club {ref['fbref_squad']!r} "
                        f"({e!r}) -- falling back to unadjusted reference values.",
                        RuntimeWarning, stacklevel=2,
                    )
                ref_components["defensive_actions_per90"] = sum(percentile_rank(v, population) for v in ref_values) / len(ref_values)

    if not ref_components:
        return None

    shared_keys = set(target_components) & set(ref_components)
    if not shared_keys:
        return None
    avg_abs_diff = sum(abs(target_components[k] - ref_components[k]) for k in shared_keys) / len(shared_keys)

    return {
        "reference_club": ref["display_name"],
        "position_group": group,
        "target_components": {k: target_components[k] for k in shared_keys},
        "reference_components": {k: round(ref_components[k], 1) for k in shared_keys},
        "avg_abs_diff": round(avg_abs_diff, 1),
        "label": _fit_label(avg_abs_diff),
    }
