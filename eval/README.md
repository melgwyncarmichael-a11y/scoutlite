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

### Labeled and scored (2026-09-16) — the real result

```
Judge recall on "overstated": 50%   (1 of 2 -- caught the Fit Read overreach, missed the news-summary hype)
False-positive rate on grounded: 7%  (5 of 68 -- honest hedging the judge over-flagged as a problem)
```

Small sample (2 real `overstated` cases so far), so this is a first data point, not a verified
rate -- but it lands exactly on the hypothesis this eval was designed to test: the rule-based
judge is decent at catching factual overreach (misreading a stat with too much confidence) and
weaker at catching plain narrative hype dressed as an ordinary summary sentence, since the
latter is tonal, not something a grounding regex can see.

Two labeling-process things worth recording alongside the number itself:

**A scorer bug, found from real labeling.** The first label pass came back as full sentences
("Yes, same role, I think it's correct") rather than bare y/n -- `score_track_a.py`'s and
`score_track_b.py`'s truthy checks were exact-string matches, so every one of those was
silently read as false, and `human_label` needed the same fix (a keyword-based
`_normalize_label()`, since the five categories are free text now too, not an enum). Both
fixed; see the `judge_rules.py` section below for the parallel pattern -- this project keeps
finding real bugs by actually running the eval, not by imagining edge cases in advance.

**A genuine judge-vs-human disagreement, resolved by tracing it to the exact sentence.**
Haaland's philosophy-set brief has 3 sentences in "What People Say"; the labeler's first pick
for the one exaggeration and the judge's own LLM-supplement findings pointed at *different*
sentences entirely. Traced each finding's quoted text back to its exact source sentence to
make the disagreement concrete instead of guessing: the labeler's final call was that the
judge over-flagged two fine, honestly-hedged sentences (2 of the 5 false-positive cases) and
missed the real one. That's the eval doing exactly its job -- surfacing a specific, checkable
disagreement rather than a vague "seems fine" impression either way.

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

## Track A — Quality signal validity (labeled, scored, one bug found and fixed)

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
narrow defensive-minded pivot (Casemiro-shaped) stays classified as one.

### A1 result (2026-09-16): 67% exact match, 87% defensible

The gap between those two numbers is the actual finding. 3 of the 5 mismatches (Bruno
Fernandes, De Bruyne, Ødegaard — all `FW-MF` → Attack) were called defensible anyway: *"a
number 10 is in the middle between attack and midfield... makes sense to put a 10 as an
attacker too."* The other 2 (Declan Rice, Rodri — both `DF-MF (CM-DM)` → Defense) were called
**not** defensible, and for a sharper reason than "coarse rule": Casemiro, same defensive-
midfielder role, same `(CM-DM)` tag, gets correctly classified Midfield -- purely because
FBref didn't prefix him with `DF-`. Same job, two different buckets, by coincidence of which
code FBref lists first. That's a real inconsistency, not just a blunt simplification.

### A2 result (2026-09-16): 9 of 13 flagged surprising — three distinct causes

1. **Averaging dilutes a specialist's peak trait.** Haaland's components: `goals 100th %ile,
   xG 99th %ile` but `assists 56th, xA 53rd` -- averaged to 77, just under the 80 cutoff for
   5/5, landing at 4/5. He's literally top-of-population on the two metrics that define a pure
   striker; the composite score undersells exactly the thing he's best at.
2. **Position misclassification directly breaks the signal** for Rodri and Trent
   Alexander-Arnold -- both land in Defense (see A1), so their *entire* Quality score is one
   single `defensive_actions_per90` percentile (Rodri: 48th, Trent: 50th). Neither player's
   actual defining trait (Rodri's tempo control, Trent's creativity from right-back) is
   measured at all. Same mechanism as Wan-Bissaka's honest 5/5 in `TESTS.md`, just flipped --
   he got lucky that his one measured metric is his strength; they didn't.
3. **A real bug, not a limitation** — found and fixed. Mbappé's four components all came back
   at exactly `50.0%`, which is `percentile_rank()`'s hardcoded empty-population fallback, not
   four real percentiles. His capture's season (`2026-2027`) was only 4 games in -- essentially
   no player league-wide had crossed the 450-minute floor yet, so the reference population was
   genuinely empty, and the signal silently rendered a normal-looking `3/5` carrying zero
   actual information. **Fixed in `scoring.py`**: a component is only added to the average when
   its population is non-empty, so an entirely-empty population now correctly returns `None`
   ("not available") instead of fabricating a neutral score; a *partially* empty case (e.g. one
   of a midfielder's two source populations) now just drops that one component rather than
   losing the whole signal. Verified against the real Mbappé data once the fix landed (see
   below) and covered by two new tests in `tests/test_scoring.py` (113 tests total across the
   suite) using a mocked empty population, since the real world moved on -- more games have
   been played since, so the live population is no longer empty and the bug can't be
   reproduced live anymore.

Re-ran Mbappé's capture after the fix: **now 5/5** (`avg_percentile: 85.7`, driven by real
100th-percentile goals and xG) — which actually matches the "World's Elite" tier and
"surprising" flag from the original labeling, since a 3/5 was what looked wrong in the first
place. `track_a_quality_spotcheck.csv`'s Mbappé row was updated with the corrected numbers and
a note explaining the change; the `surprising` flag itself was deliberately left as the
labeler's own call to revisit, not silently flipped.

## Track C — Fit-signal consistency (scaffolded, one real result so far)

B4 in `TESTS.md`: same inputs, 3-5 reruns, check whether the Fit score itself flips (not just
prose wording drifting, which `temperature=0.3` makes expected).

**Workflow:**

```bash
.venv/bin/python eval/track_c_repeat.py "Erling Haaland" --season 2023-2024 \
    --in-possession vertical --out-of-possession high_line --runs 5
.venv/bin/python eval/score_track_c.py
```

`track_c_repeat.py` reuses `track_b_capture.capture()` directly (it now takes optional
`out_dir`/`out_name`, backward-compatible, Track B's own behaviour is unchanged) rather than
duplicating the pipeline — FBref/Understat data is fetched once and reused across runs (via the
normal cache, `force_refresh=False` throughout), so only the LLM call actually varies run to
run. Each run saves to `track_c_samples/<player>__<philosophy>__run<N>.json`; `score_track_c.py`
groups runs by player+philosophy and reports whether `fit_score` stayed identical across them
(pure aggregation, covered by `tests/test_score_track_c.py`).

**One real result already:** Haaland, vertical/high-line, 3 runs — `fit_score` landed on **3**
every single time, while the `fit_read` prose visibly reworded itself run to run ("give a
mixed and largely incomplete picture" / "give only a partial read" / "give only partial
purchase" — same underlying stats cited each time, same conclusion, different phrasing). That's
exactly the pattern the design predicted: `temperature=0.3` drifts the wording, not the score.
Not enough runs yet to call this "verified" (B4 asks for 3-5 reruns per case, this is one case),
but the first data point is the expected one, not a surprise.
