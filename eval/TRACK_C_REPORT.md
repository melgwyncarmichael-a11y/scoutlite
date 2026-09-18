# Track C — Fit-Signal Consistency Report

**ScoutLite eval, Technical Vision doc §6, item B4.** Compiled 2026-09-16.

## Addendum, 2026-09-18 — this report is now a historical record, not current methodology

Everything below this line describes the **pre-v3** Fit mechanism, where an LLM picked a 1-5
`fit_score` by reading a prompt. That's exactly what this report's finding (21/21 runs landed
on `3/5`, see "Result 2" below) drove `EVAL_REPORT.md` and `CHANGELOG.md` to fix: as of v3,
Fit is computed deterministically (`scoring.compute_fit_signal`), the same way Quality always
has been — no LLM involved in the number at all.

That makes this report's original question moot, not unresolved: a deterministic function has
no run-to-run variance to test, by construction — running `compute_fit_signal` twice on
identical inputs is guaranteed to return the identical label and numbers every time, the same
way `2 + 2` doesn't need re-testing. There was nothing left in the *label's* path for Track C
to keep checking.

**What Track C checks now instead:** `eval/track_c_repeat.py` and `eval/score_track_c.py` were
reworked to test the one thing that *does* still touch an LLM at `temperature=0.3` — whether
the model's prose explanation of the fixed Fit label ever drifts from or misrepresents it
across identical reruns (does it still name the correct reference club every time, etc.),
which is closer in kind to a narrow Track-B-style hallucination check than to the original
consistency question. A 2-run smoke test of the reworked tooling on Erling Haaland vs.
Manchester City (possession / high line) came back label-stable both times, with the reference
club correctly named in the prose both times — as expected, since the label can no longer
vary. That same smoke test caught a real, live bug: the fit-read prose fabricated a reference
to "the scout's own role notes" on a run where no scout notes were actually given. Root cause
was an ambiguous prompt instruction ("if the scout's role notes are present, weave them in")
that let the model decide for itself whether notes existed rather than being told directly;
fixed in `build_prompt()` by gating that sentence on `has_scout_notes` computed in code, and a
new deterministic `judge_rules.py` HONESTY check now catches this specific fabrication if it
ever recurs. See `NOTES.md` (2026-09-18 entry) for the full writeup.

The 21 archived runs in `eval/track_c_samples/*.json` and the table below are kept as-is: they
are accurate records of the old mechanism's real behavior, and the reasoning in "Interpretation"
below is exactly why Fit was redesigned. Nothing below has been changed to match the new
architecture.

## What this checks (pre-v3, historical)

The Fit signal (`Fit: X/5`) is the one number in a ScoutLite brief that comes from the LLM
rather than deterministic math. B4 asks a narrow question: **given identical inputs — same
player, same season, same club philosophy, same scout notes — does re-running the pipeline
ever produce a different `fit_score`?** `temperature=0.3` on the synthesis call means the
*wording* is expected to vary run to run; the question is whether the *number* does too.

## Method

`eval/track_c_repeat.py` runs the full pipeline N times per case, holding every input fixed
and reusing the same cached FBref/Understat data across runs (`force_refresh=False`
throughout) so only the LLM call itself can introduce variance. `eval/score_track_c.py`
groups the runs by player+philosophy and reports whether `fit_score` matched across all of
them.

## Sample

7 cases, 3 runs each (21 runs total), covering every one of the 6 possible philosophy
combinations (2 in-possession × 3 out-of-possession) at least once, across attack, midfield,
and defense profiles:

| Player | Position group | Philosophy | `fit_score` (3 runs) | Stable? |
|---|---|---|---|---|
| Erling Haaland | Attack | vertical, fast transitions / high line, counter-press | 3, 3, 3 | Yes |
| Kevin De Bruyne | Attack | slow, methodical possession / mid block, hybrid | 3, 3, 3 | Yes |
| Aaron Wan-Bissaka | Defense | slow, methodical possession / low block, counter | 3, 3, 3 | Yes |
| Trent Alexander-Arnold | Defense | vertical, fast transitions / high line, counter-press | 3, 3, 3 | Yes |
| Casemiro | Midfield | vertical, fast transitions / low block, counter | 3, 3, 3 | Yes |
| Rodri | Defense* | vertical, fast transitions / mid block, hybrid | 3, 3, 3 | Yes |
| Virgil van Dijk | Defense | slow, methodical possession / high line, counter-press | 3, 3, 3 | Yes |

