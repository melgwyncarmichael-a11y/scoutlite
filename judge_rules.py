#!/usr/bin/env python3
"""
Rule-based half of the ScoutLite judge -- the bulk of it. Deterministic checks on the two
LLM-authored paragraphs (news read + fit read) against the exact structured inputs that were
fed to synthesis. Computes a source-accuracy % (the number that actually gates the revision
loop, per the Technical Vision doc's 80% threshold) plus a list of concrete findings.

The LLM half (judge_llm.py) only covers what rules structurally can't: whether a stat
interpretation is *fair*, whether the news characterization is faithful, subtle misframing.
"""
import re

# Currency / valuation / transfer-fee language -- the prompt forbids transfer-value talk.
_FORBIDDEN_VALUE = re.compile(
    r"[€£$]\s?\d[\d,.]*\s?(?:million|m|bn|k)?|\bvalued at\b|\bmarket value\b|\btransfer fee\b|"
    r"\bworth\b[^.]{0,20}\b(?:million|m\b|bn\b)",
    re.IGNORECASE,
)
# Future-performance speculation -- also forbidden.
_FORBIDDEN_FUTURE = re.compile(
    r"\bhas the potential to\b|\bwill (?:become|develop|be a)\b|\bcould develop into\b|"
    r"\bfuture star\b|\bprojects? to\b|\bceiling\b",
    re.IGNORECASE,
)
# Verdict / recommendation language -- ScoutLite produces signals, never a verdict.
_FORBIDDEN_VERDICT = re.compile(
    r"\b(?:should|must)\s+sign\b|\brecommend signing\b|\bno[- ]brainer\b|\bclear upgrade\b|"
    r"\bclearly the best\b",
    re.IGNORECASE,
)

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Only straight/curly DOUBLE quotes delimit a quote -- deliberately not a bare "'"/"'". Real
# headlines routinely contain possessives/contractions inside a real quote ("Jacquet's start",
# "it's not Jeremy Jacquet"), and treating an apostrophe as a delimiter breaks in two ways at
# once: it reads a possessive as an opening quote (misreads "Ødegaard's resurgence..." as an
# invented quote spanning most of the paragraph), and it closes a real quote early at its first
# internal apostrophe -- which then strands the real closing " as a fresh false "opener" for
# whatever text follows. Both found via a real generated brief (Declan Rice's news read scored
# 20% from cascading false positives caused by exactly this; Virgil van Dijk's scored a lower
# 65% for the same reason). Excluding apostrophes from the delimiter set entirely, and allowing
# them inside the content instead, fixes both at once.
#
# Deliberately no length bound in the regex itself (just a generous upper cap against a
# malformed/unbalanced string) -- matching pairs in order, whatever their length, is what keeps
# every real quote mark correctly paired with its own partner. A minimum-length FILTER lives in
# the caller instead: a real but trivially short quote (e.g. a headline's "found" or "decision
# time") still has to consume its own quote marks here, or the marks either side of it pair up
# with each other and manufacture a fake quote out of the plain narrative in between -- the
# second real bug this same Van Dijk brief surfaced, on the very next capture after the first
# fix went in.
_QUOTED = re.compile(r'["“]([^"“”]{0,200})["”]')


def _normalize_number(tok: str) -> str:
    tok = tok.replace(",", "")
    try:
        f = float(tok)
        return str(int(f)) if f == int(f) else f"{f:.2f}"
    except ValueError:
        return tok


