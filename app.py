#!/usr/bin/env python3
"""
ScoutLite UI shell: three-step flow.
1. Search a player -> FBref may return one unambiguous match (proceeds straight through) or
   several candidates for a common name (Danny Ward, etc.) -- shown for explicit confirmation
   rather than silently taking the first result.
2. Confirm which candidate, if there was more than one.
3. Pick a season, optionally add your own short role notes and a club philosophy to assess a
   fit signal against, then generate the combined research brief (FBref + Understat + NewsAPI
   -> one DeepSeek-V3 call). Changing the season re-parses the already-cached FBref page -- no
   second scrape/pacing hit.

Reuses scoutlite_combined.py's functions directly rather than duplicating logic.

ScoutLite produces a player research brief -- a data/research layer for a scout, not a
scouting verdict. It accelerates research, it doesn't replace judgment.
"""
import io
import os

import requests
import streamlit as st

from docx_report import build_docx
from news_fetch import LOOKBACK_DAYS, fetch_articles
from scoutlite import (
    extract_keeper_stats,
    extract_latest_season,
    extract_misc_stats,
    extract_player_bio,
    get_player_page,
    list_available_seasons,
    search_player,
)
from scoring import compute_quality_signal
from scoutlite_combined import ROLE_NOTES_MAX_CHARS, summarize_combined
from understat_xg import get_player_xg

st.set_page_config(page_title="ScoutLite", page_icon="⚽")

st.title("ScoutLite")
st.caption("A player research brief for a scout to weigh — not a scouting verdict. Accelerates research, doesn't replace judgment.")

if not os.environ.get("DEEPSEEK_API_KEY"):
    st.error("DEEPSEEK_API_KEY is not set. Add it to .env in this project folder and restart the app.")
    st.stop()

if "player_data" not in st.session_state:
    st.session_state.player_data = None
if "search_candidates" not in st.session_state:
    st.session_state.search_candidates = None


def _resolve_candidate(candidate: dict, player_name: str, fresh: bool):
    """Fetch the candidate's full page (instant if search_player() already cached it for the
    single-match case) and populate player_data."""
    with st.spinner(f"Fetching {candidate['name']}'s page..."):
        url, html = get_player_page(candidate["url"], force_refresh=fresh)
    st.session_state.player_data = {
        "player_name": player_name,
        "url": url,
        "html": html,
        "seasons": list_available_seasons(html),
    }
    st.session_state.search_candidates = None


player_name = st.text_input(
    "Player name",
    placeholder="e.g. Erling Haaland",
    help="Use the player's real, full name as it's commonly spelled online (e.g. on FBref or "
    "Wikipedia) -- nicknames, abbreviations (\"Jr\"), or a misspelling can fail to match or "
    "match the wrong player. Always check the resolved name/link after searching.",
)
fresh_mode = st.checkbox(
    "⚡ Always fetch fresh data (skip cache)",
    value=False,
    help="Off (default): reuse recently-cached data when available -- much faster, and safe "
    "since past-season data never changes. On: always pull live from FBref/Understat, useful "
    "right after a match you want reflected immediately. Either way, results are always saved "
    "to the cache for next time.",
)
search = st.button("Search player", type="primary", disabled=not player_name)

if search:
    st.session_state.player_data = None
    st.session_state.search_candidates = None
    try:
        with st.spinner(f"Searching FBref for '{player_name}' (rate-limit paced, ~7-9s)..."):
            candidates = search_player(player_name, force_refresh=fresh_mode)
        if len(candidates) == 1:
            _resolve_candidate(candidates[0], player_name, fresh_mode)
            st.success(f"Found: {st.session_state.player_data['url']}")
        else:
            st.session_state.search_candidates = (candidates, player_name, fresh_mode)
    except Exception as e:
        st.error(f"Something went wrong: {e}")

