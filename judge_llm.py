#!/usr/bin/env python3
"""
LLM half of the ScoutLite judge -- the small part. Covers only what judge_rules.py structurally
can't: whether a stat interpretation is a *fair* reading vs. an overreach, whether the news
paragraph's characterization is faithful to the headlines, subtle misframing.

One narrow, structured call. Currently DeepSeek-V3 (same as synthesis) -- when model tiering
lands (Vision doc Section 5), swap MODEL below for a cheaper/faster one; this is the natural
first place for it.
"""
import json
import os
import re

from openai import OpenAI

MODEL = "deepseek-chat"


def review(
    news_synthesis: str,
    fit_read: str,
    stats: dict,
    misc: dict | None,
    keeper: dict | None,
    xg: dict | None,
    philosophy: dict | None,
    articles: list[dict] | None = None,
) -> dict:
    """Returns {findings: [{claim, issue, severity}], has_major: bool}. Fails soft: on any
    error (parse failure, API error) returns an empty finding list rather than blocking the
    pipeline -- the rule checker is the hard gate, this is the supplement."""
    inputs = {"season stats": stats}
    if misc:
        inputs["defensive/discipline stats"] = misc
    if keeper:
        inputs["goalkeeping stats"] = keeper
    if xg:
        inputs["advanced stats (Understat)"] = xg
    if philosophy and (philosophy.get("in_possession") or philosophy.get("out_of_possession")):
        inputs["club philosophy"] = " / ".join(v for v in philosophy.values() if v)

    input_block = "\n".join(f"- {k}: {v}" for k, v in inputs.items())
    if articles:
        headlines = "\n".join(f"  - {a.get('title', '')}" for a in articles[:8])
        input_block += f"\n- recent news headlines (last 28 days):\n{headlines}"
    else:
        input_block += "\n- recent news headlines: none were found"
    prompt = (
        "You are a strict fact-checker for a football research brief. Below is the COMPLETE set "
        "of data that was available, followed by two paragraphs written from it.\n\n"
        f"AVAILABLE DATA:\n{input_block}\n\n"
        f"PARAGRAPH 1 (news read):\n{news_synthesis}\n\n"
        f"PARAGRAPH 2 (fit read):\n{fit_read}\n\n"
        "List every place where a paragraph:\n"
        "(a) draws a conclusion the stats don't fairly support (an overreach, not just a "
        "cautious reading), or\n"
        "(b) characterizes the news more strongly or differently than a neutral reading would, or\n"
        "(c) frames a fact in a misleading way even if the fact itself is present.\n\n"
        "Do NOT flag: cautious/hedged statements, explicit 'insufficient data' notes, correct "
        "arithmetic (e.g. per-game rates derived from the totals shown), a direct restatement of "
        "the data, or which source a correct number came from (mixing an Understat figure and an "
        "FBref figure in one sentence is fine as long as both numbers are right).\n\n"
        "Reserve \"major\" for a factual claim that is wrong or an event asserted that isn't in "
        "the data. Style/emphasis nitpicks are \"minor\".\n\n"
        "Respond with ONLY a JSON array, no prose. Each item: "
        '{"claim": "<the exact phrase>", "issue": "<what is wrong in one sentence>", '
        '"severity": "minor" or "major"}. "major" = a reader could be materially misled. '
        "If there is nothing to flag, respond with []."
    )

    try:
        client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()  # strip markdown fences if any
        findings = json.loads(text)
        if not isinstance(findings, list):
            return {"findings": [], "has_major": False}
        has_major = any(str(f.get("severity", "")).lower() == "major" for f in findings)
        return {"findings": findings, "has_major": has_major}
    except Exception:
        return {"findings": [], "has_major": False}
