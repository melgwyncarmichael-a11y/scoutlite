# Fit Signal — Reference

A quick-lookup reference for what ScoutLite's Fit signal actually measures and what each label
means. For the full mechanism, see `scoring.compute_fit_signal()`; for how these thresholds
were chosen (and what's still unvalidated), see `EVAL_REPORT.md` and `eval/TRACK_C2_REPORT.md`.

> **Don't hand this to a blind labeler before they judge a Track C3 case.** Knowing where the
> numeric cutoffs sit can shape a "blind" judgment in ways that defeat the point of testing it
> independently. This doc is for maintainers/reviewers, and for annotating your own `your_guess`
> column after you already know how the tool works.

## What Fit actually measures

Fit is **not** "is this a good player" (that's Quality's job) and **not** "does this player
play for this club." It measures **profile-shape similarity**: how closely a player's own
percentile profile (per-90 stats, ranked against real peers in their league/season/position)
resembles the *average* percentile profile of a real reference club's current squad in the same
position group, for a chosen in-possession / out-of-possession philosophy.

It's fully deterministic — pure percentile math, no LLM involved in the number. The LLM only
writes a paragraph explaining an already-computed label; it never decides the label itself.

The comparison is one number, `avg_abs_diff`: the average absolute percentile-point gap between
the player and the reference club's squad average, across whichever metrics both populations
share for that position group.

## The three tiers

| Label | `avg_abs_diff` | What it means |
|---|---|---|
| **Hand-in-Glove Fit** | < 20 | The player's percentile profile sits close to the reference club's average — on the shared metrics, he ranks about the same as a typical player in that position at that club. |
| **Somewhat Fits** | 20 – 34.9 | A moderate gap. Some metrics line up well, others diverge noticeably — a mixed profile, not a clean match either way. |
| **Completely Different** | ≥ 35 | A large, consistent gap across every shared metric. Statistically, this player doesn't resemble what that club's players in this position typically produce. |

Exact cutoffs live in `scoring.FIT_LABELS`.

## Calibration status — the two cutoffs are not equally trustworthy

- **20 (Hand-in-Glove cutoff) has real tuning evidence behind it.** Originally 15; Track C2
  (`eval/TRACK_C2_REPORT.md`) found two genuine standout players (Haaland vs. Man City, Kimmich
  vs. Bayern) landed just past the old cutoff at 16.0–17.1, even though comparing a standout
  against his own squad's average — which includes weaker depth — will always show some real
  gap. Raised to 20 on 2026-09-18; re-tested match rate went from 2/9 to 4/9 on the same cases.
- **35 (Completely Different cutoff) has never been validated against anything.** It's still
  the original first-pass guess from when the mechanism was built. No eval track has produced
  evidence either way about whether it's set correctly.
- **Track C3 (in progress, see `NOTES.md`)** is testing both cutoffs against genuinely blind
  human judgment — a labeler decides each case's tier from real football knowledge, before ever
  seeing the tool's output — rather than the self-graded "expected by construction" cases Track
  C2 used. `eval/track_c3_labels.csv` is the live labeling sheet; results land in
  `eval/score_track_c3.py`'s output once labels are filled in.

## A structural caveat: not all position groups are equally reliable

Defense (and goalkeeper) compare on only **one** shared metric (`defensive_actions_per90` for
defense, `save_pct` for goalkeeper), where attack has 4 and midfield has 2–3. Averaging several
metrics smooths out noise; a single metric doesn't. Track C2 found defense-group cases swing far
more widely (9.2 to 41.9 in one 9-case sample) than attack/midfield — this is a known,
disclosed structural limitation, not something the 20/35 cutoffs can fix on their own. A second
defensive metric would fix it at the source, but neither FBref (via `soccerdata`) nor Understat
currently exposes one (checked directly, see `TESTS.md`'s "Not yet built").

## The 6 reference clubs

Fit only exists for a chosen combination of in-possession and out-of-possession philosophy —
"Not specified" skips Fit entirely. Each of the 6 combinations maps to one real club, whose
*current* squad (same league, same season) is the actual comparison population:

| In possession | Out of possession | Reference club | League |
|---|---|---|---|
| Vertical, fast transitions | High line, counter-press | Borussia Dortmund | Bundesliga |
| Vertical, fast transitions | Mid block, hybrid | Real Madrid | La Liga |
| Vertical, fast transitions | Low block, counter | Atlético Madrid | La Liga |
| Slow, methodical possession | High line, counter-press | Manchester City | Premier League |
| Slow, methodical possession | Mid block, hybrid | Bayern Munich | Bundesliga |
| Slow, methodical possession | Low block, counter | Brighton | Premier League |

Source of truth: `scoring.REFERENCE_CLUBS`. If this table and the code ever disagree, the code
is right — this doc is a convenience snapshot, not the definition.

## What Fit still can't see

No ScoutLite data source (FBref, Understat) measures pace, sprint speed, or pressing intensity
— all central to what "philosophy fit" actually means tactically. Even a close statistical match
above doesn't confirm tactical fit on those dimensions. Every brief with a Fit result discloses
this explicitly (`docx_report.FIT_SCOPE_CAVEAT`).