if st.session_state.search_candidates:
    candidates, searched_name, fresh_mode = st.session_state.search_candidates
    st.warning(
        f"{len(candidates)} players matched \"{searched_name}\" — confirm which one before "
        "continuing, rather than guessing for you."
    )
    labels = [
        f"{c['name']}"
        + (f" ({c['alt_name']})" if c["alt_name"] else "")
        + f" — {c['nationality'] or '?'}, active {c['years_active'] or '?'}, {c['clubs'] or 'clubs unknown'}"
        for c in candidates
    ]
    chosen_idx = st.radio("Which player did you mean?", range(len(candidates)), format_func=lambda i: labels[i])
    if st.button("Confirm selection", type="primary"):
        try:
            _resolve_candidate(candidates[chosen_idx], searched_name, fresh_mode)
            st.success(f"Confirmed: {st.session_state.player_data['url']}")
        except Exception as e:
            st.error(f"Something went wrong: {e}")

data = st.session_state.player_data
if data:
    st.divider()
    season = st.selectbox("Season", data["seasons"], index=0)

    scout_notes = st.text_area(
        f"Your role notes (optional, max {ROLE_NOTES_MAX_CHARS} chars)",
        max_chars=ROLE_NOTES_MAX_CHARS,
        placeholder='e.g. "tall, can play as a 9 or 10, fast feet, gets in behind often, lacking work rate sometimes"',
        help="Short, adjective-style notes on ROLE -- how they're actually used on the pitch, which stats alone don't show. Included as your observation, not treated as verified data.",
    )

    col1, col2 = st.columns(2)
    with col1:
        in_possession_choice = st.selectbox(
            "Club philosophy — in possession (optional)",
            ["Not specified", "Vertical, fast transitions", "Slow, methodical possession"],
        )
    with col2:
        out_of_possession_choice = st.selectbox(
            "Club philosophy — out of possession (optional)",
            ["Not specified", "High line, counter-press", "Low block, counter", "Mid block, hybrid"],
        )

    generate = st.button("Generate research brief", type="primary")

    if generate:
        try:
            player_name = data["player_name"]
            html = data["html"]

            with st.status("Parsing season stats...", expanded=True) as status:
                stats = extract_latest_season(html, season)
                bio = extract_player_bio(html)
                misc = extract_misc_stats(html, season)
                keeper = extract_keeper_stats(html, season)
                st.write(f"Season: {stats['season']} — {stats['squad']} ({stats['competition']})")

                status.update(label="Looking up Understat xG/xA...")
                xg = get_player_xg(
                    player_name, stats["competition"], stats["season"], stats["squad"], force_refresh=fresh_mode
                )
                if xg:
                    st.write(f"xG/xA found — matched to Understat's \"{xg['understat_matched_name']}\"")
                else:
                    st.write("xG/xA not available (league not covered, no name match, or Understat unreachable) — continuing without it")

                status.update(label="Computing Quality signal (non-AI, percentile-based)...")
                quality = compute_quality_signal(
                    bio["position"], stats["competition"], stats["season"], player_name, stats, misc, keeper, xg,
                    force_refresh=fresh_mode,
                )
                st.write(f"Quality: {quality['score']}/5" if quality else "Quality signal not available (league/position not covered)")

                articles = []
                newsapi_key = os.environ.get("NEWSAPI_KEY")
                if newsapi_key:
                    status.update(label=f"Fetching recent news (last {LOOKBACK_DAYS} days)...")
                    try:
                        articles = fetch_articles(player_name, newsapi_key)
                        st.write(f"Found {len(articles)} recent news articles")
                    except requests.RequestException as e:
                        st.write(f"NewsAPI request failed ({e}) — continuing without news")
                else:
                    st.write("NEWSAPI_KEY not set — skipping news")

                philosophy = {
                    "in_possession": {
                        "Vertical, fast transitions": "vertical, fast transitions",
                        "Slow, methodical possession": "slow, methodical possession",
                    }.get(in_possession_choice, ""),
                    "out_of_possession": {
                        "High line, counter-press": "high line, counter-press",
                        "Low block, counter": "low block, counter",
                        "Mid block, hybrid": "mid block, hybrid",
                    }.get(out_of_possession_choice, ""),
                }

                status.update(label="Calling DeepSeek-V3 for the research brief (with judge loop)...")
                synthesis = summarize_combined(
                    player_name, stats, xg, articles, misc, keeper, scout_notes, philosophy
                )

                status.update(label="Building Word document...")
                buffer = io.BytesIO()
                build_docx(
                    player_name, bio, stats, xg, articles, misc, keeper,
                    synthesis["news_synthesis"], synthesis["fit_read"],
                    scout_notes, philosophy, buffer,
                    quality=quality, fit_score=synthesis["fit_score"], judge=synthesis["judge"],
                    player_url=data["url"],
                )
                buffer.seek(0)
                status.update(label="Done", state="complete")

            j = synthesis["judge"]
            if j["confidence_warning"]:
                st.warning(
                    f"**Confidence warning** — the two written paragraphs scored "
                    f"{j['source_accuracy']}% on automated claim-grounding after "
                    f"{j['iterations']} revision pass(es), below the {j['threshold']}% threshold. "
                    f"The data tables and signals are unaffected; verify the written sections "
                    f"against these flags:\n\n" + "\n".join(f"- {f}" for f in j["findings"])
                )

            combined = (
                f"{quality['score'] + synthesis['fit_score']}/10"
                if quality and synthesis["fit_score"]
                else "—/10"
            )
            st.subheader("Signals")
            st.markdown(
                f"**Quality: {quality['score'] if quality else 'N/A'}/5** · "
                f"**Fit: {synthesis['fit_score'] or 'N/A'}/5** · **Combined: {combined}**"
            )
            st.caption(
                "Signals for the scout to weigh, never a conclusion the tool reaches on the "
                "scout's behalf. Quality is a non-AI, percentile-based baseline against real "
                "players in the same league/season/position group -- not an LLM judgment."
            )
            if quality:
                st.caption(quality["explanation"])
                st.caption(
                    f"Exact breakdown ({quality['avg_percentile']} percentile average): " + ", ".join(
                        f"{k.replace('_', ' ')} = {v:.0f} pct" for k, v in quality["components"].items()
                    )
                )
            st.caption(
                f"Automated judge: written sections scored {j['source_accuracy']}% on "
                f"claim-grounding after {j['iterations']} pass(es) — "
                + ("passed the threshold." if j["passed"] else f"below {j['threshold']}%, see warning above.")
            )

            st.subheader("Background")
            st.table({k: v for k, v in bio.items() if v})

            st.subheader(f"Season stats ({stats['season']})")
            st.table(stats)

            if keeper:
                st.subheader("Goalkeeping stats")
                st.table(keeper)

            if misc:
                st.subheader("Defensive/discipline stats")
                st.table(misc)

            if xg:
                st.subheader("Advanced stats (Understat)")
                st.caption(
                    f"⚠️ Matched by name lookup (not a guaranteed-unique ID) to Understat's "
                    f"**\"{xg['understat_matched_name']}\"** — for compound surnames, nicknames, or "
                    f"abbreviations (e.g. searching \"Vinicius Jr\" won't match \"Vinícius Júnior\"), "
                    f"this can occasionally match the wrong player or miss a real one. Check the "
                    f"matched name above against who you actually mean before trusting these numbers."
                )
                st.table(xg)

            if articles:
                st.subheader(f"Recent news (last {LOOKBACK_DAYS} days)")
                for a in articles[:8]:
                    st.write(f"- {a.get('title', '')}")

            st.subheader("What People Say")
            st.write(synthesis["news_synthesis"])

            st.subheader("Signals & Fit Read")
            st.write(synthesis["fit_read"])

            st.download_button(
                "Download research brief (.docx)",
                data=buffer,
                file_name=f"{player_name.lower().replace(' ', '_')}_{stats['season']}_brief.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception as e:
            st.error(f"Something went wrong: {e}")
