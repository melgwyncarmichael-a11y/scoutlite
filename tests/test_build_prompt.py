"""build_prompt assembly + parse_synthesis marker splitting -- both pure, no API call."""
import scoutlite_combined as sc

STATS = {"season": "2023-2024", "squad": "Manchester City", "goals": "27", "assists": "5",
         "minutes": "2,552"}
XG = {"xG": 28.8, "xA": 5.51, "key_passes": 25}
ARTICLES = [{"title": "Haaland closing in on scoring record"},
            {"title": "City rotate ahead of midweek"}]


def test_prompt_has_both_section_markers():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES)
    assert sc.NEWS_MARKER in p
    assert sc.FIT_MARKER in p
    assert "Erling Haaland" in p
    assert "27" in p and "28.8" in p


def test_prompt_without_xg_says_not_available():
    p = sc.build_prompt("Erling Haaland", STATS, None, ARTICLES)
    assert "not available" in p
    assert "Understat" in p


def test_prompt_without_articles_says_none_found():
    p = sc.build_prompt("Erling Haaland", STATS, XG, [])
    assert "none found" in p


def test_prompt_with_philosophy_demands_fit_score_line():
    phil = {"in_possession": "possession", "out_of_possession": "high_line"}
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES, philosophy=phil)
    assert 'Fit: X/5' in p
    assert "possession" in p and "high_line" in p


def test_prompt_without_philosophy_demands_not_assessed_line():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES)
    assert "Fit: not assessed" in p


def test_prompt_includes_scout_notes_capped():
    long_note = "x" * 500
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES, scout_notes=long_note)
    assert "role notes" in p
    assert "x" * sc.ROLE_NOTES_MAX_CHARS in p
    assert "x" * (sc.ROLE_NOTES_MAX_CHARS + 1) not in p


def test_prompt_blank_scout_notes_omitted():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES, scout_notes="   ")
    # the scout-notes DATA section (not the generic instruction mention) must be absent
    assert "capped free text from a human scout" not in p


def test_prompt_with_prior_findings_adds_rewrite_block():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES,
                        prior_findings=["invented a transfer fee", "cited xG that was not provided"])
    assert "PREVIOUS DRAFT" in p
    assert "invented a transfer fee" in p


def test_prompt_no_prior_findings_no_rewrite_block():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES)
    assert "PREVIOUS DRAFT" not in p


# ---- parse_synthesis ----

def test_parse_synthesis_splits_on_markers():
    raw = (f"{sc.NEWS_MARKER}\nNo relevant news this window.\n\n"
           f"{sc.FIT_MARKER}\nFit: 4/5\nStrong final-third output against the pressing demand.")
    out = sc.parse_synthesis(raw)
    assert out["news_synthesis"] == "No relevant news this window."
    assert out["fit_score"] == 4
    assert out["fit_read"].startswith("Strong final-third")


def test_parse_synthesis_not_assessed():
    raw = (f"{sc.NEWS_MARKER}\nQuiet week.\n\n"
           f"{sc.FIT_MARKER}\nFit: not assessed\nScout notes only, no philosophy given.")
    out = sc.parse_synthesis(raw)
    assert out["fit_score"] is None
    assert out["fit_read"].startswith("Scout notes only")


def test_parse_synthesis_missing_markers_keeps_whole_text():
    out = sc.parse_synthesis("The model ignored the format entirely.")
    assert out["news_synthesis"] == "The model ignored the format entirely."
    assert out["fit_read"] == ""
    assert out["fit_score"] is None
