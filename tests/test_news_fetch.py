"""fetch_articles()'s caching logic -- does it serve from cache when fresh, refetch when stale
or forced, and cache what it fetches. Mocks requests.get (no real network); uses a temp cache
DB (same fixture pattern as test_cache.py), no network."""
import time

import pytest

import cache
import news_fetch


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test_cache.db")
    monkeypatch.setattr(cache, "_conn", None)
    yield
    if cache._conn:
        cache._conn.close()
        cache._conn = None


class _FakeResponse:
    def __init__(self, articles):
        self._articles = articles

    def raise_for_status(self):
        pass

    def json(self):
        return {"articles": self._articles}


def test_first_call_fetches_live_and_caches(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        return _FakeResponse([{"title": "live headline"}])

    monkeypatch.setattr(news_fetch.requests, "get", fake_get)
    articles = news_fetch.fetch_articles("Erling Haaland", "key")
    assert articles == [{"title": "live headline"}]
    assert len(calls) == 1


def test_second_call_within_ttl_serves_cache_not_live(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        return _FakeResponse([{"title": "live headline"}])

    monkeypatch.setattr(news_fetch.requests, "get", fake_get)
    news_fetch.fetch_articles("Erling Haaland", "key")
    articles = news_fetch.fetch_articles("Erling Haaland", "key")  # second call, same query
    assert articles == [{"title": "live headline"}]
    assert len(calls) == 1  # not fetched twice


def test_cache_key_is_case_and_whitespace_insensitive(monkeypatch):
    calls = []
    monkeypatch.setattr(news_fetch.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([]))
    news_fetch.fetch_articles("Erling Haaland", "key")
    news_fetch.fetch_articles("  ERLING HAALAND  ", "key")
    assert len(calls) == 1


def test_force_refresh_bypasses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(news_fetch.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([]))
    news_fetch.fetch_articles("Erling Haaland", "key")
    news_fetch.fetch_articles("Erling Haaland", "key", force_refresh=True)
    assert len(calls) == 2


def test_stale_cache_is_refetched(monkeypatch):
    monkeypatch.setattr(cache, "NEWS_TTL_HOURS", 0.001)  # ~3.6s
    calls = []
    monkeypatch.setattr(news_fetch.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([]))
    news_fetch.fetch_articles("Erling Haaland", "key")
    time.sleep(0.02)
    monkeypatch.setattr(cache, "NEWS_TTL_HOURS", -1)  # force staleness deterministically
    news_fetch.fetch_articles("Erling Haaland", "key")
    assert len(calls) == 2


def test_different_limit_is_a_different_cache_entry(monkeypatch):
    calls = []
    monkeypatch.setattr(news_fetch.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([]))
    news_fetch.fetch_articles("Erling Haaland", "key", limit=5)
    news_fetch.fetch_articles("Erling Haaland", "key", limit=15)
    assert len(calls) == 2
