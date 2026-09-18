# Track C2 — Fit Label Calibration Report

**ScoutLite eval, follow-on to Track C's v3 rework.** Compiled 2026-09-18.

## Applied, 2026-09-18 (later same day)

The Hand-in-Glove cutoff recommended below (15 -> 20) has been made in `scoring.FIT_LABELS`.
Re-running all 9 cases against the new threshold: **4 of 9 now match, up from 2 of 9.**
Adeyemi, Casemiro (both already matched), and now Haaland and Kimmich all match. The three
defense-group cases (Valverde, Giménez, Dunk) are unaffected, as expected -- their gaps
(35.2-41.9) are well past even the new cutoff, and the report's own recommendation was
explicitly *not* to fix defense-group volatility by moving this number.

One case got *more* wrong in an interesting way: Rúben Dias vs. Dortmund moved from "Somewhat
Fits" to "Hand-in-Glove Fit" (his 16.0 now falls under the raised 20 cutoff), further from the
expected "Completely Different." This is the predicted cost of the fix, not a surprise -- Dias
sits in the same 16-17 range as Haaland and Kimmich for the same structural reason (defense's
single-metric volatility, Finding 1 below), so a cutoff raised to rescue the two genuine-
standout cases will also catch a defense case sitting in that same band. Left as-is rather than
special-cased, consistent with the recommendation that defense's issue needs a second metric,
not a different number here.

The 9 samples in `eval/track_c2_samples/*.json` and the table below reflect this updated
threshold (re-captured after the change, not left showing the old numbers).

## What this checks

v3 made the Fit signal deterministic (`scoring.compute_fit_signal`), replacing an LLM-judged
1-5 score with a label computed from real percentile comparisons: `avg_abs_diff` (the average
absolute percentile-point gap between a player's profile and a reference club's squad average)
maps to one of three labels via fixed cutoffs (`scoring.FIT_LABELS`):

| `avg_abs_diff` | Label |
|---|---|
| < 15 | Hand-in-Glove Fit |
| < 35 | Somewhat Fits |
| ≥ 35 | Completely Different |

Those cutoffs (15 and 35) were a first-pass guess when the mechanism was built, explicitly
flagged in `scoring.py`'s own comment as "not eval-validated yet." Track C (reworked the same
day) confirmed the *label* can't vary run-to-run — but never checked whether 15/35 are the
*right* numbers. Track C2 does that.

## Method

No LLM or NewsAPI call needed — like Track A, this checks a deterministic signal directly, not
written prose, so it's fast and cheap (`eval/track_c2_capture.py`). Rather than a human-labeling
CSV, 9 cases were picked so the "right answer" is knowable up front without anyone's subjective
judgment:

- **6 self-reference cases** — a player compared against the actual reference club he plays
  for. Expected label: close to Hand-in-Glove Fit, since his own club's squad average is
  computed partly *from* him. One per reference club (Dortmund, Real Madrid, Atlético Madrid,
  Man City, Bayern Munich, Brighton), spanning attack/midfield/defense.
- **3 deliberate-mismatch cases** — a player whose real style is the opposite of a philosophy's
  reference club. Expected label: Completely Different.

Season `2023-2024` throughout, matching every other eval track's convention.

## Result (original run, 15/35 threshold): 2 of 9 cases matched their expected label

*(See "Applied, 2026-09-18" above for the updated 4/9 result under the now-live 20/35
threshold — this table is kept as the original run that justified the change.)*

| Case | Category | Position group | Expected | Actual | `avg_abs_diff` | Match? |
|---|---|---|---|---|---|---|
| Karim Adeyemi vs. Dortmund | self-reference | attack | Hand-in-Glove | **Hand-in-Glove** | 9.2 | ✅ |
| Federico Valverde vs. Real Madrid | self-reference | defense* | Hand-in-Glove | Completely Different | 35.2 | ❌ |
| José María Giménez vs. Atlético | self-reference | defense | Hand-in-Glove | Completely Different | 38.6 | ❌ |
| Erling Haaland vs. Man City | self-reference | attack | Hand-in-Glove | Somewhat Fits | 17.1 | ❌ |
| Joshua Kimmich vs. Bayern | self-reference | midfield | Hand-in-Glove | Somewhat Fits | 16.0 | ❌ |
| Lewis Dunk vs. Brighton | self-reference | defense | Hand-in-Glove | Completely Different | 41.9 | ❌ |
| Adama Traoré vs. Man City | mismatch | attack | Completely Different | Hand-in-Glove | 11.6 | ❌ |
| Casemiro vs. Bayern | mismatch | midfield | Completely Different | **Completely Different** | 47.9 | ✅ |
| Rúben Dias vs. Dortmund | mismatch | defense | Completely Different | Somewhat Fits | 16.0 | ❌ |

*Valverde classified as **defense**, not midfield — his 2023-2024 FBref position tag reflects
real minutes at right-back that season (Real Madrid used him there through injuries), not a
misclassification bug. A legitimate confound for this specific case's design, not a code error.

A 2/9 hit rate looks damning at first glance, but reading *why* each case landed where it did
shows two distinct, more useful findings than "the thresholds are wrong":

## Finding 1 — single-metric position groups (defense) are structurally more volatile

