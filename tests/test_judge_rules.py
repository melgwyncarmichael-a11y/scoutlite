"""The rule-based judge is the bulk of the judge and is fully pure -- this is the richest
test target in the project."""
import judge_rules as jr

STATS = {"season": "2023-2024", "squad": "Manchester City", "goals": "27", "assists": "5",
         "minutes": "2,552", "matches_played": "31"}
XG = {"xG": 28.8, "xA": 5.51, "key_passes": 25, "shots": 122, "understat_matched_name": "Erling Haaland"}
ARTICLES = [{"title": "Haaland closing in on Premier League scoring record"},
            {"title": "Man City rotate ahead of Champions League clash"}]
PHIL = {"in_possession": "possession-based", "out_of_possession": ""}

_UNSET = object()  # so a test can pass xg=None explicitly and mean it


def _check(news, fit, fit_score=4, stats=None, misc=None, keeper=None, xg=_UNSET, articles=None,
           notes=None, phil=None):
    return jr.check("Erling Haaland", news, fit, fit_score, stats or STATS, misc, keeper,
                    XG if xg is _UNSET else xg,
                    articles if articles is not None else ARTICLES,
                    notes, phil if phil is not None else PHIL)


def test_clean_brief_scores_high_no_findings():
    r = _check(
        'Recent headlines note Haaland is "closing in on Premier League scoring record". '
        "No injury or transfer news in this window.",
        "Fit reflects 27 goals against an xG of 28.8, plus 25 key passes -- strong final-third "
        "output. Defensive data limited.",
    )
    assert r["source_accuracy"] >= 95
    assert r["hard_fail"] is False
    assert r["findings"] == []


def test_empty_section_is_hard_fail():
    assert _check("some news text long enough to pass length", "")["hard_fail"] is True
    assert _check("", "some fit text long enough to pass length")["hard_fail"] is True


def test_philosophy_given_but_no_fit_score_is_hard_fail():
    r = _check("news text long enough", "fit read text also long enough here", fit_score=None)
    assert r["hard_fail"] is True


def test_no_philosophy_but_fit_score_produced_penalised():
    r = _check("news text long enough", "fit read text long enough here", fit_score=3,
               phil={"in_possession": "", "out_of_possession": ""})
    assert any("no philosophy given but a fit score" in f for f in r["findings"])


def test_ungrounded_number_flagged_not_hard_failed():
    r = _check("news text long enough here to pass", "The player scored 99 goals this season.")
    assert any("NUMBERS" in f for f in r["findings"])
    assert "99" in r["ungrounded_numbers"]
    assert r["hard_fail"] is False  # numbers are flagged for review, never a hard fail


def test_grounded_numbers_not_flagged():
    r = _check("news text long enough here to pass",
              "27 goals from 122 shots against an xG of 28.8 and xA of 5.51.")
    assert r["ungrounded_numbers"] == []


def test_headline_numbers_count_as_grounded():
    articles = [{"title": "Haaland scores hat-trick, now on 300 club goals"}]
    r = _check("news text long enough here", "He is closing on 300 club goals with a hat-trick.",
              articles=articles)
    assert "300" not in r["ungrounded_numbers"]


def test_invented_quote_flagged():
    r = _check('Reports say he is "set for a shock move to Real Madrid this summer" per sources.',
              "fit read long enough here to pass length check")
    assert any("HEADLINES" in f for f in r["findings"])


def test_xg_cited_when_none_available_is_flagged():
    r = _check("news text long enough here", "His xG of 12.0 shows elite creativity.", xg=None)
    assert any("HONESTY" in f and "xG" in f for f in r["findings"])


def test_missing_not_assessed_when_no_philosophy():
    r = _check("news text long enough here", "He has good numbers overall.", fit_score=None,
               phil={"in_possession": "", "out_of_possession": ""})
    assert any("not assessed" in f for f in r["findings"])


def test_scout_notes_not_attributed_is_flagged():
    r = _check("news text long enough here", "He is a lazy finisher who drops deep.",
               notes="lazy off ball, great finisher")
    assert any("scout notes were provided" in f for f in r["findings"])


def test_transfer_value_language_flagged():
    r = _check("news text long enough here", 'He is valued at £120 million on the market.')
    assert any("FORBIDDEN" in f and "transfer value" in f for f in r["findings"])


def test_future_speculation_flagged():
    r = _check("news text long enough here", "He has the potential to become the best ever.")
    assert any("future speculation" in f for f in r["findings"])


def test_verdict_language_flagged():
    r = _check("news text long enough here", "The club should sign a replacement immediately.")
    assert any("verdict language" in f for f in r["findings"])


def test_wrong_player_focus_flagged():
    r = jr.check("Kevin De Bruyne", "This is all about some other footballer entirely.",
                 "And this fit read never names the target at all, discussing tactics abstractly.",
                 3, STATS, None, None, XG, ARTICLES, None, PHIL)
    assert any("FOCUS" in f for f in r["findings"])


def test_dirty_brief_scores_near_zero():
    r = _check(
        'Reports say Haaland "set for £120 million move to Real Madrid".',
        "With 45 goals and xG of 60.0 he has the potential to become the greatest. City should "
        "sign a replacement. His xA of 12.0 shows elite creativity.",
        fit_score=5, xg=None, notes="great finisher",
        phil={"in_possession": "", "out_of_possession": ""},
    )
    assert r["source_accuracy"] < 20
    assert len(r["findings"]) >= 6
