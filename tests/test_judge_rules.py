"""The rule-based judge is the bulk of the judge and is fully pure -- this is the richest
test target in the project."""
import pytest

import judge_rules as jr

STATS = {"season": "2023-2024", "squad": "Manchester City", "goals": "27", "assists": "5",
         "minutes": "2,552", "matches_played": "31"}
XG = {"xG": 28.8, "xA": 5.51, "key_passes": 25, "shots": 122, "understat_matched_name": "Erling Haaland"}
ARTICLES = [{"title": "Haaland closing in on Premier League scoring record"},
            {"title": "Man City rotate ahead of Champions League clash"}]
PHIL = {"in_possession": "possession-based", "out_of_possession": ""}

_UNSET = object()  # so a test can pass xg=None explicitly and mean it
FIT_SIGNAL = {
    "reference_club": "Manchester City", "position_group": "attack",
    "target_components": {"goals_per90": 91.0}, "reference_components": {"goals_per90": 80.0},
    "avg_abs_diff": 11.0, "label": "Hand-in-Glove Fit",
}


def _check(news, fit, fit_signal=None, stats=None, misc=None, keeper=None, xg=_UNSET, articles=None,
           notes=None, phil=None):
    return jr.check("Erling Haaland", news, fit, fit_signal, stats or STATS, misc, keeper,
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


def test_fit_signal_given_but_not_mentioned_in_fit_read_is_flagged():
    # v3: Fit is computed deterministically and handed to the LLM to explain -- if the fit read
    # never mentions the reference club, it likely isn't actually grounded in that comparison.
    r = _check("news text long enough here", "This player has strong output in the final third.",
               fit_signal=FIT_SIGNAL)
    assert any("HONESTY" in f and "Manchester City" in f for f in r["findings"])


def test_fit_signal_mentioned_in_fit_read_not_flagged():
    r = _check("news text long enough here",
               "Compared to Manchester City's forwards, this player's output is very close.",
               fit_signal=FIT_SIGNAL)
    assert not any("Manchester City" in f and "HONESTY" in f for f in r["findings"])


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


def test_possessive_apostrophe_is_not_misread_as_a_quote():
    # Real bug, found via a real generated brief (Declan Rice, 2026-09-12): a bare possessive
    # apostrophe ("Ødegaard's") was misread as an opening quote, then swallowed everything up
    # to the next real quote mark as a fake "invented quote" spanning most of the paragraph --
    # collapsing the brief's score from ~90% to 20% for a reason that had nothing to do with
    # actual hallucination.
    articles = [{"title": "Martin Ødegaard's resurgence lifts Arsenal ahead of derby"}]
    r = _check(
        "A piece on Martin Ødegaard's resurgence and Arsenal's advanced talks over new deals "
        "for three players headlines this window.",
        "fit read text long enough here to pass length check",
        articles=articles,
    )
    assert not any("HEADLINES" in f for f in r["findings"])


def test_real_quote_with_internal_apostrophe_still_grounds_correctly():
    # The other half of the same bug: a real quote CONTAINING a possessive/contraction used to
    # get closed early at its own internal apostrophe, stranding the real closing " as a false
    # opener for whatever followed (found on Virgil van Dijk's brief the same day).
    articles = [{"title": "Van Dijk praises new centre-back partner Jacquet's start"}]
    r = _check(
        "A headline notes Van Dijk \"praises new centre-back partner Jacquet's start\" this week.",
        "fit read text long enough here to pass length check",
        articles=articles,
    )
    assert not any("HEADLINES" in f for f in r["findings"])


def test_trivially_short_real_quotes_dont_manufacture_a_fake_one_between_them():
    # A third variant of the same underlying bug, found on the very next Van Dijk regeneration
    # after fixing the first two: two short (<15 char) real quotes like "found" and "decision
    # time" fall under the grounding-check's own length floor, but if the regex itself also
    # ignored them, their leftover quote marks paired across the plain narrative connecting the
    # two -- manufacturing one long fake "quote" out of real prose. Pairing must happen for
    # every quote mark regardless of length; only the grounding CHECK skips trivially short ones.
    articles = [{"title": "Liverpool: decision time as club search for Van Dijk successor"},
                {"title": "Liverpool have found their long-term Van Dijk successor"}]
    r = _check(
        'A headline notes "decision time" for Van Dijk amid reporting that Liverpool have '
        '"found" a successor, according to separate coverage this week.',
        "fit read text long enough here to pass length check",
        articles=articles,
    )
    assert not any("HEADLINES" in f for f in r["findings"])


def test_invented_quote_flagged():
    r = _check('Reports say he is "set for a shock move to Real Madrid this summer" per sources.',
              "fit read long enough here to pass length check")
    assert any("HEADLINES" in f for f in r["findings"])


def test_xg_cited_when_none_available_is_flagged():
    r = _check("news text long enough here", "His xG of 12.0 shows elite creativity.", xg=None)
    assert any("HONESTY" in f and "xG" in f for f in r["findings"])


def test_missing_not_assessed_when_no_philosophy():
    r = _check("news text long enough here", "He has good numbers overall.",
               phil={"in_possession": "", "out_of_possession": ""})
    assert any("not assessed" in f for f in r["findings"])


def test_scout_notes_not_attributed_is_flagged():
    r = _check("news text long enough here", "He is a lazy finisher who drops deep.",
               notes="lazy off ball, great finisher")
    assert any("scout notes were provided" in f for f in r["findings"])


def test_fabricated_scout_notes_is_flagged():
    # No notes were actually given (notes=None) -- the model inventing "the scout's own role
    # notes" anyway is a real hallucination found via live Track C testing, 2026-09-18.
    r = _check("news text long enough here",
               "The scout's own role notes frame this as a stylistic question worth weighing.")
    assert any("no scout notes were given" in f for f in r["findings"])


def test_transfer_value_language_flagged():
    r = _check("news text long enough here", 'He is valued at £120 million on the market.')
    assert any("FORBIDDEN" in f and "transfer value" in f for f in r["findings"])


def test_future_speculation_flagged():
    r = _check("news text long enough here", "He has the potential to become the best ever.")
    assert any("future speculation" in f for f in r["findings"])


def test_verdict_language_flagged():
    r = _check("news text long enough here", "The club should sign a replacement immediately.")
    assert any("verdict language" in f for f in r["findings"])


@pytest.mark.parametrize("phrase", [
    "He was simply electric in the final third this season.",
    "This is a truly generational talent at his position.",
    "A world-class performer week in, week out.",
    "Sensational numbers from a phenomenal season.",
    "Genuinely the best in the world at what he does.",
])
def test_hype_language_flagged(phrase):
    r = _check("news text long enough here", phrase)
    assert any("hype/superlative language" in f for f in r["findings"])


def test_hype_regex_does_not_flag_a_plain_factual_sentence():
    # false-positive guard -- ordinary stat-grounded language must not trip the hype check
    r = _check(
        "news text long enough here",
        "27 goals from 122 shots against an xG of 28.8, a strong finishing return this season.",
    )
    assert not any("hype/superlative language" in f for f in r["findings"])


def test_wrong_player_focus_flagged():
    r = jr.check("Kevin De Bruyne", "This is all about some other footballer entirely.",
                 "And this fit read never names the target at all, discussing tactics abstractly.",
                 FIT_SIGNAL, STATS, None, None, XG, ARTICLES, None, PHIL)
    assert any("FOCUS" in f for f in r["findings"])


def test_dirty_brief_scores_near_zero():
    r = _check(
        'Reports say Haaland "set for £120 million move to Real Madrid".',
        "With 45 goals and xG of 60.0 he has the potential to become the greatest. City should "
        "sign a replacement. His xA of 12.0 shows elite creativity.",
        xg=None, notes="great finisher",
        phil={"in_possession": "", "out_of_possession": ""},
    )
    assert r["source_accuracy"] < 20
    assert len(r["findings"]) >= 6
