#!/usr/bin/env python3
"""
ScoutLite MVP slice: one player name -> FBref season stats -> one LLM call -> one paragraph.

Data source: FBref only. Scraping is permitted but rate-limited to <10 requests/min
(violations risk a block of up to 24h), so every request is paced at ~6.5-8s with jitter.
FBref sits behind Cloudflare's bot challenge, which blocks plain HTTP (requests/curl) and
standard headless automation (Playwright/Selenium) alike -- only an undetected browser
driver (seleniumbase's uc=True mode) gets through, so that's what this script uses.
"""
import argparse
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from seleniumbase import Driver

import cache

RATE_LIMIT_SECONDS = 6.5
JITTER_SECONDS = 1.5

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def pace():
    delay = RATE_LIMIT_SECONDS + random.uniform(0, JITTER_SECONDS)
    print(f"[pacing] sleeping {delay:.1f}s before FBref request (rate-limit compliance)...")
    time.sleep(delay)


def _uc_fetch(url: str) -> tuple[str, str]:
    """Paced, undetected-browser fetch of a single URL. Returns (final_url, html)."""
    driver = Driver(uc=True, headless=True)
    try:
        pace()
        driver.uc_open_with_reconnect(url, reconnect_time=6)
        driver.sleep(3)
        return driver.get_current_url(), driver.get_page_source()
    finally:
        driver.quit()


def search_player(player_name: str, force_refresh: bool = False) -> list[dict]:
    """Search FBref for a player name. Returns every candidate FBref could match -- does NOT
    auto-pick one. Caller must confirm which candidate to use, then call get_player_page()
    with its 'url' to get the actual page (instant if this was a single-match resolution,
    since that page gets cached below as a side effect).

    Each candidate: {name, url, years_active, nationality, alt_name, clubs}.
    years_active/nationality/alt_name/clubs are "" when unknown (always true for the single-
    match case, since that info only appears on the search-results page, not the player page).

    Quick mode (default): serves a cached candidate list if one exists and isn't older than
    cache.SEARCH_RESULTS_TTL_HOURS. Fresh mode (force_refresh=True): always searches live, but
    still updates the cache afterward so the next Quick-mode search benefits.
    """
    query_key = player_name.strip().lower()
    if not force_refresh:
        cached = cache.get_cached_search(query_key)
        if cached:
            candidates, fetched_at = cached
            if not cache.is_stale(fetched_at, cache.SEARCH_RESULTS_TTL_HOURS):
                return candidates

    search_url = f"https://fbref.com/en/search/search.fcgi?search={quote(player_name)}"
    current_url, html = _uc_fetch(search_url)

    if "/search/" not in current_url:
        # FBref auto-redirected: exactly one unambiguous match. We already have the page --
        # cache it directly so a subsequent get_player_page() call is instant, not a second fetch.
        cache.set_cached_player_page(current_url, html)
        soup = BeautifulSoup(html, "lxml")
        name_el = soup.select_one("#meta h1 span")
        candidates = [{
            "name": name_el.text.strip() if name_el else player_name,
            "url": current_url,
            "years_active": "",
            "nationality": "",
            "alt_name": "",
            "clubs": "",
        }]
    else:
        soup = BeautifulSoup(html, "lxml")
        candidates = []
        for item in soup.select("div.search-item"):
            name_div = item.select_one("div.search-item-name")
            link = name_div.select_one("a") if name_div else None
            if not link:
                continue
            parts = [p.strip() for p in name_div.get_text(" ", strip=True).split("\xb7")]
            alt_el = item.select_one("div.search-item-alt-names")
            clubs_el = item.select_one("div.search-item-team")
            candidates.append({
                "name": link.get_text(strip=True),
                "url": "https://fbref.com" + link["href"],
                "years_active": parts[1] if len(parts) > 1 else "",
                "nationality": parts[2] if len(parts) > 2 else "",
                "alt_name": alt_el.get_text(strip=True) if alt_el else "",
                "clubs": clubs_el.get_text(strip=True).removeprefix("Clubs:").strip() if clubs_el else "",
            })
        if not candidates:
            raise RuntimeError(f"No FBref match found for '{player_name}'")

    cache.set_cached_search(query_key, candidates)
    return candidates