*Rodri classifies as Defense, not Midfield, due to a separate documented limitation
(`classify_position_group` — see Track A1's writeup); noted here because it means this case
also doubles as one more data point on that issue, not a new one.

Trent Alexander-Arnold was deliberately chosen as an on-paper mismatch: a fullback known for
attacking output rather than recovery pace, tested specifically against a high-line,
counter-pressing philosophy that punishes exactly that profile.

## Result 1 — within-case stability: confirmed

Every run in every case matched every other run in that same case. Where `temperature=0.3`
did show up was in the prose, not the number — e.g. Haaland's three runs open with "give a
mixed and largely incomplete picture," "give only a partial read," and "give only partial
purchase" respectively, citing the same underlying stats and reaching the same conclusion each
time. This is the expected, designed-for behavior.

## Result 2 — the actual finding: **21 for 21 runs landed on `fit_score: 3`**

Zero exceptions, across 7 different players, 6 different philosophy combinations, and 3
different position groups. This is not the model repeating a template — each `fit_read` cites
different real stats specific to that player (Haaland: interceptions/tackles per-90;
De Bruyne: key passes/crosses; Wan-Bissaka: interceptions/tackles in a defensive context;
Trent: crosses/key passes vs. missing pace data; Casemiro, Rodri, Van Dijk each their own
defensive-output numbers) and reaches 3 by a different reasoning path each time.

**The Trent case names the mechanism directly:**
> "There is no pace or sprint data listed, so the speed-dependent transition fit central to
> this club's philosophy cannot be assessed at all."

Every one of the 7 `fit_read`s follows the same underlying pattern: cite what stats are
available, note they speak to at most half of what the philosophy actually asks about (attack
output OR defensive-action counts are present; pace, sprint distance, and pressing-volume data
are never present in any ScoutLite source), and land on 3 as the honest "insufficient
information to judge confidently" answer. `build_prompt()` explicitly instructs exactly this
behavior — "when in doubt, score closer to 3, not a confident extreme" — so every one of these
21 outputs is the *correct* response to the instructions it was given.

## Supporting evidence: the judge is still doing real work, even though the score doesn't move

Virgil van Dijk's first run scored 80% (the pass threshold, not a clean 100%) and surfaced
genuine findings before shipping:
- a FOCUS gate (the player's name didn't appear in either paragraph on the first draft)
- a misleading reframe of a headline about a "2027 boost," which is transfer/recruitment
  context, not sporting form
- an attribution error — comments attributed to a manager ("Iraola") who does not manage the
  player's actual club in the supplied data
- an unsupported inference drawing "aerial/set-piece involvement" from shots and xG alone

None of this affected `fit_score` (still 3) or blocked the brief (passed at exactly the 80%
threshold). It's included here because it shows the judge loop is actively catching real
issues in these same captures — the Fit-score stability finding isn't happening because
nothing else is being checked, it's specifically the Fit number itself that never moves.

## Interpretation

This reads as a genuine **scope limitation of the Fit signal as currently designed**, not a
bug and not model laziness:

- ScoutLite's two stat sources (FBref counting stats, Understat xG) never include pace,
  sprint-distance, or pressing-volume data.
- Philosophy fit — vertical vs. possession, high-line vs. low-block — is fundamentally a
  question about tempo, distances covered, and pressing intensity.
- The model is instructed to, and does, refuse to guess at that dimension rather than
  fabricate confidence.
- The consequence, empirically demonstrated across every combination tried: **the Fit signal
  may be structurally unable to move off a neutral 3 for any player against any club
  philosophy**, given today's data sources — not because of a flaw in the prompt or the model,
  but because the inputs can't speak to the question being asked.

## What would actually change this

Not more reruns — the within-case and cross-case evidence is already consistent and unlikely
to be a sampling artifact at this point. The two real options:

1. **Source the missing data.** Pace/sprint/pressing metrics exist (e.g. some providers expose
   distance-covered and high-intensity-run counts), but none of ScoutLite's current sources
   carry them — this would mean a new data source, not a code fix.
2. **Be upfront about the ceiling in the product itself.** If Fit is unlikely to ever move off
   neutral given current inputs, the brief (and this project's write-up) should say so plainly,
   rather than let "Fit: 3/5" read as a considered middle judgment when it may really mean "not
   enough data exists to say anything else."

## Caveats

- 7 cases is not exhaustive — every player tried happens to have a stat profile centered on
  goals/assists/xG/xA or basic defensive counting stats; a player with an unusually extreme
  profile even within those stats (rather than pace) was not specifically sought out.
- All 7 cases pull from the same two data sources by construction (FBref + Understat) — this
  finding is about ScoutLite's current inputs specifically, not a claim about LLM-based
  scouting tools in general.
- Raw data for every run is in `eval/track_c_samples/*.json`; `eval/score_track_c.py` reproduces
  the table above directly from that data.
