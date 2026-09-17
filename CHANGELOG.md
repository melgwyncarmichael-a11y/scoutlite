# Changelog

Practical, user-facing summary of what changed in ScoutLite and what you'll actually notice
the next time you generate a brief — not the full investigation. For the detailed build/debug
narrative behind each entry, see `NOTES.md`; for the evaluation findings that drove this round
of fixes, see `EVAL_REPORT.md`.

## 2026-09-17 — v3: both Signals are now fully deterministic

The biggest change yet, and it changes what the top of every brief looks like.

### Quality and Fit no longer show a bare 1–5 number — they show a label

**Quality** now reads "World Class," "Strong Starter," "Solid Starter," "Depth Option," or
"Below Rotation" — same underlying percentile math as before, just a word instead of a number
that implied more precision than the data actually has.

**Fit** is a bigger change: it's no longer a number the AI decided by reading a description of
your club's style. It's now computed the same way Quality always has been — deterministically,
by comparing this player's actual statistical profile against **a real club's current squad**
in the same position:

| Your philosophy | Compared against |
|---|---|
| Vertical, high line, counter-press | Borussia Dortmund |
| Vertical, mid block | Real Madrid |
| Vertical, low block | Atlético Madrid |
| Possession, high line | Manchester City |
| Possession, mid block | Bayern Munich |
| Possession, low block | Brighton |

You'll see a label — **Hand-in-Glove Fit**, **Somewhat Fits**, or **Completely Different** —
plus the exact numbers behind it (e.g. "this player's key passes rank 70 vs. Dortmund's 57").
The AI still writes a paragraph explaining *why*, but it no longer decides the result itself.
This directly answers something testing turned up: asking the AI for a 1–5 Fit score landed on
exactly 3/5 in every single test run, across every possible club style — the AI was correctly
refusing to guess at things (pace, pressing intensity) no data source ScoutLite uses actually
measures, but the number never moved either way. Making it deterministic fixes that.

### Quality now corrects for a real fairness problem

A defender at a team that dominates possession (like Manchester City) naturally records fewer
tackles and interceptions than an equally good defender at a team that spends more time
defending — not because they're worse, just because their team leaves them less to do. Quality
now shows **both** numbers: the raw one, and one adjusted for how much possession the player's
team actually has. On a real test case, this moved a defensive-actions reading from the 57th
percentile to the 88th once the adjustment was applied.

### Every brief now ends with a plain-English explanation of both signals

A new "Understanding the Signals" section at the bottom of every brief — the same on every
run — explains what Quality and Fit actually measure, the label scale, which club your Fit
result was compared against, and what neither signal can see (pace, sprint speed, pressing
intensity — no source available to ScoutLite tracks these).

## 2026-09-17 — Post-eval fixes (4 changes)

Four fixes made directly in response to the evaluation findings in `EVAL_REPORT.md`. All are
visible the next time you generate a brief.

### 1. Defensive midfielders no longer misclassified as defenders

**What changed:** `classify_position_group()` now also checks FBref's secondary position tag,
not just which code is listed first. A player tagged `DF-MF (CM-DM)` — a genuine defensive
midfielder — now classifies as **Midfield**. A player tagged `DF-MF (FB, right)` — a genuine
fullback — still correctly classifies as **Defense**.

**What you'll notice:** Rodri and Declan Rice now get scored against midfield creativity +
defensive-work metrics, instead of being reduced to one defensive-actions percentile as if
they were centre-backs. Verified against all 15 real Track A captures: the tool's position
call now matches the labeler's own judgment **80% of the time, up from 67%**.

**Confirmed with real numbers, not just the classification change:** Rodri's Quality score
moved **3/5 → 4/5** once his 70th-percentile key-passing output was actually counted — his
score used to reflect defensive actions alone. Declan Rice stayed at 4/5, but the number is
now backed by three dimensions of his game (key passes, xA, defensive actions) instead of one.

**Unaffected:** Wan-Bissaka, Trent Alexander-Arnold, and every attacking-midfielder case
(De Bruyne, Ødegaard, Bruno Fernandes) — only the specific ambiguity this targeted changed.

### 2. Quality signal now flags when it might be hiding a specialist's peak trait

**What changed:** if a player's individual component percentiles vary by more than 40 points,
the brief now says so explicitly, right after the existing percentile breakdown.

**What you'll notice:** on a player like Haaland — 100th percentile on goals and xG, but only
mid-50s on assists and xA — the brief now adds a line noting the composite score may
understate whichever trait they're actually best known for, instead of silently averaging a
world-class scorer down toward a 4/5.

### 3. Every Fit signal now discloses what it can't see

**What changed:** any brief where a club philosophy was assessed now carries a fixed
disclosure that Fit can't evaluate pace, sprint, or pressing intensity, because no ScoutLite
data source measures them.

**What you'll notice:** a `Fit: 3/5` now reads as "insufficient data to say more," not as a
considered middle judgment. This follows directly from the Track C finding that all 21 test
runs, across every one of the 6 possible philosophy combinations, landed on exactly 3/5.

### 4. A first line of defense against hype language

**What changed:** the automated judge now flags a short list of unambiguous hype/superlative
words ("electric," "generational," "world-class," "sensational," "phenomenal," "unstoppable,"
and similar) the same way it already flags transfer-value talk or verdict language.

**What you'll notice:** a brief is slightly more likely to get sent back for a rewrite if the
LLM reaches for this kind of language. This doesn't solve hype detection in general (that
needs the LLM supplement, not a keyword list) — it raises the floor on the most blatant cases,
directly responding to the Track B finding that the judge was only catching about half of real
hype cases.

---
*(Newest entries go above this line. Each entry should say what you'll actually notice using
the tool, not just what code changed — see `NOTES.md` for engineering detail and `eval/` for
the evidence behind each fix.)*