def get_player_page(url: str, requested_season: str | None = None, force_refresh: bool = False) -> tuple[str, str]:
    """Fetch a specific, already-identified FBref player URL. Used once the caller has
    confirmed which search_player() candidate to proceed with.

    Quick mode (default): serves the cached page if it's within cache.PLAYER_PAGE_TTL_HOURS
    OR if requested_season is a season in that cached page that is NOT its most-recent one --
    historical season data is immutable, so an old cache is still 100% correct for it
    regardless of age. Fresh mode (force_refresh=True): always fetches live, but still updates
    the cache afterward.
    """
    if not force_refresh:
        cached = cache.get_cached_player_page(url)
        if cached:
            html, fetched_at = cached
            if not cache.is_stale(fetched_at, cache.PLAYER_PAGE_TTL_HOURS):
                return url, html
            if requested_season:
                available = list_available_seasons(html)
                if available and requested_season in available and requested_season != available[0]:
                    return url, html  # stale for "current", but this season is historical -- still valid

    url, html = _uc_fetch(url)
    cache.set_cached_player_page(url, html)
    return url, html


def _season_rows(soup: BeautifulSoup, table_id: str):
    """Return every real-season tbody row (in table order, oldest first) for the given FBref
    table, or [] if the table isn't on this page (e.g. Goalkeeping, for an outfield player)."""
    table = soup.find("table", id=table_id)
    if table is None:
        return []
    return [
        tr
        for tr in table.find("tbody").find_all("tr")
        if (cell := tr.find(attrs={"data-stat": "year_id"}))
        and re.match(r"^\d{4}(-\d{4})?$", cell.text.strip())
    ]


def _season_row(soup: BeautifulSoup, table_id: str, season: str | None = None):
    """Return the row for a specific season (year_id), or the most recent one if season is
    None. None if the table isn't on the page or the requested season isn't in it."""
    rows = _season_rows(soup, table_id)
    if not rows:
        return None
    if season is None:
        return rows[-1]
    return next((r for r in rows if r.find(attrs={"data-stat": "year_id"}).text.strip() == season), None)


def list_available_seasons(html: str) -> list[str]:
    """All seasons present in the Standard Stats table, most recent first."""
    soup = BeautifulSoup(html, "lxml")
    rows = _season_rows(soup, "stats_standard_dom_lg")
    return [r.find(attrs={"data-stat": "year_id"}).text.strip() for r in reversed(rows)]


def _row_stats(row, fields: dict) -> dict:
    """fields maps output key -> FBref data-stat name."""
    def stat(name):
        cell = row.find(attrs={"data-stat": name})
        return cell.text.strip() if cell else ""

    return {key: stat(data_stat) for key, data_stat in fields.items()}


def extract_latest_season(html: str, season: str | None = None) -> dict:
    """Pull a season row (most recent if season is None) from the Standard Stats table."""
    soup = BeautifulSoup(html, "lxml")
    row = _season_row(soup, "stats_standard_dom_lg", season)
    if row is None:
        raise RuntimeError(
            "Could not find season rows in the standard stats table"
            if season is None
            else f"Season '{season}' not found in the standard stats table"
        )

    return _row_stats(row, {
        "season": "year_id",
        "age": "age",
        "squad": "team",
        "competition": "comp_level",
        "matches_played": "games",
        "starts": "games_starts",
        "minutes": "minutes",
        "goals": "goals",
        "assists": "assists",
        "goals_plus_assists": "goals_assists",
        "non_penalty_goals": "goals_pens",
        "yellow_cards": "cards_yellow",
        "red_cards": "cards_red",
    })


def extract_misc_stats(html: str, season: str | None = None) -> dict | None:
    """Pull defensive/discipline numbers (tackles, interceptions, fouls, etc.) from the Misc
    table -- applies to any position, most relevant for outfield defensive contribution."""
    soup = BeautifulSoup(html, "lxml")
    row = _season_row(soup, "stats_misc_dom_lg", season)
    if row is None:
        return None

    return _row_stats(row, {
        "fouls_committed": "fouls",
        "fouls_drawn": "fouled",
        "offsides": "offsides",
        "crosses": "crosses",
        "interceptions": "interceptions",
        "tackles_won": "tackles_won",
        "penalties_won": "pens_won",
        "penalties_conceded": "pens_conceded",
        "own_goals": "own_goals",
    })


