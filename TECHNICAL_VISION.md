# ScoutLite — Technical Vision & Implementation Notes

*Companion doc to the PE6201 Problem Statement draft. This is a working/feasibility document, not for submission — for discussion with implementation-focused sessions (e.g. Claude Code).*

> **Build status (as of `STATUS.md`, 2026-09-25, commit `7786827`, 237 tests passing):** two significant, evidence-driven changes since the last check-in. **(1)** Quality's planned external validation (ranking against transfer value) was proposed during planning and dropped before implementation — it conflicts with ScoutLite's own hardcoded rule against transfer-value language, and transfer value is a confounded proxy anyway. A replacement (mirroring Fit's method below) is planned but not yet run (Section 4, Section 6). **(2)** Fit's validation has actually been executed — Track C3: a blind human labeler judged 10 new cases before seeing tool output, matching 4/10, with every mismatch traced to one diagnosed root cause (the metric measures statistical output, not tactical role) rather than left unexplained. A fresh, zero-context LLM session triangulated the same cases. This is real evidence, not the circular "run-to-run consistency" claim from an earlier version of this doc — a fully deterministic function is consistent by construction, which proves nothing about correctness. Full detail in Sections 4, 6, and 7. Two earlier resolved items (abstention: ship-with-warning, not hard-abstain; scoring: two separate labels, never combined) still stand as decided.

**Naming note:** the output is a **player research brief**, not a "scouting report" — think of it as a dictionary entry for a player-season: concise and standardized, covering well-known and obscure players in the same format. It goes beyond a plain dictionary/stat table by **translating raw numbers into scouting vocabulary** (e.g. "aggressive presser, limited off-ball work rate" rather than a row of figures) — that translation is the LLM's actual job, not judgment. The Quality/Fit numbers are **signals/suggested analysis for the scout to weigh**, never a claim that a player is good or bad. ScoutLite does not recommend, match, or rank players for a given need (e.g. "find me a striker like X") — that judgment call, and the final scouting decision, stays entirely with the scout. Data is explicitly an additional factor, not a replacement for watching games and video, which remains the main part of the job.

## 1. User flow

**Input (from scout/user):**
- Player name
- Year(s)/seasons of interest (scope of data to pull) — **practical lower bound: 2014/15 season**, since Understat's xG/xA coverage (the sole source for these metrics — see Section 2 for why FBref doesn't provide them) starts there; older seasons aren't reliably reconstructable from either committed source
- Short, capped free-text notes (adjective-style, e.g. "tall, can play as a 9 or 10, fast feet, gets in behind often, lacking work rate sometimes" — intentionally not a full report, to keep synthesis in scope). Per scouting-methodology research (Section 4a), this field specifically captures **role**, not position — stats alone capture position and output, not job.
- Club philosophy — two single-select dropdowns (not free text, to keep inputs consistent and testable):
  - **In possession:** vertical/fast transitions vs. slow/methodical possession
  - **Out of possession:** high line/counter-press vs. low block/counter vs. mid block/hybrid
  - *(Single-select for MVP; primary+secondary blend considered but deferred — adds real testing surface for a "nice to have" realism gain)*

**Pipeline (deterministic, not agentic):**

The LLM does not search or browse for data itself — that pattern (AI as scraper) is slower, costlier per-player, and non-deterministic. Instead, the architecture is a fixed pipeline of parameterized function calls, with the LLM reserved for the synthesis and judging steps only:

```
Scout input (Streamlit)
        ↓
Deterministic data lookup — parameterized calls to FBref + Understat scrapers + NewsAPI,
by player name + year (not an open-ended agent search). FotMob, Transfermarkt, and Reddit
were evaluated and are not core sources for now — see Section 2.
        ↓
Data found? ──No──→ "Player not found" error, fails visibly, no synthesis attempted
        │
       Yes
        ↓
Structured data package (stats, news text)
        ↓
LLM synthesis — combines stats + scout notes + philosophy selections into a draft research brief
        ↓
LLM judge — checks structure completeness + source-claim matching only (narrow, testable
criteria, not open-ended "is this good"). Loop is capped at 2 iterations, but can exit early
if it clears an 80% source-accuracy threshold on iteration 1.
        │
        ├─ Below 80% after 2 iterations → ship the brief anyway, with a visible confidence
        │  warning at the top (hard-abstaining here was considered and rejected — a flagged
        │  brief still gives the scout something to work with, honestly labeled, rather than
        │  nothing at all after the tokens are already spent)
        ├─ 80% or above → ship, and always display the verified-confidence score at the top
        │  (e.g. "92% verified"), not only when something's wrong — transparency by default.
        ↓
Evals computed on the final brief (factuality %, source attribution, quality-signal-vs-blind-human-label —
mirroring Fit's Track C3 method, planned but not yet run, see Section 6 and Section 7). Flagged
low-confidence cases are also checked after the fact: were they actually the cases that were wrong?
        ↓
Word doc output
```