def _known_numbers(*dicts: dict | None) -> set[str]:
    known = set()
    for d in dicts:
        if not d:
            continue
        for v in d.values():
            for tok in _NUMBER.findall(str(v)):
                known.add(_normalize_number(tok))
                # also the rounded-to-int form, for "0.766..." vs "0.77" vs "1"
                try:
                    known.add(str(round(float(tok.replace(",", "")))))
                except ValueError:
                    pass
    return known


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def check(
    player_name: str,
    news_synthesis: str,
    fit_read: str,
    fit_score: int | None,
    stats: dict,
    misc: dict | None,
    keeper: dict | None,
    xg: dict | None,
    articles: list[dict],
    scout_notes: str | None,
    philosophy: dict | None,
) -> dict:
    """Returns {source_accuracy: 0-100, hard_fail: bool, findings: [str], ungrounded_numbers: [str]}."""
    findings: list[str] = []
    hard_fail = False
    score = 100.0

    combined = f"{news_synthesis}\n{fit_read}"
    has_philosophy = bool(philosophy and (philosophy.get("in_possession") or philosophy.get("out_of_possession")))

    # --- A. Structure (hard gates) -----------------------------------------------------------
    if not news_synthesis.strip():
        findings.append("STRUCTURE: 'What people say' section is empty.")
        hard_fail = True
    if not fit_read.strip():
        findings.append("STRUCTURE: 'Signals & fit read' section is empty.")
        hard_fail = True
    for label, para in (("news read", news_synthesis), ("fit read", fit_read)):
        n = len(para.strip())
        if 0 < n < 20:
            findings.append(f"STRUCTURE: {label} is suspiciously short ({n} chars).")
            hard_fail = True
        elif n > 2500:
            findings.append(f"STRUCTURE: {label} is very long ({n} chars) -- likely rambling.")
            score -= 10
    if has_philosophy and fit_score not in (1, 2, 3, 4, 5):
        findings.append(f"STRUCTURE: philosophy was given but fit score is {fit_score!r}, not an int 1-5.")
        hard_fail = True
    if not has_philosophy and fit_score is not None:
        findings.append(f"STRUCTURE: no philosophy given but a fit score ({fit_score}) was produced.")
        score -= 15

    # --- B. Numeric grounding --------------------------------------------------------------
    known = _known_numbers(stats, misc, keeper, xg)
    known.add(str(fit_score) if fit_score is not None else "")
    known.add("28")  # the news-lookback window ("last 28 days"), a fixed part of the prompt
    for a in articles[:8]:  # numbers in headlines the news read may legitimately cite
        for tok in _NUMBER.findall(a.get("title", "")):
            known.add(_normalize_number(tok))
    para_numbers = [_normalize_number(t) for t in _NUMBER.findall(combined)]
    ungrounded = [n for n in para_numbers if n not in known and n not in ("", "0")]
    if para_numbers:
        grounded_ratio = 1 - (len(ungrounded) / len(para_numbers))
        score *= max(grounded_ratio, 0.0)
        if ungrounded:
            findings.append(
                f"NUMBERS: {len(ungrounded)}/{len(para_numbers)} figures aren't directly in the "
                f"input data ({', '.join(sorted(set(ungrounded))[:8])}) -- may be legitimately "
                f"derived (e.g. per-game rates); review each."
            )

    # --- C. Headline grounding (news read only) -------------------------------------------
    headline_token_sets = [_tokens(a.get("title", "")) for a in articles[:8]]
    # Trivially short quotes (a single word like "found") are skipped for the actual grounding
    # check -- checked here, after pairing, so a short real quote still consumes its own marks
    # rather than leaving them to pair up with something else. See _QUOTED's comment.
    quotes = [q for q in _QUOTED.findall(news_synthesis) if 15 <= len(q) <= 120]
    ungrounded_quotes = []
    for q in quotes:
        q_tokens = _tokens(q)
        if not q_tokens:
            continue
        best_overlap = max(
            (len(q_tokens & hs) / len(q_tokens) for hs in headline_token_sets if hs), default=0.0
        )
        if best_overlap < 0.6:
            ungrounded_quotes.append(q)
    if quotes:
        grounded_q_ratio = 1 - (len(ungrounded_quotes) / len(quotes))
        score *= max(grounded_q_ratio, 0.3)  # floor -- a bad quote shouldn't zero the whole score
        if ungrounded_quotes:
            findings.append(
                f"HEADLINES: {len(ungrounded_quotes)} quoted phrase(s) in the news read don't "
                f"closely match any provided headline: {ungrounded_quotes[:3]}"
            )

    # --- D. Honesty gates ----------------------------------------------------------------
    if xg is None and re.search(r"\bxG\b|\bxA\b|expected goals|expected assists|npxG", combined, re.IGNORECASE):
        findings.append("HONESTY: brief cites xG/xA figures, but no Understat data was available for this player.")
        score -= 20
    if not has_philosophy and "not assessed" not in fit_read.lower():
        findings.append("HONESTY: no philosophy given, but the fit read doesn't say 'not assessed'.")
        score -= 10
    if scout_notes and scout_notes.strip() and "scout" not in fit_read.lower():
        findings.append(
            "HONESTY: scout notes were provided but the fit read never attributes them "
            "('the scout notes...') -- they may have been dropped or stated as fact."
        )
        score -= 10

    # --- E. Forbidden content ----------------------------------------------------------
    for label, pat in (("transfer value", _FORBIDDEN_VALUE), ("future speculation", _FORBIDDEN_FUTURE), ("verdict language", _FORBIDDEN_VERDICT)):
        m = pat.search(combined)
        if m:
            findings.append(f"FORBIDDEN: {label} detected ('{m.group(0).strip()}').")
            score -= 10

    # --- F. Player focus --------------------------------------------------------------
    name_tokens = [t for t in _tokens(player_name) if len(t) > 2]
    if name_tokens and not (name_tokens[-1] in _tokens(combined) or name_tokens[0] in _tokens(combined)):
        findings.append(
            f"FOCUS: neither '{name_tokens[0]}' nor '{name_tokens[-1]}' appears anywhere in the "
            f"two paragraphs -- the brief may be about the wrong player."
        )
        score -= 20

    score = max(0.0, min(100.0, score))
    return {
        "source_accuracy": round(score, 1),
        "hard_fail": hard_fail,
        "findings": findings,
        "ungrounded_numbers": sorted(set(ungrounded)),
    }
