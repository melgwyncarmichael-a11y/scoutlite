"""build_prompt assembly + parse_synthesis marker splitting -- both pure, no API call."""
import scoutlite_combined as sc

STATS = {"season": "2023-2024", "squad": "Manchester City", "goals": "27", "assists": "5",
         "minutes": "2,552"}
XG = {"xG": 28.8, "xA": 5.51, "key_passes": 25}
ARTICLES = [{"title": "Haaland closing in on scoring record"},
            {"title": "City rotate ahead of midweek"}]
FIT_SIGNAL = {
    "reference_club": "Borussia Dortmund",
    "position_group": "attack",
    "target_components": {"goals_per90": 91.0, "xG_per90": 88.0},
    "reference_components": {"goals_per90": 70.0, "xG_per90": 65.0},
    "avg_abs_diff": 22.0,
    "label": "Somewhat Fits",
}


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


def test_prompt_with_fit_signal_gives_the_llm_the_precomputed_label_and_comparison():
    # v3: Fit is computed BEFORE the LLM call -- the prompt hands it the label and the exact
    # percentile comparison to explain, rather than asking it to invent a score.
    phil = {"in_possession": "slow, methodical possession", "out_of_possession": "high line, counter-press"}
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES, philosophy=phil, fit_signal=FIT_SIGNAL)
    assert "already been computed" in p.lower()
    assert "Somewhat Fits" in p
    assert "Borussia Dortmund" in p
    assert "91" in p  # target component value surfaced
    assert "Do NOT invent a different score" in p


def test_prompt_with_philosophy_but_no_fit_signal_says_could_not_be_computed():
    # philosophy given, but Fit unavailable (e.g. league/position not covered) -- must not ask
    # the LLM to guess a score in its place.
    phil = {"in_possession": "vertical", "out_of_possession": "high_line"}
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES, philosophy=phil, fit_signal=None)
    assert "could not be computed" in p
    assert "Do NOT invent a different score" not in p  # that instruction only applies when a signal IS given


def test_prompt_without_philosophy_says_not_assessed():
    p = sc.build_prompt("Erling Haaland", STATS, XG, ARTICLES)
    assert "not assessed" in p.lower()
    assert "Fit: X/5" not in p  # no more asking the LLM to invent a numeric line


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
    # v3: fit_read is now purely the model's prose -- no "Fit: X/5" line to strip out, since
    # the score is computed deterministically before the LLM ever runs.
    raw = (f"{sc.NEWS_MARKER}\nNo relevant news this window.\n\n"
           f"{sc.FIT_MARKER}\nStrong final-third output against the pressing demand.")
    out = sc.parse_synthesis(raw)
    assert out["news_synthesis"] == "No relevant news this window."
    assert out["fit_read"] == "Strong final-third output against the pressing demand."
    assert "fit_score" not in out


def test_parse_synthesis_missing_markers_keeps_whole_text():
    out = sc.parse_synthesis("The model ignored the format entirely.")
    assert out["news_synthesis"] == "The model ignored the format entirely."
    assert out["fit_read"] == ""