This shape means there's no "search budget" to manage — token cost is concentrated at the synthesis/judge steps, which is exactly where it should be spent.

**Output — Word doc only, a research brief, not a "report" or verdict:**
- **Signals, at the top:** Quality (1-5 percentile-based label, e.g. "World Class") and Fit (3-tier label, e.g. "Hand-in-Glove Fit," against a real reference club) — reported as two separate labels, not summed into a combined figure — plus a verified-confidence score (e.g. "92% verified") shown on every brief, not just flagged ones. Framed as data points for the scout to weigh, not a conclusion.
- **1. Who he is** — bio, background, club history
- **2. Stats & performance** — production across teams, tables, position-grouped
- **3. What people say** — news/sentiment context
- **4. Signals & fit read** — the quality/fit signals presented alongside the evidence that produced them (renamed from "conclusion" to avoid implying ScoutLite reaches a verdict)

**On low confidence:** the only true decline-to-answer is "player not found" (data doesn't exist). A brief that clears the data-lookup stage but stays below 80% source-accuracy after 2 judge iterations still ships, carrying a visible confidence warning rather than being withheld. This is measured in evals: how often the warning triggers, and whether flagged briefs were actually the ones that contained real errors (checked against factuality).

## 2. Data sourcing — status & risk

| Source | Purpose | Access | Risk / note |
|---|---|---|---|
| FBref | Basic stats + deep historical archive | Scraping — mature tooling exists (`soccerdata`, `ScraperFC` Python libs; unofficial `fbrapi.com` JSON wrapper) | Permitted but rate-limited: 10 requests/minute, violations block a session up to 24 hours. **Important:** FBref's free/public pages have never exposed progressive-passes/carries or a true duel-success-rate metric — this was confirmed directly during the build by checking both FBref's own "On this page" table-of-contents and Understat's actual `getPlayerData` API response, not just assuming from page labels. This is a pre-existing free-tier data limitation, not a recent removal event. Basic stats (goals, assists, appearances, cards) and the historical archive remain reliable. **Core source for basic stats and history.** |
| Understat | xG/xA and shot-level data | Scraping — established Python libraries exist (e.g. `understat`, also covered by some `soccerdata` pulls) | Runs its own independently-built xG model. Covers Big 5 leagues + Russian league, reportedly from the 2014/15 season onwards *(coverage start date as commonly cited; not independently re-verified against Understat directly this session)*. **The sole source for xG/xA and key-pass data** — the quality signal's attack/midfield groups depend on it directly, since FBref's free pages don't provide these (see FBref row above). |
| NewsAPI | News context | Official API, free tier | Rate-limited on free tier |
| Transfermarkt | Stats, market value, transfer history | Scraping (also covered by `ScraperFC`; no official API) | `robots.txt` confirmed to exist with real rules; existing scraper tooling (`transfermarkt-scraper`) is built to respect it. Exact scope not independently verified — **not currently a committed pipeline source, and not integrated at all.** A transfer-value-based validation for the Quality signal was proposed during planning and dropped before implementation (see Section 4, Section 6) — it conflicts with ScoutLite's own hardcoded rule against transfer-value language, and transfer value is a noisy, confounded proxy for on-pitch quality anyway. No manual or automated Transfermarkt lookup has been done for any eval batch. |
| FotMob | Match-level stats | N/A | **Excluded.** Direct fetch test confirmed `robots.txt` explicitly disallows automated access to its data endpoints — a stronger, more explicit signal than an unofficial-API gray area |
| Reddit | Sentiment / word cloud | Official API (PRAW), free tier | **Dropped from current scope** to keep the build focused on the core stats-and-news loop. May be reintroduced later — if so, revisit the PDPA note below. |
| Images | Visuals for report | **TBD — nice-to-have** | Must use free/appropriately-licensed sources (e.g. Wikimedia Commons) rather than scraping arbitrary images, to avoid copyright issues. Not core to MVP. |

**Note on FBref vs. FotMob vs. Transfermarkt risk tiers** — these are not equivalent risks and shouldn't be treated as one bucket: FBref's constraint is a documented, known rate limit you can engineer around; FotMob's is an explicit `robots.txt` disallow, a clear signal to not proceed; Transfermarkt sits in between — real rules exist but their exact scope is unconfirmed, so it stays an open question rather than a "probably fine" assumption.

**Note on AI-as-scraper:** considered and rejected — using an AI agent to browse/extract data directly is slower, costlier per-player, and less reliable than the existing scraping libraries above, which return clean structured data. Right division of labor: dumb-but-reliable tools handle collection; the LLM is reserved for synthesis/reasoning, where it actually adds value ("don't use a hammer for drill work").

**PDPA note:** with Reddit dropped, the current data plan (public stats and published news about players acting in a professional/public capacity) sits differently under Singapore's Personal Data Protection Act than the Reddit-inclusive plan did — it is not personal data collected from private individuals. Revisit if Reddit or another social-sentiment source is reintroduced.

**Repository portability:** bulk FBref/Understat data cannot be redistributed in a public repository. The repo ships a small cached sample — the actual data for the 10-player eval batch only — plus a README stating plainly that bulk data is not included, and that live use requires running the scraper against FBref directly, subject to its documented rate limit.

## 3. Build vs. buy

Working down the stack layer by layer:

| Layer | Own or rent | Reasoning |
|---|---|---|
| Interface | Own | Simple input form (name, year, notes, club philosophy) |
| Orchestration | Own | The deterministic pipeline + conditional judge/revise loop is specific to this problem |
| Model | Rent | LLM API, tiered by task (see Section 5) |
| Data & retrieval | Own | Scrapers for FBref/Understat + NewsAPI calls, built on existing libraries rather than from scratch |
| Evaluation & observability | Own | Factuality checks, judge validation, and the signal-scoring logic |

**Low-code:** no no-code tool (Zapier, n8n, a hosted assistant builder) was evaluated. The task needs custom scraping against FBref/Understat (not standard connectors in those tools), a deterministic multi-step pipeline with a conditional judge/revise loop, and direct control over prompt structure and API cost — none of which fit a no-code trigger-action model. Code was the realistic route from the start; this is a stated decision, not an unconsidered gap.

**Why not RAG:** considered and rejected. RAG fits when answers must be grounded in a held document corpus — but the inputs here are structured stats tables refreshed per query, not a static document store to retrieve passages from. There's no retrieval step that adds value: the relevant data is already fully assembled before the LLM call, so a retrieval layer would add cost and complexity without a corresponding benefit.

## 4. Scoring methodology

Per professor feedback: avoid conflating "this is a bad player" with "this is a poor fit for this system" — a great player can score low on fit without that meaning they're a weak player. Quality and Fit are reported as **two separate labels, never combined into one figure** — a summed score would blur exactly the distinction the professor flagged, so the design deliberately keeps them apart rather than compressing them into a single headline number.

**As actually built:**
- **Quality:** a 1-5 percentile-based label (e.g. "World Class") — **fully deterministic, zero LLM involvement in the number itself**, only in the prose explaining it. This is a stronger version of "signal, not judgment" than a simple framing note: the AI doesn't just avoid stating a verdict, it never touches the score at all.
- **Fit:** a **3-tier deterministic label** (e.g. "Hand-in-Glove Fit") compared against 6 hardcoded reference clubs, one per in-possession × out-of-possession philosophy combination. This replaced an earlier 1-5 LLM-influenced score after eval work (Track C, then C2) found the original approach landed on exactly 3/5 in 21 out of 21 test runs regardless of input — it wasn't discriminating between players at all. The 3-tier percentile-threshold system replaced it, and the lower cutoff was itself tuned with real eval evidence (raised from 15 to 20 percentile points after two genuine standout players missed the top tier by 1-2 points — match rate improved from 2/9 to 4/9 on the hand-picked validation set). The upper cutoff (35, "Completely Different") is still unvalidated.

- **Quality label derivation:** derived from **position-grouped, context-aware stats** rather than raw counting stats, since raw totals are confounded by team quality — and the build has since added **possession-adjustment (PAdj)**, so a dominant-possession team's defender isn't penalized for facing fewer defensive actions per 90, a confound named in Section 4a that's now partially addressed rather than only disclosed. Benchmarked against a **non-AI rule-based baseline** (percentile-averaged stats mapped to a label via fixed cutoffs, no LLM involved) — the deterministic signal needs to beat this simple lookup to justify itself. Three broad position groups:
  - **Attack:** goals, assists, xG, xA (per 90) — sourced from Understat, since FBref's free pages don't provide xG/xA (see Section 2)
  - **Midfield:** key passes, xA, xG-chain/xG-buildup involvement (per 90) — sourced from Understat. Progressive passes/carries are **not available from either committed source** on their free tiers; this stat group is narrower than originally planned as a result.
  - **Defense + GK:** tackles won, duel success rate (per 90/rate) for outfield defenders; save % for GK — **confirmed, not just flagged, as structurally noisier than the other groups.** Direct checks against both FBref (via `soccerdata`) and Understat found only one shared defensive metric (`defensive_actions_per90`) versus 3-4 for other groups. A real fix needs a new scraper for a league-wide defensive-actions table — deferred as out of scope for now, disclosed as a named limitation rather than solved.
  - **External validation — transfer value dropped, mirroring Track C3 planned as replacement.** The original design proposed validating Quality by ranking against real transfer value (the professor's "Ronaldo" concern). This was dropped during planning, before any implementation, for two reasons: it directly conflicts with ScoutLite's own hardcoded rule against transfer-value language ever appearing in a brief (can't validate against the exact thing the tool refuses to reference), and transfer value is itself a noisy, confounded proxy for on-pitch quality (age, contract length, hype, position scarcity). **Replacement (planned, not yet run):** mirror Fit's Track C3 methodology exactly — independent blind human judgment of "how good is this player, in general, regardless of club" on the same test batch, scored the same honest way.
- **Fit label derivation and validation — already run, real results.** Compares the player's stats/style + scout's notes against 6 reference-club profiles. Per Section 4a's position-vs-role distinction, the scout's notes carry role information into this comparison. **Track C3** ran the actual validation: a blind human labeler judged 10 new cases (3 defenders, 3 midfielders, 3 attackers, 1 GK; 5 known/5 relatively unknown; spanning 4 of 5 top-5 leagues) *before* seeing tool output. **Result: 4/10 matched** — worse than Track C2's 4/9, but every mismatch traces to one diagnosed root cause: the metric captures statistical output rate, not tactical role/style, which none of ScoutLite's sources measure. This is not a regression from making Fit deterministic — the pre-v3 LLM-judged version had the identical blind spot (21/21 runs stuck at 3/5, effectively refusing to guess at pace/pressing data it also lacked). **Triangulation:** a fresh LLM session with zero access to this project or the tool's output independently judged the same 10 cases from general football knowledge — it agreed with the blind human on 6/10 but with the tool on only 3/10, suggesting its read tracks closer to aggregated public reputation/narrative than either pure stats or first-hand tactical expertise. **Honest limitations, stated plainly rather than glossed over:** one blind human labeler so far, not two — a second independent labeler is the natural next strengthening step. The upper cutoff (35) remains entirely unvalidated; only the lower one has real tuning evidence behind it.

**A broader non-AI baseline also applies to the whole tool, not just the quality signal:** a scout manually curating FBref/Understat stat tables and formatting them into a research brief by hand. A simple script could automate the formatting step alone — the LLM's specific value-add is the signal synthesis (reading notes + philosophy + stats together), which formatting automation alone can't do. Time-to-brief versus this manual baseline is tracked as a secondary metric (Section 6).

**Why coarse labels rather than a fine-grained score:** coarser scales are more reproducible for both human raters and automated checks — clear anchors are easier to define and test for consistency than finer-grained scales, where small differences aren't reliably distinguishable. The Fit 21/21-run finding above is direct evidence of what happens when a scale is too fine for the signal actually available: it collapses to the same value rather than discriminating.

## 4a. Grounding in professional scouting methodology

A secondary research summary on professional scouting tools and methods (see companion doc, "Professional scouting tools and methods in football") surfaces several points that sharpen design decisions already made, rather than requiring new ones:

- **Position vs. role.** Scouting practice draws a sharp distinction: position is where a player starts, role is what they must repeatedly deliver. The scout's short free-text notes field (e.g. "can play as a 9 or 10, gets in behind often") is specifically what captures *role* — stats alone (and the position-grouped scoring) capture position and output, not job. This validates the free-text notes field as methodologically load-bearing, not just a nice-to-have input.
- **Four-stage scouting pipeline** (identification → shortlisting → deep evaluation → reporting) gives ScoutLite a precise place to sit: it operationalizes identification and shortlisting, and can support early deep evaluation, but does not perform the live/video-dependent parts of deep evaluation or replace the human reporting/recommendation. This is the basis for the "research/data layer, not a scouting report" reframe — ScoutLite is explicitly upstream of the report a scout would eventually write themselves.
- **Method-specific weaknesses.** The three core scouting methods (data, video, live) are complementary, and data specifically "loses context and risks role misuse when metrics are detached from game model" when used alone. This is a direct, sourced justification for why ScoutLite's data-only scope is an honest, named limitation rather than an implicit gap.
- **Named context confounds.** Opposition quality, team game model, match state, and competition tempo are named factors that change how a stat should be interpreted (e.g. low pressure can inflate time-on-ball figures). This gives the "good team average player" confound specific, citable categories rather than a single vague caveat — and these are **not currently corrected for** in the quality signal, which should be stated plainly as a limitation.
- **Report format caution.** The same research warns that new scouts often over-produce graphics-heavy dossiers, which professional decision-makers don't actually want — reports should be concise and quick to read. Worth keeping in mind if there's any temptation to add more visual elements to the research brief beyond the stat tables already planned.

*(Caveat on the source itself: several of its citations trace to a single author's framework, so this should be treated as one credible perspective to cite, not an independently verified consensus.)*

## 5. Cost structure (conceptual, with actual build noted)

Per professor feedback: evals and costing are the next milestone, and model choice should be deliberate, not default-to-biggest ("don't use a hammer for drill work").

- **Free/near-free:** all scraping (FBref/Understat — compute time only), NewsAPI (free tier), own hosting for a course-scale project.
- **As designed:** a stronger model (e.g. Claude Sonnet 5, ~$2/$10 per million input/output tokens) for synthesis, a cheaper/faster model (e.g. Claude Haiku 4.5 at ~$1/$5, or DeepSeek V3.2 at ~$0.21/$0.31) for the narrow, mechanical judge and evals checks — two separate clients. *(Pricing figures approximate — not independently re-verified against current provider pricing pages this session; worth confirming against the live pricing docs before citing exact numbers in a submission.)*
- **As actually built:** a single DeepSeek-V3 client, shared as one lazy singleton (`llm_client.py`), used for both the synthesis call and the judge's fact-check call. This simplifies the "tiered model" story from two providers to one, but the underlying reasoning still holds — DeepSeek-V3 was chosen specifically because it's cost-conscious relative to a flagship model, so the "right-sized model, not the biggest" argument is intact even with one model rather than two. Worth stating plainly in the write-up: consolidating three separate `OpenAI(...)` client instantiations into one shared singleton was also a real fix made this week, for both cost and correctness reasons (one client instance rather than one per call).
- **Real cost driver — LLM API calls**, governed by input tokens (stats table + scout notes + news text + philosophy selections), output tokens (length of the generated research brief), and model choice as above.
- **Estimate:** the original tiered estimate (~$0.05–$0.06/report with Sonnet+Haiku) is likely now an overestimate given the single, cheaper DeepSeek-V3 model actually used — worth recalculating with real token counts from the live pipeline rather than carrying the original estimate forward unchanged.
- **Scale consideration (not needed for course project, worth one line in write-up):** cost is per-report, so viability at real volume (many scouts × many players) is a different question than course-project feasibility.

## 6. Evals concept

For each generated brief, computed **after the judge passes (or exhausts its loop)**, on the final text:
- **Source attribution:** % of content traceable to each source (stats vs. news vs. scout's own notes)
- **Factuality:** % of stat claims independently verifiable against source data
- **Quality-signal validity — transfer value dropped, blind-labeling planned as replacement.** Ranking Quality against transfer value was proposed and dropped before implementation: it conflicts with ScoutLite's hardcoded rule against transfer-value language, and transfer value is itself a confounded proxy. Replacement (not yet run): mirror Fit's Track C3 methodology — independent blind human judgment of general player quality, regardless of club, on the same test batch, scored honestly against the tool's label.
- **Fit-signal validity — already run (Track C3), real result: 4/10 matched.** Not run-to-run consistency (which is circular for a fully deterministic function — it's guaranteed to be perfectly consistent by construction and proves nothing about correctness). Instead: a blind human labeler judged 10 new cases before seeing tool output; every mismatch traced to one root cause (the metric measures statistical output rate, not tactical role, which no source captures) rather than being scattered/unexplained. A fresh, zero-context LLM session triangulated the same 10 cases, agreeing with the human on 6/10 and the tool on 3/10.
- **Time-to-brief:** compared against the manual-curation baseline (Section 4) — the direct test of the actual time-saved value claim
- **Model comparison:** since the actual build uses a single DeepSeek-V3 client (Section 5) rather than a tiered setup, this now means comparing DeepSeek-V3 against one other model on the same eval suite, if time allows, rather than a two-tier-by-design comparison

**Judge vs. evals — different jobs:** the judge (in the pipeline) checks structure and source-matching *during* generation, with a pass/revise loop. Evals run once, after, on the finished brief — they measure the pipeline's overall quality/validity, not any single brief's pass/fail.

## 7. Manual test plan — real results for Fit, planned for Quality

The plan below was originally written before either validation ran. Fit's has since actually been executed (Track C3, see Sections 4 and 6) with real, honestly-reported results; Quality's blind-labeling replacement has not been run yet. The selection logic below still applies to whichever batch runs next.

**Player selection — vary across three axes, not just league:**
- **League tier:** a few top-5 league players (best data coverage), a few second-tier league players, and 1-2 from a data-sparse league — tests the limits of source coverage
- **Profile type:** an obvious elite/famous player (easy mode), a solid-but-unspectacular squad player (average case), and a genuinely under-the-radar player (stress case, and arguably closest to the tool's actual target user). Track C3's actual batch followed this shape: 5 known/5 relatively unknown players.
- **Position spread:** at least one player per position group. Track C3's actual batch: 3 defenders, 3 midfielders, 3 attackers, 1 GK.

**Per-player, record:**

| Check | What it tests |
|---|---|
| Was the player found at all? | Coverage — does "not found" trigger correctly? |
| Stat claims in brief vs. source tables | Factuality % |
| Quality label vs. blind human "how good, in general" judgment (planned, not yet run) | External validity, replacing the dropped transfer-value approach |
| Fit label vs. blind human judgment, judged before seeing tool output (already run — Track C3) | 4/10 matched; root cause diagnosed, not just reported |
| Judge outcome (passed iteration 1 / needed revise / hit the 80% flag) | Whether the judge/threshold behaves sensibly across data quality |
| What broke or felt thin | Raw material for the limitations section |

**Maps back to three original questions:**
1. **Accuracy vs. the dataset** — factuality % holds up as a check regardless of the scoring-validation change; still worth checking across league tiers
2. **Limitations** — Track C3 already surfaced a real, diagnosed one (Fit's blind spot on tactical role/style) rather than a hypothetical one from the sparse-data cases
3. **How useful the evals actually are** — Track C3's honest 4/10 with root-cause diagnosis is a stronger answer to this than a clean pass would have been; the same rigor now needs applying to Quality

**Batch-size caveat:** 10 players is directional evidence, not statistical proof. One atypical or flaky case could shift the result — if a single player's outcome is doing most of the work in either direction, that should be named explicitly in the write-up rather than glossed over.

**Intended use / explicit non-use:** intended as a research input for an independent scout during identification and shortlisting. Explicitly not intended: as the sole basis for a final signing/contract decision without human review, or as a public-facing player-rating or ranking product.

## 8. Open questions for implementation discussion

- ~~Scraping approach~~ — resolved: FBref + Understat only, rate-limit-aware pacing built in; FotMob dropped (robots.txt disallow); Reddit dropped from scope; Transfermarkt remains open pending direct robots.txt confirmation
- ~~Defense + GK stat availability~~ — confirmed (not just flagged): checked both FBref and Understat directly, only one shared metric (`defensive_actions_per90`) exists. A real fix needs a new league-wide defensive-actions scraper; deferred as out of scope, disclosed as a named limitation.
- ~~Abstention logic~~ — resolved: ship with a visible confidence warning below 80%, not a hard abstain. Decided against withholding the brief entirely — a flagged brief still gives the scout something to work with after the tokens are spent, honestly labeled.
- ~~Combined /10 vs. separate labels~~ — resolved: Quality and Fit are reported as two separate labels, never summed. This deliberately avoids blurring the "bad player" vs. "poor fit" distinction the professor flagged.
- ~~Whether an existing MCP server could replace the custom FBref/Understat scraping~~ — checked (2026-09-26): a few do exist, more than expected. [`kupsas/football-data-mcp`](https://github.com/kupsas/football-data-mcp) unifies FBref, Understat, SofaScore, and Transfermarkt behind an MCP interface — closest match on paper — but it's a static, pre-scraped dataset (10 leagues, three fixed seasons: 2023-24 through 2025-26), not a live per-player/per-season lookup, so it wouldn't cover most of Track C3's cases or anything before 2023-24. Several Apify-hosted "FBref/Understat scraper MCP servers" also exist, but they're commercial, usage-metered wrappers scraping the same sites ScoutLite already scrapes directly — using one wouldn't remove the "it's scraped data" caveat, just move the scraping to a third party. More fundamentally, wiring in any MCP data server would mean letting the LLM fetch data itself via tool calls at synthesis time — exactly the "AI-as-scraper" pattern already evaluated and rejected above for being slower, costlier per-player, and non-deterministic. Conclusion: none are a better fit than the current deterministic scraping pipeline; the check confirmed the existing design choice rather than changing it.
- **Quality's external validation — planned, not yet run.** Transfer-value ranking was proposed during planning and dropped before implementation (conflicts with the tool's own no-transfer-value-language rule, and is a confounded proxy anyway). Replacement: mirror Fit's Track C3 blind-labeling method. Needs an independent human labeler and a test batch, same as Fit had.
- **A second independent blind labeler for Fit** — Track C3 used one; a second is the natural next step to confirm the 4/10 finding isn't one person's particular reading, not a different person's opinion overturning it.
- **Judge's 80% threshold has never been checked against a human labeler** — a protocol exists in `NOTES.md` but hasn't been run. This is the actual evidence needed to know if 80% is the right cutoff at all.
- Whether/how to correct the quality signal for the remaining named context confounds (opposition quality, match state, competition tempo) not yet addressed by PAdj — team-quality confound is partially handled now, the others are not
- Report generation: is the Word doc built directly (python-docx style) or LLM-drafted text placed into a template — resolved in practice via `docx_report.py`, worth documenting the actual approach here
- Images: confirm whether to include at all for MVP, or defer entirely to "future work"
- **Scope of "years of knowledge" input** — handled implicitly, not by a dedicated validation rule. There's no explicit "reject seasons before 2014/15" check in the code. In practice this rarely bites in the Streamlit app, since its season dropdown only ever lists seasons that actually exist on the player's real FBref page; the CLI already fails with a visible "season not found" error on a bad input, but that's generic error handling, not a deliberate Understat-coverage-aware rule. Still open if a dedicated check is wanted.
- Comparison mode (`scoutlite_compare.py`) is CLI-only, not yet in the Streamlit app that's documented as the recommended entrypoint — worth deciding whether this matters before submission

## 9. Explicitly out of scope for now

- "Does this player fit my team" system-matching feature
- Match footage / video analysis
- Reddit and X/Twitter sentiment (dropped from current scope)
- Primary + secondary club philosophy blend (single-select only for MVP)
- Sub-position granularity in stat groups (3 broad groups only)
- PPT output (Word doc only)
- Transfermarkt as a committed pipeline source (not integrated; no manual lookup performed either)
