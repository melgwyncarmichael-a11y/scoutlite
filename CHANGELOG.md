# Changelog

Practical, user-facing summary of what changed in ScoutLite and what you'll actually notice
the next time you generate a brief — not the full investigation. For the detailed build/debug
narrative behind each entry, see `NOTES.md`; for the evaluation findings that drove this round
of fixes, see `EVAL_REPORT.md`.

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