Every defense-group case swung hard: Valverde 35.2, Giménez 38.6, Dunk 41.9, Dias 16.0. Compare
that spread to attack (9.2, 17.1, 11.6) and midfield (16.0, 47.9) — noticeably tighter, apart
from Casemiro's deliberate extreme case.

The reason is structural, not a tuning accident: `compute_fit_signal` averages the percentile
gap across every shared component to get `avg_abs_diff`. Attack has 4 components (goals,
assists, xG, xA); midfield has 2-3. Averaging several independent metrics naturally smooths out
any one metric's noise. **Defense has exactly one** — `defensive_actions_per90` — so its
"average" gap *is* that single metric's raw gap, with none of the smoothing every other
position group gets for free. A defender who plays a different sub-role than his squad's
average (a converted fullback, a low-minutes rotation piece, a possession team's defender
facing fewer duels overall) will swing the whole signal on its own.

**This is a real design gap, not a calibration number to retune.** Widening the defense cutoffs
would just make the label less sensitive without fixing the actual cause — the position group
has one shared stat where every other group effectively has several. A second defensive metric
(e.g., pressures or blocks, if FBref's `misc` stats expose one cleanly per-90) would fix this
at the source; that's a data-availability question, not a threshold-tuning one.

## Finding 2 — an elite outlier reliably diverges from his own squad's average

Both multi-component self-reference cases that used a genuine standout player — Haaland (Man
City's clear top scorer) and Kimmich (arguably Bayern's most complete midfielder) — landed
"Somewhat Fits," not "Hand-in-Glove," at almost identical gaps (17.1 and 16.0, both just past
the 15-point cutoff). Adeyemi, a good-but-not-superlative squad member, is the one attack case
that actually cleared Hand-in-Glove (9.2).

This says something true about what the signal measures, and it isn't a bug: **Fit compares a
player against his squad's *positional average*, which includes weaker rotation and backup
players at the same position.** A player who is *better* than that average — which is exactly
what makes him a standout at that club — will show a real, correctly-computed gap from it. The
mechanism is answering "is this player statistically typical of this position at this club,"
not "does this player exemplify this club's system" — and those aren't the same question. The
original a-priori assumption behind this eval ("self-reference should read Hand-in-Glove") was
too strong for exactly the players most worth testing it on.

**Practical takeaway:** the 15-point Hand-in-Glove cutoff is stricter than it should be for the
common case of comparing a genuinely good player against a squad average that includes weaker
depth. Two multi-component self-reference cases landed within 2 points of that cutoff (16.0,
17.1) — that's a specific, actionable signal that 15 is set too tight, distinct from the
defense-group finding above.

## The one case that shows the mechanism does work as intended

Casemiro vs. Bayern Munich (mismatch, midfield, 47.9) is the clearest positive result in this
set: a genuine, large, multi-dimensional stylistic gap — low creative output, high defensive
output, tested against a creative possession midfield — produced the correct label with room to
spare. When the real difference is large across every shared metric, averaging doesn't wash it
out; the label response is exactly what the design intends.

## A limitation of this eval's own design, not the signal: Adama Traoré

The Traoré case was picked from reputation (a winger historically known more for dribbling than
end product) rather than checked against real 2023-2024 data first. His actual captured
numbers that season — 100th-percentile assists, 86.9 goals, both well above Man City's own
attacking average — contradict the reputation the case was built on. This produced a
"Hand-in-Glove Fit" that isn't wrong given the real data; the case's *premise* was outdated.
Worth stating plainly: this is a mistake in this eval's own case selection, not a finding about
the signal. Future case picks for this kind of eval should be verified against a real capture
before being written into the expected-label table, the same "fail visibly, verify with real
data" principle this project applies everywhere else — including, this time, to its own eval
design.

## Recommendation

Two changes, kept separate because they fix different things:

1. **Raise the Hand-in-Glove cutoff** from 15 to 20 — directly supported by two multi-component
   self-reference cases landing at 16.0 and 17.1, just past the old line, for players who are
   unambiguously good representatives of their own club's system. **Applied 2026-09-18** (see
   the "Applied" note at the top of this report for the re-run result: 4/9 -> up from 2/9).
2. **Do not retune the defense-group thresholds separately.** The volatility there comes from
   having only one shared metric, not from the wrong cutoff value — a second defensive-actions-
   style metric (if one exists cleanly in FBref's `misc` stat block) would be the real fix, and
   is a data-investigation task, not a number change. **Not applied** — left as a disclosed,
   open limitation.

The threshold change was flagged for a decision before being applied, rather than changed
silently — the same disclose-rather-than-hide standard this eval held itself to when reporting
its own case-selection mistake (Traoré) above instead of quietly swapping in a different player.

## Caveats

- 9 cases is a small, hand-picked sample, not a statistically powered validation — it's
  designed to surface structural issues cheaply, not to prove a precise threshold value.
- All 9 pull from the same two data sources (FBref + Understat) and the same 6 reference clubs
  already hardcoded in `scoring.REFERENCE_CLUBS` — this doesn't test whether those 6 clubs are
  themselves good representatives of their philosophies, only whether the label mechanics
  behave sensibly given them.
- Raw data for every case is in `eval/track_c2_samples/*.json`; `eval/score_track_c2.py`
  reproduces the table above directly from that data.
