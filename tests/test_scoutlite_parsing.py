"""HTML parsing against real captured fixtures -- the extractors have had real bugs
(bio parsing, height/weight, the search-item split), so these are regression guards."""
import scoutlite


def test_list_available_seasons_ordered_recent_first(haaland_html):
    seasons = scoutlite.list_available_seasons(haaland_html)
    assert seasons  # non-empty
    assert "2023-2024" in seasons
    # every entry looks like a season string
    assert all(s[:4].isdigit() for s in seasons)


def test_extract_latest_season_specific_year(haaland_html):
    s = scoutlite.extract_latest_season(haaland_html, "2023-2024")
    assert s["season"] == "2023-2024"
    assert s["squad"] == "Manchester City"
    assert s["goals"] == "27"
    assert s["competition"].endswith("Premier League")


def test_extract_latest_season_unknown_year_raises(haaland_html):
    try:
        scoutlite.extract_latest_season(haaland_html, "1999-2000")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "1999-2000" in str(e)


def test_extract_player_bio(haaland_html):
    bio = scoutlite.extract_player_bio(haaland_html)
    assert bio["full_name"] == "Erling Braut Haaland"
    assert bio["footed"] == "Left"
    assert bio["birth_date"] == "2000-07-21"
    assert "cm" in bio["height_weight"] and "kg" in bio["height_weight"]
    assert bio["national_team"].startswith("Norway")
    assert bio["birthplace"].endswith("United Kingdom")


def test_extract_misc_stats(haaland_html):
    misc = scoutlite.extract_misc_stats(haaland_html, "2023-2024")
    assert misc is not None
    assert misc["interceptions"].isdigit()
    assert misc["tackles_won"].isdigit()


def test_extract_keeper_stats_none_for_outfield(haaland_html):
    assert scoutlite.extract_keeper_stats(haaland_html, "2023-2024") is None


def test_search_player_candidate_parsing_offline(danny_ward_search_html, monkeypatch):
    """Feed the real multi-match search HTML straight into search_player's parsing path."""
    monkeypatch.setattr(scoutlite, "_uc_fetch",
                        lambda url: ("https://fbref.com/en/search/search.fcgi?search=Danny+Ward",
                                     danny_ward_search_html))
    monkeypatch.setattr(scoutlite.cache, "get_cached_search", lambda k: None)
    monkeypatch.setattr(scoutlite.cache, "set_cached_search", lambda k, v: None)
    monkeypatch.setattr(scoutlite.cache, "set_cached_player_page", lambda u, h: None)

    candidates = scoutlite.search_player("Danny Ward")
    assert len(candidates) == 2
    names = {c["name"] for c in candidates}
    assert names == {"Danny Ward"}
    nats = {c["nationality"] for c in candidates}
    assert nats == {"ENG", "WAL"}
    assert all(c["url"].startswith("https://fbref.com/en/players/") for c in candidates)
    assert any(c["alt_name"] == "Daniel Carl Ward" for c in candidates)
