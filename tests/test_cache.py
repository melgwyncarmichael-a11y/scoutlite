"""Cache TTL logic + roundtrips. Uses a temp DB file, no network."""
import time

import pytest

import cache


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the cache at a throwaway DB for each test."""
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test_cache.db")
    monkeypatch.setattr(cache, "_conn", None)
    yield
    if cache._conn:
        cache._conn.close()
        cache._conn = None


def test_is_stale_boundary():
    assert cache.is_stale(time.time() - 10, 1) is False
    assert cache.is_stale(time.time() - 3601, 1) is True
    assert cache.is_stale(time.time(), 0.001) is False


def test_player_page_roundtrip():
    assert cache.get_cached_player_page("http://x") is None
    cache.set_cached_player_page("http://x", "<html>hi</html>")
    html, fetched_at = cache.get_cached_player_page("http://x")
    assert html == "<html>hi</html>"
    assert abs(fetched_at - time.time()) < 5


def test_player_page_replace_updates_timestamp():
    cache.set_cached_player_page("http://x", "old")
    old_ts = cache.get_cached_player_page("http://x")[1]
    time.sleep(0.02)
    cache.set_cached_player_page("http://x", "new")
    html, new_ts = cache.get_cached_player_page("http://x")
    assert html == "new"
    assert new_ts > old_ts


def test_understat_population_roundtrip():
    assert cache.get_cached_understat_population("EPL:2025") is None
    cache.set_cached_understat_population("EPL:2025", [{"a": 1}, {"b": 2}])
    players, _ = cache.get_cached_understat_population("EPL:2025")
    assert players == [{"a": 1}, {"b": 2}]


def test_search_roundtrip():
    assert cache.get_cached_search("danny ward") is None
    cache.set_cached_search("danny ward", [{"name": "Danny Ward", "url": "http://x"}])
    cands, _ = cache.get_cached_search("danny ward")
    assert cands[0]["name"] == "Danny Ward"


def test_fresh_db_initialises_schema_on_first_use():
    # temp_db reset _conn to None; first call must create tables without error
    assert cache.get_cached_player_page("http://never-seen") is None


def test_news_roundtrip():
    assert cache.get_cached_news("erling haaland::15") is None
    cache.set_cached_news("erling haaland::15", [{"title": "A headline"}])
    articles, _ = cache.get_cached_news("erling haaland::15")
    assert articles == [{"title": "A headline"}]


def test_news_replace_updates_timestamp():
    cache.set_cached_news("k", [{"title": "old"}])
    old_ts = cache.get_cached_news("k")[1]
    time.sleep(0.02)
    cache.set_cached_news("k", [{"title": "new"}])
    articles, new_ts = cache.get_cached_news("k")
    assert articles == [{"title": "new"}]
    assert new_ts > old_ts
