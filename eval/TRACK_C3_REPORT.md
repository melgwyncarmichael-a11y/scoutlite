# Track C3 — Fit Label Validation Against Blind Human Judgment

**ScoutLite eval, follow-on to Track C2.** Compiled 2026-09-25.

## What this checks, and why C2 wasn't enough

Track C2 checked the 15/35 (later 20/35) percentile-point cutoffs behind the Fit labels, but
its 9 "expected" labels were decided by construction — self-reference should read Hand-in-Glove,
a deliberate mismatch should read Completely Different — reasoned out by the same person who
built the tool. That's weaker evidence than it looked: nothing stopped the case selection and
the expected answer from unconsciously matching how the tool actually works.

Track C3 fixes that with a genuinely independent check: 10 new cases, each blind-labeled by a
human from real football knowledge of the player's style — **before seeing the tool's own
output at all** — then compared against what `compute_fit_signal()` actually computed.

## Method

10 cases (`eval/track_c3_capture.py`), agreed with the project owner across several rounds:
3 defenders, 3 midfielders, 3 attackers, 1 goalkeeper; 5 relatively famous / 5 relatively
unknown; rotated across all 6 `REFERENCE_CLUBS` entries; spanning 4 of the 5 top-5 leagues
(Premier League, Bundesliga, Serie A, La Liga) after an early all-Premier-League draft was
flagged and rebalanced. Season `2023-2024` throughout, matching every other eval track.

The labeling sheet (`eval/build_track_c3_labeling_sheet.py` → `eval/track_c3_labels.csv`)
showed only neutral context — player, real club, competition, position group, the reference
club's real name, and its philosophy in plain English. No tool output, no `avg_abs_diff`,
nothing that could bias an independent judgment. The blind labeler filled in one of the three
real tier names per case, informed only by their own knowledge of each player's actual style.

`score_track_c3.py` also had to normalize the filled-in text (`"Hand in glove fit"`, `"Somewhat
fits"`, `"Completely different"`) against the tool's exact label strings — the same class of
issue as Track A/B's early full-sentence label-matching bug. Fixed with a keyword-based
`normalize_label()`, tested, before scoring anything.

## Result: 4 of 10 matched the blind label

| Case | Fame | Position | Tool | Blind label | `avg_abs_diff` |
|---|---|---|---|---|---|
| Bastoni vs. Dortmund | Unknown | Defense | Somewhat Fits | Somewhat Fits | 22.9 ✅ |
| Bellingham vs. Bayern | Known | Midfield | Hand-in-Glove Fit | Hand-in-Glove Fit | 10.1 ✅ |
| Guirassy vs. Man City | Unknown | Attack | Somewhat Fits | Completely Different | 23.4 ❌ |
| Haaland vs. Dortmund | Known | Attack | Somewhat Fits | Hand-in-Glove Fit | 27.6 ❌ |
| Kean vs. Real Madrid | Unknown | Attack | Completely Different | Somewhat Fits | 50.5 ❌ |
| Kobel vs. Brighton | Unknown | Goalkeeper | Completely Different | Completely Different | 46.9 ✅ |
| Koné vs. Atlético | Unknown | Midfield | Hand-in-Glove Fit | Hand-in-Glove Fit | 13.9 ✅ |
| Rodri vs. Real Madrid | Known | Midfield | Hand-in-Glove Fit | Somewhat Fits | 12.4 ❌ |
| Upamecano vs. Atlético | Known | Defense | Hand-in-Glove Fit | Somewhat Fits | 8.9 ❌ |
| Van Dijk vs. Brighton | Known | Defense | Somewhat Fits | Completely Different | 22.3 ❌ |

