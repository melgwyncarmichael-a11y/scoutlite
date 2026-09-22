#!/usr/bin/env python3
"""
ScoutLite staging cache -- a plain SQLite table, not a vector DB. Our data is structured/
numeric (per-90 stats, player identity), which needs exact lookups, not semantic retrieval --
a vector DB would be the wrong tool for what we're storing. See NOTES.md for the fuller
architecture discussion.

Two lanes, one cache (per the project owner's design):
  - Quick mode (default): serve from cache when present and fresh enough, else fetch live and
    populate the cache.
  - Fresh mode (opt-in): always skip the cache read and fetch live, but still write the result
    back afterward so the next Quick-mode lookup benefits too.

Freshness policy differs by what's being cached:
  - player_pages: the smart case. A cached page is served regardless of age if the season being
    asked for is provably NOT the latest one in that cached copy (historical data is immutable,
    no TTL needed). Otherwise a flat TTL applies (the season being asked for might be the
    current, still-changing one).
  - understat_populations / search_results: a flat TTL each. Simpler on purpose -- Understat's
    league-wide pull is a single cheap request (no FBref-style ban risk), and search results
    aren't tied to a specific season at all, so the historical/current distinction that matters
    for player_pages doesn't apply the same way here.
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "scoutlite_cache.db"

PLAYER_PAGE_TTL_HOURS = 24
UNDERSTAT_POPULATION_TTL_HOURS = 24
SEARCH_RESULTS_TTL_HOURS = 24 * 7  # new players get indexed by FBref far less often than stats update
# Short on purpose (2026-09-22): NewsAPI's free Developer tier caps at 100 requests/day, and
# scoutlite_compare.py multiplies calls (one per candidate per run). A 28-day lookback window
# doesn't meaningfully change minute to minute, so this protects the daily cap across repeated/
# overlapping lookups in one scouting session without serving noticeably stale headlines.
NEWS_TTL_HOURS = 4

_conn = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        # check_same_thread=False: this module-level connection is shared for the life of the
        # process, but Streamlit's ScriptRunner can execute a session's reruns on different
        # worker threads (especially under concurrent multi-tab/multi-user access) -- the
        # sqlite3 default (True) would raise "SQLite objects created in a thread can only be
        # used in that same thread" the first time that happens. Safe under WAL mode (below):
        # SQLite itself serializes access, this flag only lifts Python's same-thread check.
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")  # more graceful under concurrent CLI+UI access
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_pages (
            url TEXT PRIMARY KEY,
            html TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS understat_populations (
            cache_key TEXT PRIMARY KEY,
            json_blob TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_results (
            query_key TEXT PRIMARY KEY,
            candidates_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            cache_key TEXT PRIMARY KEY,
            articles_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    conn.commit()


def is_stale(fetched_at: float, ttl_hours: float) -> bool:
    return (time.time() - fetched_at) > ttl_hours * 3600


# --- player_pages -------------------------------------------------------------------------

def get_cached_player_page(url: str) -> tuple[str, float] | None:
    row = get_conn().execute(
        "SELECT html, fetched_at FROM player_pages WHERE url = ?", (url,)
    ).fetchone()
    return tuple(row) if row else None


def set_cached_player_page(url: str, html: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO player_pages (url, html, fetched_at) VALUES (?, ?, ?)",
        (url, html, time.time()),
    )
    conn.commit()


# --- understat_populations ------------------------------------------------------------------

def get_cached_understat_population(cache_key: str) -> tuple[list, float] | None:
    row = get_conn().execute(
        "SELECT json_blob, fetched_at FROM understat_populations WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0]), row[1]


def set_cached_understat_population(cache_key: str, players: list):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO understat_populations (cache_key, json_blob, fetched_at) VALUES (?, ?, ?)",
        (cache_key, json.dumps(players), time.time()),
    )
    conn.commit()


# --- search_results -----------------------------------------------------------------------

def get_cached_search(query_key: str) -> tuple[list, float] | None:
    row = get_conn().execute(
        "SELECT candidates_json, fetched_at FROM search_results WHERE query_key = ?", (query_key,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0]), row[1]


def set_cached_search(query_key: str, candidates: list):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO search_results (query_key, candidates_json, fetched_at) VALUES (?, ?, ?)",
        (query_key, json.dumps(candidates), time.time()),
    )
    conn.commit()


# --- news_articles --------------------------------------------------------------------------

def get_cached_news(cache_key: str) -> tuple[list, float] | None:
    row = get_conn().execute(
        "SELECT articles_json, fetched_at FROM news_articles WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0]), row[1]


def set_cached_news(cache_key: str, articles: list):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO news_articles (cache_key, articles_json, fetched_at) VALUES (?, ?, ?)",
        (cache_key, json.dumps(articles), time.time()),
    )
    conn.commit()
