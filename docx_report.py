#!/usr/bin/env python3
"""
Builds the ScoutLite player research brief as a .docx file.

Structure follows the Technical Vision doc (2026-08-22):
  - Signals block at the top (Quality X/5 + Fit X/5 = X/10, always with breakdown -- never
    shown alone). Quality is a non-AI percentile-based baseline (scoring.py); Fit is the LLM's
    numeric read. Either can come back None (unsupported league/position, or no philosophy
    given) -- shown as "not available" rather than a fabricated number.
  - 1. Who he is -- bio/background (pure data, no LLM)
  - 2. Stats & performance -- season/misc/keeper/xG tables (pure data, no LLM)
  - 3. What people say -- news headlines (data) + a short LLM-synthesized read
  - 4. Signals & fit read -- LLM fit-signal paragraph + scout's role notes + philosophy chosen

Deliberately named "research brief," never "report" or "verdict" -- ScoutLite is a data/
research layer for a scout, not a conclusion reached on their behalf.
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


def _add_dict_table(doc: Document, data: dict):
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for key, value in data.items():
        if value in (None, ""):
            continue
        row = table.add_row().cells
        row[0].text = key.replace("_", " ").title()
        row[1].text = str(value)


def build_docx(
    player_name: str,
    bio: dict,
    stats: dict,
    xg: dict | None,
    articles: list[dict],
    misc: dict | None,
    keeper: dict | None,
    news_synthesis: str,
    fit_read: str,
    scout_notes: str | None,
    philosophy: dict | None,
    output_path: Path,
    quality: dict | None = None,
    fit_score: int | None = None,
    judge: dict | None = None,
) -> Path:
    doc = Document()

    title = doc.add_heading(f"{player_name} — Player Research Brief", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    subtitle = doc.add_paragraph()
    subtitle.add_run(
        f"Season: {stats.get('season', 'unknown')}  ·  A data/research layer for a scout to "
        "weigh -- not a scouting verdict."
    ).italic = True

    # --- Confidence warning (only if the automated judge didn't clear the threshold) ---------
    if judge and judge.get("confidence_warning"):
        warn = doc.add_paragraph()
        warn.add_run(
            f"⚠ CONFIDENCE WARNING — this brief's two written paragraphs scored "
            f"{judge['source_accuracy']}% on automated claim-grounding after "
            f"{judge['iterations']} revision pass(es), below the "
            f"{judge.get('threshold', 80)}% threshold. Check the flagged points below before "
            f"relying on the written sections; the data tables and signals are unaffected."
        ).bold = True
        for finding in judge.get("findings", []):
            doc.add_paragraph(finding, style="List Bullet")

    # --- Signals block (top) -----------------------------------------------------------
    doc.add_heading("Signals", level=1)
    quality_score = quality["score"] if quality else None
    combined = f"{quality_score + fit_score}/10" if quality_score and fit_score else "—/10"
    p = doc.add_paragraph()
    p.add_run(
        f"Quality signal: {quality_score if quality_score else 'not available'}/5  ·  "
        f"Fit signal: {fit_score if fit_score else 'not available'}/5  ·  Combined: {combined}"
    ).bold = True
    doc.add_paragraph().add_run(
        "Signals for the scout to weigh, never a conclusion the tool reaches on the scout's "
        "behalf. Quality is a non-AI, percentile-based baseline (this player's per-90 stats vs. "
        "the same league/season's real players in their position group) -- not an LLM judgment. "
        "Fit is the LLM's read of stats + role notes against the club philosophy, when given."
    ).italic = True
    if quality:
        doc.add_paragraph().add_run(quality["explanation"]).italic = True
        doc.add_paragraph().add_run(
            f"Exact breakdown ({quality['avg_percentile']} percentile average): " + ", ".join(
                f"{k.replace('_', ' ')} = {v:.0f} percentile" for k, v in quality["components"].items()
            )
        ).italic = True
    elif quality_score is None:
        doc.add_paragraph().add_run(
            "Quality signal not available -- either this player's league isn't one of the 5 "
            "covered (Premier League, La Liga, Bundesliga, Serie A, Ligue 1), or there wasn't "
            "enough data for their position group this season."
        ).italic = True

    # --- 1. Who he is --------------------------------------------------------------------
    doc.add_heading("1. Who He Is", level=1)
    if bio:
        _add_dict_table(doc, bio)
    else:
        doc.add_paragraph("No background data available.")

    # --- 2. Stats & performance ------------------------------------------------------------
    doc.add_heading("2. Stats & Performance", level=1)
    doc.add_heading(f"Season stats ({stats.get('season', 'unknown')})", level=2)
    _add_dict_table(doc, stats)

    if keeper:
        doc.add_heading("Goalkeeping stats", level=2)
        _add_dict_table(doc, keeper)

    if misc:
        doc.add_heading("Defensive/discipline stats", level=2)
        _add_dict_table(doc, misc)

    if xg:
        doc.add_heading("Advanced stats (Understat: xG/xA)", level=2)
        doc.add_paragraph().add_run(
            f"⚠ Matched by name lookup (not a guaranteed-unique ID) to Understat's "
            f"\"{xg['understat_matched_name']}\" -- for compound surnames, nicknames, or "
            f"abbreviations, this can occasionally match the wrong player or miss a real one. "
            f"Verify the matched name against who you actually mean before trusting these numbers."
        ).italic = True
        _add_dict_table(doc, xg)
    else:
        doc.add_paragraph("Advanced stats (xG/xA): not available -- Understat doesn't cover this player's league, or no name match was found.")

    # --- 3. What people say --------------------------------------------------------------
    doc.add_heading("3. What People Say", level=1)
    doc.add_paragraph(news_synthesis or "No recent news synthesis available.")
    if articles:
        doc.add_heading("Recent headlines (last 28 days)", level=2)
        for a in articles[:8]:
            doc.add_paragraph(a.get("title", ""), style="List Bullet")

    # --- 4. Signals & fit read -------------------------------------------------------------
    doc.add_heading("4. Signals & Fit Read", level=1)
    if philosophy and (philosophy.get("in_possession") or philosophy.get("out_of_possession")):
        style_desc = " / ".join(v for v in philosophy.values() if v)
        doc.add_paragraph().add_run(
            f"Club philosophy assessed against: {style_desc}  ·  Fit signal: {fit_score if fit_score else 'not available'}/5"
        ).bold = True
    if scout_notes and scout_notes.strip():
        doc.add_paragraph().add_run(f"Scout's role notes: \"{scout_notes.strip()}\"").italic = True
    doc.add_paragraph(fit_read or "No fit signal available.")

    doc.save(output_path)
    return output_path
