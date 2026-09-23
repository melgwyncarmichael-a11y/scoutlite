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
import time

import requests
import streamlit as st

from docx_report import build_docx, format_dict_for_display
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
from scoring import REFERENCE_CLUBS, compute_fit_signal, compute_quality_signal
from scoutlite_combined import ROLE_NOTES_MAX_CHARS, friendly_error_message, philosophy_from_keys, summarize_combined
from understat_xg import get_player_xg

st.set_page_config(page_title="ScoutLite", page_icon="⚽")

# One-time splash on first open (2026-09-23) -- session_state persists across reruns within a
# browser tab's session but not across a fresh tab/session, so this shows exactly once per
# session rather than flashing on every button click. The deliberate sleep is what makes it
# visible at all; without it the script runs faster than a human can perceive.
if "app_initialized" not in st.session_state:
    splash = st.empty()
    with splash.container():
        st.markdown(
            """
            <div style="display:flex; flex-direction:column; align-items:center;
                        justify-content:center; padding:5rem 0; text-align:center;">
                <div style="font-size:56px; line-height:1;">⚽</div>
                <div style="font-size:28px; font-weight:600; margin-top:0.75rem;">ScoutLite</div>
                <div style="color:#888; margin-top:0.35rem;">Loading player research tools…</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    time.sleep(1.0)
    splash.empty()
    st.session_state.app_initialized = True

st.title("ScoutLite")
st.caption("A player research brief for a scout to weigh — not a scouting verdict. Accelerates research, doesn't replace judgment.")

if not os.environ.get("DEEPSEEK_API_KEY"):
    st.error("DEEPSEEK_API_KEY is not set. Add it to .env in this project folder and restart the app.")
    st.stop()

if "player_data" not in st.session_state:
    st.session_state.player_data = None
if "search_candidates" not in st.session_state:
    st.session_state.search_candidates = None


def _show_error(e: Exception, context: str):
    """Friendly, actionable message for the user, with the raw exception tucked into an
    expander for anyone who wants the technical detail (2026-09-23). Categorization itself
    lives in scoutlite_combined.friendly_error_message() (2026-09-24) -- shared with both CLI
    entrypoints so all three surfaces give the same guidance for the same failure, rather than
    three copies that could drift out of sync."""
    if isinstance(e, RuntimeError):
        # search_player()/get_player_page() already raise clear, user-facing messages for
        # expected, actionable situations (no match found, ambiguous name) -- not a system
        # failure, so a less alarming warning (and no technical-details dump of a message
        # that's already the full, user-facing picture) reads more honestly than a red error.
        # Confirmed live (2026-09-23): searching a nonexistent name raises exactly this.
        st.warning(str(e))
        return
    st.error(friendly_error_message(e, context))
    with st.expander("Technical details"):
        st.code(f"{type(e).__name__}: {e}")


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
        _show_error(e, f"searching for \"{player_name}\"")

if st.session_state.search_candidates:
    candidates, searched_name, fresh_mode = st.session_state.search_candidates
    st.warning(
        f"{len(candidates)} players matched \"{searched_name}\" — click a row below to select "
        "the correct one before continuing, rather than guessing for you. A common name (e.g. "
        "\"Bruno Fernandes\") can match several unrelated real players -- check Clubs/Active "
        "before confirming, not just the name."
    )
    table_rows = [
        {
            "Name": c["name"],
            "Also known as": c["alt_name"] or "—",
            "Nationality": c["nationality"] or "?",
            "Active": c["years_active"] or "?",
            "Clubs": c["clubs"] or "clubs unknown",
        }
        for c in candidates
    ]
    selection = st.dataframe(
        table_rows,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="candidate_table",
    )
    selected_rows = selection.selection.rows
    if not selected_rows:
        st.caption("Click a row above to select a player.")
    else:
        chosen_idx = selected_rows[0]
        if st.button(f"Confirm: {candidates[chosen_idx]['name']}", type="primary"):
            try:
                _resolve_candidate(candidates[chosen_idx], searched_name, fresh_mode)
                st.success(f"Confirmed: {st.session_state.player_data['url']}")
            except Exception as e:
                _show_error(e, f"fetching {candidates[chosen_idx]['name']}'s page")

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

    # v3 (2026-09-17): keyed by the same short strings scoring.REFERENCE_CLUBS uses -- the CLI's
    # --in-possession/--out-of-possession choices, not the descriptive phrase. One combined
    # dropdown (2026-09-24, was two separate in/out-of-possession selectboxes) so the reference
    # club a combination compares against is visible at selection time, not just after
    # generating the whole brief -- built directly from scoring.REFERENCE_CLUBS so the club
    # names here can never drift out of sync with what compute_fit_signal() actually uses.
    _IN_POSSESSION_LABELS = {"vertical": "Vertical, fast transitions", "possession": "Slow, methodical possession"}
    _OUT_OF_POSSESSION_LABELS = {
        "high_line": "High line, counter-press", "low_block": "Low block, counter", "mid_block": "Mid block, hybrid",
    }
    PHILOSOPHY_OPTIONS = {("", ""): "Not specified — Fit not assessed"}
    for (_in_key, _out_key), _ref in REFERENCE_CLUBS.items():
        PHILOSOPHY_OPTIONS[(_in_key, _out_key)] = (
            f"{_IN_POSSESSION_LABELS[_in_key]} + {_OUT_OF_POSSESSION_LABELS[_out_key]} "
            f"— compared to {_ref['display_name']}"
        )
    philosophy_choice = st.selectbox(
        "Club philosophy to assess Fit against (optional)",
        list(PHILOSOPHY_OPTIONS),
        format_func=lambda k: PHILOSOPHY_OPTIONS[k],
        help="Fit compares this player's statistical profile against the real club shown for "
        "each combination -- e.g. possession + high line compares against Manchester City's "
        "current squad, regardless of which club this player actually plays for.",
    )
    in_possession_key, out_of_possession_key = philosophy_choice

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
                if quality:
                    st.write(f"Quality: {quality['label']}" + (
                        f" (raw: {quality['raw_label']})" if quality["raw_label"] != quality["label"] else ""
                    ))
                else:
                    st.write("Quality signal not available (league/position not covered)")

                status.update(label="Computing Fit signal (non-AI, reference-club comparison)...")
                fit_signal = compute_fit_signal(
                    bio["position"], stats["competition"], stats["season"], misc, xg,
                    quality["components"] if quality else {},
                    in_possession=in_possession_key, out_of_possession=out_of_possession_key,
                    force_refresh=fresh_mode,
                ) if quality else None
                if fit_signal:
                    st.write(f"Fit: {fit_signal['label']} vs. {fit_signal['reference_club']}")
                elif in_possession_key and out_of_possession_key:
                    st.write("Fit not available (league/position not covered by the reference-club comparison)")

                articles = []
                newsapi_key = os.environ.get("NEWSAPI_KEY")
                if newsapi_key:
                    status.update(label=f"Fetching recent news (last {LOOKBACK_DAYS} days)...")
                    try:
                        articles = fetch_articles(player_name, newsapi_key, force_refresh=fresh_mode)
                        st.write(f"Found {len(articles)} recent news articles")
                    except requests.RequestException as e:
                        st.write(f"NewsAPI request failed ({e}) — continuing without news")
                else:
                    st.write("NEWSAPI_KEY not set — skipping news")

                philosophy = philosophy_from_keys(in_possession_key, out_of_possession_key)

                status.update(label="Calling DeepSeek-V3 for the research brief (with judge loop)...")
                synthesis = summarize_combined(
                    player_name, stats, xg, articles, misc, keeper, scout_notes, philosophy,
                    fit_signal=fit_signal,
                )

                status.update(label="Building Word document...")
                buffer = io.BytesIO()
                build_docx({
                    "player_name": player_name, "player_url": data["url"], "bio": bio,
                    "stats": stats, "xg": xg, "articles": articles, "misc": misc, "keeper": keeper,
                    "scout_notes": scout_notes, "philosophy": philosophy,
                    "news_synthesis": synthesis["news_synthesis"], "fit_read": synthesis["fit_read"],
                    "quality": quality, "fit_signal": synthesis["fit_signal"], "judge": synthesis["judge"],
                }, buffer)
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

            quality_text = quality["label"] if quality else "N/A"
            if quality and quality["raw_label"] != quality["label"]:
                quality_text += f" (raw: {quality['raw_label']})"
            if fit_signal:
                fit_text = f"{fit_signal['label']} vs. {fit_signal['reference_club']}"
            elif in_possession_key and out_of_possession_key:
                # A philosophy was chosen but the signal still came back None -- genuinely
                # uncovered, not the scout's own choice not to assess it. Distinguished
                # (2026-09-24) after a real user report: a blanket "N/A" for both made "I
                # didn't pick a philosophy" indistinguishable from "can't be assessed."
                fit_text = "N/A (league/position not covered)"
            else:
                fit_text = "N/A (no club philosophy selected)"
            st.subheader("Signals")
            st.markdown(f"**Quality: {quality_text}** · **Fit: {fit_text}**")
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
                if quality["raw_avg_percentile"] != quality["avg_percentile"]:
                    st.caption(
                        f"Without the possession adjustment: {quality['raw_avg_percentile']} "
                        f"percentile average ({quality['raw_label']})."
                    )
                if quality.get("specialist_caveat"):
                    st.caption(quality["specialist_caveat"])
            if fit_signal:
                st.caption(
                    f"Compared to {fit_signal['reference_club']}'s current squad: " + ", ".join(
                        f"{k.replace('_', ' ')} = this player {v:.0f} vs. "
                        f"{fit_signal['reference_components'][k]:.0f}"
                        for k, v in fit_signal["target_components"].items()
                    )
                )
            st.caption(
                f"Automated judge: written sections scored {j['source_accuracy']}% on "
                f"claim-grounding after {j['iterations']} pass(es) — "
                + ("passed the threshold." if j["passed"] else f"below {j['threshold']}%, see warning above.")
            )

            st.subheader("Background")
            st.table(format_dict_for_display(bio))

            st.subheader(f"Season stats ({stats['season']})")
            st.table(format_dict_for_display(stats))

            if keeper:
                st.subheader("Goalkeeping stats")
                st.table(format_dict_for_display(keeper))

            if misc:
                st.subheader("Defensive/discipline stats")
                st.table(format_dict_for_display(misc))

            if xg:
                st.subheader("Advanced stats (Understat)")
                st.caption(
                    f"⚠️ Matched by name lookup (not a guaranteed-unique ID) to Understat's "
                    f"**\"{xg['understat_matched_name']}\"** — for compound surnames, nicknames, or "
                    f"abbreviations (e.g. searching \"Vinicius Jr\" won't match \"Vinícius Júnior\"), "
                    f"this can occasionally match the wrong player or miss a real one. Check the "
                    f"matched name above against who you actually mean before trusting these numbers."
                )
                st.table(format_dict_for_display(xg))

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
            _show_error(e, "generating the research brief")
