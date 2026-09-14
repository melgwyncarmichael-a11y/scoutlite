# ScoutLite evals

Two tracks, prioritized per the project owner's call (2026-09-12): **Track B matters most,
Track A follows, Track C is parked** for whenever there's time to test it. See `NOTES.md`
("Sources in the brief + a planned human eval of the judge loop") for how this was designed.

## Track B — does the LLM hallucinate or hype? (priority)

Calibrates the automated judge (`judge_rules.py` + `judge_llm.py`)'s 80% threshold against an
actual human reading the brief against its sources — not just "does the judge agree with
itself."

**Workflow:**

1. **Capture** a brief's full data (not just the rendered `.docx`) — stats, articles with real
   URLs, and the judge's findings — for each sample player:
   ```bash
   .venv/bin/python eval/track_b_capture.py "Erling Haaland" --season 2023-2024
   ```
   Supports `--player-url`, `--fresh`, `--scout-notes`, `--in-possession`, `--out-of-possession`
   the same as `scoutlite_combined.py`'s CLI. Each run writes one JSON file to
   `track_b_samples/`.

2. **Build the labeling sheet** from every captured JSON:
   ```bash
   .venv/bin/python eval/build_labeling_sheet.py
   ```
   Writes `track_b_labels.csv` — one row per sentence in "What People Say" + "Signals & Fit
   Read", pre-filled with that brief's `source_accuracy` and the judge's raw findings for
   context. Re-running it rebuilds the CSV from scratch, so don't hand-edit rows you want kept
   without saving a copy first.

3. **Label by hand.** Open the CSV in a spreadsheet. For every row, fill in:
   - `human_label` — one of `grounded` / `invented` / `overstated` / `verdict-language` /
     `unclear`. Click through the article/FBref/Understat links in the actual generated
     brief (now that sources are hyperlinked) to check each claim rather than guessing.
   - `caught_by_judge` — `y`/`n`, whether the judge's findings (shown in the row) already
     flagged this specific sentence.
   - `notes` — why, especially for anything `unclear`.

   One rater (you) is fine for a course-project timeline — no inter-rater math needed. If you
   want a self-consistency check, re-label one brief blind a few days later and compare.