**By fame tier: Unknown 3/5, Known 1/5.** A 4/10 overall rate is honestly worse than Track C2's
already-imperfect 4/9 — but unlike C2, where the miscalibration traced to one clear mechanism
(an elite player diverging from his own squad's average), this round's mismatches all trace to
a single, different, and arguably more fundamental cause once the underlying numbers are
actually read.

## Every mismatch has the same root cause: output volume vs. playing style

Pulling the raw component breakdown behind each disagreement (not just the label) shows the
same pattern in all six:

- **Kean vs. Real Madrid (biggest gap, 50.5).** Kean's own goals_per90 percentile that season
  was 6.3 against Real Madrid's attacking corps at 87.1 — an 80.8-point gap driving most of the
  average. That's a real, thin statistical season, not a reflection of Kean's actual quality or
  style as a player. The blind labeler's "Somewhat Fits" plausibly reflects broader knowledge of
  Kean as a player, not this one season's output. **The tool measures one season's statistical
  snapshot; the human measured the player.**
- **Haaland vs. Dortmund (27.6).** Goals/xG percentiles are 99–100 against Dortmund's own
  forwards at ~50–57 — a ~44–50 point gap on scoring alone, while assists are nearly identical
  (0.5 gap). This is the *exact same mechanism* Track C2 already found with Haaland vs. Man
  City: an elite scorer will always show a real gap from *any* realistic squad average,
  including his own former club's. The blind label ("Hand-in-Glove") almost certainly reflects
  genuine knowledge that Haaland's *role* (target man, in-behind runner) suits Dortmund's
  transition system — a tactical judgment the metric can't see, because it only measures
  whether his *output rate* matches the squad average, not whether his *style of play* does.
- **Guirassy vs. Man City (23.4) and Rodri vs. Real Madrid (12.4) and Upamecano vs. Atlético
  (8.9)** all show the same shape: reasonably close *counting-stat* percentiles, but a labeler
  who knows these players' actual roles (Guirassy's target-man profile vs. City's possession
  passing demands; Rodri's patient retention style vs. Madrid's vertical tempo; Bayern's
  positional pressing defense vs. Atlético's physical duel-heavy defense) sees a bigger real gap
  than the numbers show.
- **Van Dijk vs. Brighton (22.3)** is the same story on defense specifically: a single shared
  metric (`defensive_actions_per90`) can't distinguish *why* a defensive-action count lands
  where it does — proactive high-line interceptions and reactive low-block clearances can
  produce a similar raw number while representing genuinely different defensive philosophies.

**Every one of the 6 mismatches is explained by the same limitation, not six unrelated
problems.** `FIT_SCOPE_CAVEAT` already discloses that ScoutLite has no pace, sprint, or
pressing-intensity data — Track C3 is the first concrete evidence that this isn't a theoretical
gap. It's the dominant, real source of disagreement between the tool and actual football
judgment, showing up in 6 of 10 genuinely independent test cases.

## Does this mean deterministic, stats-based Fit was the wrong call? No — and it's worth saying precisely why

It would be easy to read "the tool disagrees with human judgment 6 times out of 10" as evidence
that computing Fit from stats was a mistake, and that going back to some form of judgment-based
scoring would fix it. It wouldn't, and the reason is worth stating explicitly rather than left
implicit, because it's not really a "stats vs. judgment" question — it's a **data-availability**
question that sits underneath both.

**Fit used to *be* judgment-based, and it had the identical blind spot.** Before v3, an LLM
picked the 1-5 Fit score itself, reading a text description of the club's philosophy. The
original Track C eval found this landed on exactly 3/5 in 21 of 21 test runs, across every
possible philosophy combination (`scoring.py`'s own comment above `FIT_LABELS` records this).
The LLM wasn't confused — it was being asked the same question a Track C3 labeler answers
(does this player's style suit this system), was honest that it had no pace, pressing, or
positional data to answer it with, and correctly refused to commit to a real number. That's the
*same* gap Track C3 just found, just handled differently: the old approach stayed silent about
it (a constant 3, technically honest but carrying zero information); the new one commits to a
number based on what it can actually measure (informative, but now concretely shown to miss
what the old approach was refusing to guess at in the first place).

**Swapping the computation back wouldn't add information that isn't there.** Percentile math
and an LLM reasoning over the *same* stats (goals, assists, xG, xA, tackles, interceptions) are
both blind to pace and pressing intensity for the same reason: neither was ever given that data.
Changing which "brain" processes a fixed set of numbers doesn't manufacture numbers that were
never collected.

**What actually let the Track C3 labeler see more wasn't judgment, it was knowledge scope.** The
blind labeler wasn't reasoning from the stats in the labeling sheet at all — the sheet
deliberately didn't include any. They were drawing on real, accumulated knowledge of these
specific players and clubs: Haaland's actual reputation as a penalty-box striker, Rodri's known
tempo-control style. The pre-v3 LLM never had that option — it was explicitly instructed to use
*only* the data listed in the prompt and never speculate beyond it, the same grounding rule
every other part of ScoutLite still enforces (`judge_rules.py`'s NUMBERS check, Track B's whole
purpose). An LLM *allowed* to draw on its own training knowledge of real players, the way a
human labeler draws on theirs, might close some of this gap — but that would mean deliberately
relaxing the one rule that keeps every other part of this tool from hallucinating a plausible-
sounding but ungrounded claim. That's a real, disclosed tradeoff ScoutLite has made
consistently, not an oversight: reliability and groundedness over capturing tacit knowledge
no source can verify. Track C3 shows the concrete cost of that choice for Fit specifically; it
doesn't show the choice was wrong.

**The actual fix, if pursued, is at the data layer, not the computation layer** — sourcing real
pace/pressing/positional data (already noted as unavailable from either FBref or Understat, see
`TESTS.md`), not deciding whether percentile math or an LLM should keep working with what's
already there.

## Why "known" players fared worse (1/5) than "unknown" (3/5) — a plausible, not proven, explanation

Famous players are famous partly *because* they have distinctive, well-understood playing
styles a football-literate person can reason about qualitatively (Haaland's target-man role,
Rodri's control-tempo style, Van Dijk's proactive line-stepping). For lesser-known players, a
labeler likely has less specific stylistic knowledge to draw on and may lean more on
general-quality reasoning that happens to correlate better with what a counting-stat metric
also produces. This is consistent with the case-level evidence above, not separately proven.

## A third, different kind of evidence: a fresh LLM's judgment on the same 10 cases

Asked whether a second labeler could validate that the human's readings weren't one person's
idiosyncratic take. A second genuinely *blind human* wasn't available in this round, so a
different, weaker but still informative check was run instead: a completely fresh Claude
session — no access to this conversation, the tool's output, or either report, confirmed by
zero tool calls (so no web lookups either) — judged the same 10 cases from the same neutral
labeling-sheet columns, using nothing but its own trained knowledge of these real players.
Full transcript in `eval/track_c3_llm_judgment.csv`.

**Result: the fresh LLM agreed with the human blind label on 6 of 10 cases, but with the tool
on only 3 of 10.**

| Case | Tool | Human (blind) | Fresh LLM | LLM=Tool | LLM=Human |
|---|---|---|---|---|---|
| Bastoni vs. Dortmund | Somewhat Fits | Somewhat Fits | Somewhat Fits | ✅ | ✅ |
| Bellingham vs. Bayern | Hand-in-Glove Fit | Hand-in-Glove Fit | Somewhat Fits | ❌ | ❌ |
| Guirassy vs. Man City | Somewhat Fits | Completely Different | Completely Different | ❌ | ✅ |
| Haaland vs. Dortmund | Somewhat Fits | Hand-in-Glove Fit | Hand-in-Glove Fit | ❌ | ✅ |
| Kean vs. Real Madrid | Completely Different | Somewhat Fits | Somewhat Fits | ❌ | ✅ |
| Kobel vs. Brighton | Completely Different | Completely Different | Somewhat Fits | ❌ | ❌ |
| Koné vs. Atlético | Hand-in-Glove Fit | Hand-in-Glove Fit | Hand-in-Glove Fit | ✅ | ✅ |
| Rodri vs. Real Madrid | Hand-in-Glove Fit | Somewhat Fits | Completely Different | ❌ | ❌ |
| Upamecano vs. Atlético | Hand-in-Glove Fit | Somewhat Fits | Somewhat Fits | ❌ | ✅ |
| Van Dijk vs. Brighton | Somewhat Fits | Completely Different | Somewhat Fits | ✅ | ❌ |

### What kind of evidence is each of these three, actually?

Worth being precise about this rather than treating all three as interchangeable opinions,
because they are not measuring the same thing:

- **The tool is data-and-club-fit driven.** A percentile rank of the player's own per-90 output
  against a real reference club's real current squad — reproducible, verifiable, and completely
  blind to anything not in FBref/Understat's counting stats.
- **The human blind label is subjective football expertise.** First-hand reasoning about a
  specific player's tactical role, pressing habits, and passing tempo, drawn from genuinely
  following the sport — but it is one person's read, not cross-checked against another expert,
  and carries whatever blind spots or biases that one person's knowledge has.
- **The fresh LLM's judgment is closer to aggregated sentiment than either.** It isn't
  computing anything from data, and it isn't first-hand tactical analysis either — it's
  reflecting the *dominant narrative* about a player that recurs across a huge volume of
  football writing and discussion it was trained on. That's a real signal (a widely-repeated
  reputation usually reflects *something* true), but it's a different thing from genuine
  expertise: it can just as easily be repeating a famous, oversimplified storyline as capturing
  real tactical nuance. The Haaland rationale is the clearest example — "he literally developed
  this profile at Dortmund" is a well-known biographical fact doing the work, not a tactical
  breakdown of his current movement patterns.

**This framing explains the pattern, not just describes it.** Sentiment/narrative (the LLM) and
subjective expertise (the human) both draw on the same broad category of information —
*known playing style and reputation* — that pure output-rate statistics structurally cannot
see, which is exactly why both cluster together against the tool on Guirassy, Haaland, Kean,
and Upamecano. But "the commonly repeated story about a player" and "one expert's actual
tactical judgment" are still not the same thing, which is exactly why the LLM and the human
still diverge on 4 of 10 cases even though they agree with each other far more than either
agrees with the tool:
- **Bellingham** — the LLM leans on his "explosive box-crasher" reputation as a contrast to
  Bayern's patient tempo; the human's "Hand-in-Glove" call plausibly reflects more specific,
  less-repeated knowledge of his actual technical adaptability inside a possession system.
- **Kobel** — a less globally-narrated goalkeeper than most on this list; the LLM's read reads
  generic ("outstanding shot-stopper with reasonable distribution") in a way that suggests
  thinner training-data coverage of his specific ball-playing limitations than the human has.
- **Rodri** — the LLM frames "tempo control" and "vertical transitions" as fully opposed
  archetypes, an oversimplified narrative contrast; the human's more moderate "Somewhat Fits"
  suggests a more nuanced read of how an elite deep-lying midfielder can still function in a
  more direct system.
- **Van Dijk** — the LLM weighs his genuine ball-playing quality as real stylistic overlap with
  Brighton's build-up; the human weighs the defensive-line/pressing-height mismatch as decisive
  enough to call it "Completely Different" instead.

**Bottom line: this is supplementary triangulation, not a second blind human.** It strengthens
the case that the tool-vs-human disagreement pattern isn't one person's idiosyncratic reading —
a completely separate reasoning process reached a similar conclusion on most of the same cases
— but it doesn't replace the need for an actual second independent human labeler, and it
shouldn't be averaged into the match-rate numbers above as if it were equivalent evidence.

## What this does *not* recommend

Unlike Track C2, this round's finding is not "the cutoffs are miscalibrated" — retuning 20 or 35
would just move which specific cases land on which side of an arbitrary line without addressing
the actual cause. The gap here is about *what the metric can see at all*, not where the line
sits. No threshold change is proposed from this data.

## Caveats

- 10 cases, one blind labeler — a genuinely independent check, but still a small sample from a
  single perspective. A second labeler doing the same 10 cases blind would be the natural next
  strengthening step, not a threshold change.
- The `your_guess` column (an informal second opinion, explicitly not independent evidence) was
  left blank in this round.
- Raw data for every case is in `eval/track_c3_samples/*.json`; the filled-in blind labels are
  in `eval/track_c3_human_labelled.csv`; `eval/score_track_c3.py` reproduces the table above
  directly from both. The fresh-LLM triangulation (not independent evidence on its own,
  see above) is in `eval/track_c3_llm_judgment.csv`.
