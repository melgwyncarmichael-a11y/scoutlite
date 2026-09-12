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
  - 3. What people say -- news headlines (data, each linked to its actual article) + a short
    LLM-synthesized read
  - 4. Signals & fit read -- LLM fit-signal paragraph + scout's role notes + philosophy chosen
  - 5. Sources -- every link a scout needs to check a claim themselves: the FBref profile the
    stats came from, the Understat profile the xG/xA came from, and NewsAPI's publisher/date
    per headline (also inline above) -- this is a research brief, not a black box

Deliberately named "research brief," never "report" or "verdict" -- ScoutLite is a data/
research layer for a scout, not a conclusion reached on their behalf.
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def _add_hyperlink(paragraph, url: str, text: str):
    """python-docx has no built-in hyperlink support -- this is the standard low-level recipe:
    register the URL as an external relationship on the paragraph's part, then hand-build the
    <w:hyperlink> run pointing at it, styled like a normal link (blue, underlined)."""
    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1155CC")
    run_props.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_props.append(underline)
    run.append(run_props)

    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    return hyperlink


def _add_dict_table(doc: Document, data: dict, skip: tuple[str, ...] = ()):
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for key, value in data.items():
        if value in (None, "") or key in skip:
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
    player_url: str | None = None,
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
        if xg.get("understat_url"):
            link_p = doc.add_paragraph()
            link_p.add_run("Source: ")
            _add_hyperlink(link_p, xg["understat_url"], xg["understat_url"])
        _add_dict_table(doc, xg, skip=("understat_url",))
    else:
        doc.add_paragraph("Advanced stats (xG/xA): not available -- Understat doesn't cover this player's league, or no name match was found.")

    # --- 3. What people say --------------------------------------------------------------
    doc.add_heading("3. What People Say", level=1)
    doc.add_paragraph(news_synthesis or "No recent news synthesis available.")
    if articles:
        doc.add_heading("Recent headlines (last 28 days)", level=2)
        for a in articles[:8]:
            bullet = doc.add_paragraph(style="List Bullet")
            title = a.get("title", "")
            if a.get("url"):
                _add_hyperlink(bullet, a["url"], title)
            else:
                bullet.add_run(title)
            source = a.get("source", {}).get("name", "")
            published = (a.get("publishedAt") or "")[:10]
            attribution = " · ".join(v for v in (source, published) if v)
            if attribution:
                bullet.add_run(f"  ({attribution})").italic = True

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

    # --- 5. Sources -------------------------------------------------------------------------
    # Every link a scout would need to check a claim themselves -- this is a research brief,
    # not a black box. Headline sources are already linked inline above; this section is the
    # profile pages the stats tables came from.
    doc.add_heading("5. Sources", level=1)
    if player_url:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run("FBref profile (season stats, bio, defensive/goalkeeping stats): ")
        _add_hyperlink(p, player_url, player_url)
    if xg and xg.get("understat_url"):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run("Understat profile (xG/xA): ")
        _add_hyperlink(p, xg["understat_url"], xg["understat_url"])
    if articles:
        doc.add_paragraph(
            "News headlines are linked individually in \"What People Say\" above, each with "
            "its publisher and date.", style="List Bullet"
        )
    if not player_url and not (xg and xg.get("understat_url")) and not articles:
        doc.add_paragraph("No sourced links available for this brief.")

    doc.save(output_path)
    return output_path