4. **Score it:**
   ```bash
   .venv/bin/python eval/score_track_b.py
   ```
   Reports the judge's recall per issue category (of what you flagged as invented/overstated/
   verdict-language, what fraction did it already catch) and its false-positive rate on
   sentences you called grounded. The category breakdown matters more than the overall number
   — the working hypothesis (from `judge_rules.py`'s regexes) is that it's strong on
   `invented` (numeric/quote grounding is regex-catchable) and weak on `overstated` (hype is
   tonal, not factual — the forbidden-content list only catches specific phrases, not
   adjective inflation like "electric" or "generational talent"). This eval either confirms or
   kills that.

**Sample — done, 14 captures:** the 11 successful players from the 12-case test batch
(`TESTS.md`), reused rather than generating fresh players since the batch is already
deliberately diverse (elite/average/fringe, ambiguous name, uncovered league, thin-data
season, compound surname), plus 3 philosophy-set variants of players already in that set
(Haaland/vertical+high-line, De Bruyne/possession+mid-block, Wan-Bissaka/possession+low-block)
to exercise the Fit-score path the plain batch never touches. A philosophy-set capture gets its
own `<slug>__<philosophy>.json` file rather than overwriting the plain one, so both exist side
by side for the same player — `capture_id` in the CSV (not `player`) is what actually
distinguishes them.

The 11 plain captures all score 90% on one pass (the same minor "no philosophy given" wording
nit on every one — a real result, not a placeholder, see "Two real bugs" below). The 3
philosophy captures all score 100% and all landed `fit_score: 3` (neutral / insufficient
signal) with visibly hedged reasoning ("stats offer limited signal for assessing fit...") --
worth a labeler's attention specifically: is that hedging genuinely warranted by the sparse
data, or is 3 becoming a safe default the model reaches for regardless of input? That's a
judgment call no regex can make, which is exactly what Track B is for.

70 sentences across 14 captures, ready to label.

### Two real bugs the first capture run found (2026-09-12)

Running the batch immediately paid for itself: Virgil van Dijk and Declan Rice both came back
with source-accuracy in the 20-65% range on the first pass. Investigating turned up two
distinct bugs in `judge_rules.py`'s quote-extraction regex, not real hallucination:

1. A bare apostrophe (`'`) was treated as a valid opening quote character, so a possessive like
   "Ødegaard's resurgence..." got misread as an invented quote spanning most of the paragraph.
2. Trivially short real quotes (a headline's single word "found", or "decision time") fell
   under the grounding check's own 15-character floor and were skipped by the regex entirely --
   which left their quote marks unconsumed, free to pair up with each other across the
   intervening plain narrative and manufacture one long fake quote out of real prose.

Both fixed in `judge_rules.py` (only straight/curly double quotes delimit a quote now;
apostrophes are allowed as content, not as delimiters; pairing happens for every quote
regardless of length, with the length filter applied afterward, only to the grounding check).
Verified against both real briefs (Rice: 20% → 90%; Van Dijk: 65% → 90%, then a fresh
regeneration surfaced bug #2 too: 40% → 90%), then a sweep across all 11 captures found 4 more
silently affected (David Raya, Kevin De Bruyne, Trent Alexander-Arnold, Vinicius Junior — all
recovering to 90%) and re-captured them. 3 new regression tests added to
`tests/test_judge_rules.py` (94 tests total). Full writeup in `NOTES.md`.

`track_b_samples/` held these 11 at the time; the 3 philosophy-set captures described above
were added straight after, bringing the sample to the 14/70 sentences it stands at now.

## Track A — Quality signal validity (scaffolded, sample captured, not yet labeled)

Two checks, both against a shared sample in `track_a_samples/` — no LLM, no NewsAPI, just bio
+ stats + the Quality signal, which makes captures here much cheaper than Track B's.

**Workflow:**

1. **Capture** (only needed for a genuinely new player — see "Sample" below):
   ```bash
   .venv/bin/python eval/track_a_capture.py "Casemiro" --player-url <fbref-url> --season 2023-2024
   ```
   `--player-url` is usually necessary here in a way it often isn't for Track B — a short,
   common first name like "Rodri" or "Bruno Fernandes" matches dozens of FBref players, so
   search for the exact URL first (`search_player()` from a `python -c` one-liner, or just try
   the plain name and read the candidate list `track_a_capture.py` prints on ambiguity).

2. **Build both sheets** from whatever's in `track_a_samples/`:
   ```bash
   .venv/bin/python eval/build_position_survey.py       # -> track_a_position_survey.csv
   .venv/bin/python eval/build_quality_spotcheck.py     # -> track_a_quality_spotcheck.csv
   ```

3. **Label by hand:**
   - **A1 (position survey)** — completes `TESTS.md`'s B5. For each player, fill in
     `expected_group` (your own call, looking at how they're actually used) and `defensible`
     (y/n — a mismatch against your first guess can still be a defensible read, e.g. a
     genuine fullback correctly landing in Defense even though you'd call them "fairly
     attacking"; that's not the same failure mode as Rodri landing in Defense because FBref
     happens to list "DF-MF" with DF first).
   - **A2 (quality spotcheck)** — completes B3, the "Ronaldo test". Pick each player's
     `reputation_tier` (elite / starter / squad / fringe) **before** looking at
     `quality_score`, then mark `surprising` (y/n) and explain in `notes`. Wan-Bissaka's
     honest 5/5 (`TESTS.md` Finding 1 — genuinely elite by the narrow interceptions+tackles
     metric, not a bug) is the template for how a surprising score gets investigated and
     either explained or flagged, not assumed wrong.

4. **Summarize:**
   ```bash
   .venv/bin/python eval/score_track_a.py
   ```
   Reports the position survey's exact-match rate against your `expected_group` (a stricter,
   less interesting number) alongside the `defensible` rate (the one that actually matters),
   plus the quality spotcheck's count of `surprising` flags with which players they are.

**Sample — 15 players captured, 13 with a Quality score:** 11 reused directly from Track B's
already-captured data (zero extra FBref calls) plus 4 new captures chosen specifically to fill
a gap the 11 didn't cover — every single `FW-MF`/`DF-MF` player in the batch classifies as
attack/defense respectively (first-listed code wins), so there was no genuine `midfield` case
at all until these were added:

| Player | Raw FBref position | Assigned group |
|---|---|---|
| Casemiro | `MF (CM-DM)` | midfield — the one clean case |
| Rodri | `DF-MF (CM-DM)` | defense — a Ballon d'Or-level defensive midfielder, misclassified |
| Martin Ødegaard | `FW-MF (AM-CM)` | attack — same pattern as De Bruyne |
| Bruno Fernandes | `FW-MF (AM-CM-DM)` | attack — same pattern again |

That's not a coincidence worth glossing over: **every midfielder with any attacking or
defensive involvement this season gets pulled out of "midfield" entirely**, and only a fairly
narrow defensive-minded pivot (Casemiro-shaped) stays classified as one. Worth stating plainly
once A1 is labeled, rather than leaving it as 4 anecdotes.

## Track C — Fit-signal consistency (parked)

B4 in `TESTS.md`: same inputs, 3-5 reruns, check whether the Fit score itself flips (not just
prose wording drifting, which `temperature=0.3` makes expected). Parked until there's time —
picking it back up just means running `track_b_capture.py` on the same player/philosophy
several times and diffing `fit_score` + `fit_read` across the resulting JSON files; the
capture script already returns everything needed.