def extract_keeper_stats(html: str, season: str | None = None) -> dict | None:
    """Pull goalkeeping numbers from the Goalkeeping table -- only present on the page for
    players who are actually goalkeepers."""
    soup = BeautifulSoup(html, "lxml")
    row = _season_row(soup, "stats_keeper_dom_lg", season)
    if row is None:
        return None

    return _row_stats(row, {
        "gk_matches_played": "gk_games",
        "gk_starts": "gk_games_starts",
        "gk_minutes": "gk_minutes",
        "goals_against": "gk_goals_against",
        "shots_on_target_against": "gk_shots_on_target_against",
        "saves": "gk_saves",
        "save_pct": "gk_save_pct",
        "wins": "gk_wins",
        "draws": "gk_ties",
        "losses": "gk_losses",
        "clean_sheets": "gk_clean_sheets",
        "clean_sheet_pct": "gk_clean_sheets_pct",
        "penalties_faced": "gk_pens_att",
        "penalties_allowed": "gk_pens_allowed",
        "penalties_saved": "gk_pens_saved",
    })


def extract_player_bio(html: str) -> dict:
    """Pull background info (name, physical profile, birth, nationality, club, contract) from
    the #meta block at the top of an FBref player page."""
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("div", id="meta")
    if meta is None:
        raise RuntimeError("Could not find the player bio block on the FBref page")

    text = meta.get_text("\n", strip=True)

    # The full-name <p> is the one whose entire content is just a <strong> tag, with no
    # "Label:" prefix (unlike Position/Footed/Club/etc which all follow a labeled <p>).
    full_name = ""
    for p in meta.find_all("p"):
        strong = p.find("strong")
        if strong and strong.get_text(strip=True) == p.get_text(strip=True):
            full_name = strong.get_text(strip=True)
            break

    position_match = re.search(r"Position:\s*([^▪\n]+)", text)
    foot_match = re.search(r"Footed:\s*(\w+)", text)

    height_weight = ""
    hw_p = next((p for p in meta.find_all("p") if re.search(r"\d+cm", p.get_text())), None)
    if hw_p:
        hw_match = re.search(r"(\d+cm)\s*,?\s*(\d+kg)", hw_p.get_text(" ", strip=True))
        if hw_match:
            height_weight = f"{hw_match.group(1)}, {hw_match.group(2)}"

    birth_span = meta.find(id="necro-birth")
    birth_date = birth_span["data-birth"] if birth_span and birth_span.has_attr("data-birth") else ""

    birthplace = ""
    if birth_span:
        born_p = birth_span.find_parent("p")
        if born_p:
            place_span = next(
                (s for s in born_p.find_all("span") if s.get_text(strip=True).startswith("in ")),
                None,
            )
            if place_span:
                birthplace = place_span.get_text(strip=True).removeprefix("in ").strip()

    club_match = re.search(r"Club:\s*([^\n]+)", text)
    nat_team_match = re.search(r"National Team:\s*([^\n]+)", text)
    contract_match = re.search(r"Expires\s+([A-Za-z]+\s+\d{4})", text)

    return {
        "full_name": full_name,
        "position": position_match.group(1).strip() if position_match else "",
        "footed": foot_match.group(1).strip() if foot_match else "",
        "height_weight": height_weight,
        "birth_date": birth_date,
        "birthplace": birthplace,
        "national_team": nat_team_match.group(1).strip() if nat_team_match else "",
        "club": club_match.group(1).strip() if club_match else "",
        "contract_expires": contract_match.group(1) if contract_match else "",
    }


def summarize_with_llm(player_name: str, stats: dict) -> str:
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    stats_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in stats.items())
    prompt = (
        f"You are a football scouting assistant. Using ONLY the stats listed below, write a "
        f"short paragraph (3-5 sentences) summarizing {player_name}'s most recent season. Cite "
        f"specific numbers from the stats. Do not invent or infer any stat that is not listed. "
        f"Do not speculate about transfer value, potential, or future performance.\n\n"
        f"Player: {player_name}\nStats:\n{stats_lines}"
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def main():
    parser = argparse.ArgumentParser(
        description="ScoutLite MVP slice: player name -> FBref stats -> LLM paragraph"
    )
    parser.add_argument("player", help="Player name, e.g. 'Erling Haaland'")
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("DEEPSEEK_API_KEY is not set. Add it to .env in this project folder.")

    print(f"Fetching FBref data for '{args.player}'...")
    url, html = fetch_player_page_html(args.player)
    print(f"Resolved to: {url}")

    stats = extract_latest_season(html)
    print(f"Latest season found: {stats['season']} ({stats['squad']}, {stats['competition']})")

    print("Calling DeepSeek-V3 for the summary paragraph...")
    paragraph = summarize_with_llm(args.player, stats)

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", args.player.lower()).strip("_")
    out_path = output_dir / f"{slug}.txt"
    out_path.write_text(paragraph + "\n")

    print("\n--- Summary ---")
    print(paragraph)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
