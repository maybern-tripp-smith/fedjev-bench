# FedLock-faithful protocol replication — Findings

**run_id:** `fedjev-fedlock-replica-2026-09-20`  
**Companion claim (do not conflate):** Gate 7 in the main bench is a different experiment. Gate 7 asks whether this repository’s Bradley–Terry and Score series *agree in rank* with published FedLock scores. This note asks whether a *separate* tournament, run on the same 95 chair openings under FedLock V3’s documented protocol, recovers a similar ordering. It is not a 4,000-speech / ~60,000-comparison scale copy of the published FedLock run.

This document is written so a reader fluent in finance and monetary policy, but not in natural-language processing, can re-implement the comparison from the prose and the frozen artifacts. Numbers below are taken from `agreement.json` and `cost_performance.json`. None were invented for this write-up.

---

## 1. What each name means in this note

**Federal Open Market Committee (FOMC).** The Federal Reserve committee that sets the federal funds target. The documents scored here are the Chair’s opening remarks at post-meeting press conferences (95 openings in `data/clean/statements.jsonl`).

**Behavioral label versus textual hawkishness.** The Committee’s voted action is a *behavioral* label. In the main bench that label is `d_same`, the same-day change in the federal funds target: hike, hold, or cut. A hold day has `d_same = 0` by construction, so the behavioral label cannot say whether the *wording* of a hold was hawkish or dovish. *Textual hawkishness* is a separate construct: how hawkish the opening sounds about inflation and the policy path. This replica ranks openings on textual hawkishness *relative to the macro conditions attached to each text*. It does not use `d_same` as the scoring target.

**FedLock.** An independent, published scoring project ([methodology](https://jnathan9.github.io/fedlock/); snapshot in `data/raw/fedlock/data.json`). FedLock V3 runs a large pairwise tournament: a large language model (Llama 3.3 70B) is shown two anonymized speeches and asked which takes the more hawkish monetary-policy stance *given* contemporaneous macro conditions. Those pairwise wins are aggregated with TrueSkill (defined below) over roughly 60,000 comparisons and 4,000 speeches. This repository does **not** re-invoke Llama. It only reads the published `press_conference` fields:

| Published field | Meaning in FedLock |
|-----------------|--------------------|
| `m` | Raw TrueSkill mean (μ) — the meeting’s absolute text-hawkishness score |
| `ma` | Era-adjusted mean — `m` after subtracting a quarterly (era) average, so the score is relative to that period’s typical language |
| `s` | TrueSkill uncertainty (σ). Lower means the tournament has seen enough matches that the mean has settled |
| `n` | Number of comparisons that speech entered in FedLock’s own run |
| `st` | Speech type. This note uses `press_conference` only |
| `d` | Calendar date on the FedLock record |

**TrueSkill versus Bradley–Terry.** Both turn pairwise “A beats B” judgments into a number per document. They are not the same estimator.

- **Bradley–Terry** (used in the *main* bench, Gates 1–7) fits one strength per document from a fixed set of gold pairs. It does not carry a per-document uncertainty that is used to decide which pair to ask next.
- **TrueSkill** (used by *published FedLock* and by *this replica*) is Microsoft’s Bayesian skill-rating system, originally built for matchmaking. Each document starts with a prior mean μ₀ = 50 and a prior uncertainty σ₀ = 8.33. After each match the winner’s mean rises, the loser’s falls, and both uncertainties shrink. The replica stops when every document has σ < 2.0, or when it hits the comparison caps below. **σ < 2** is therefore a *convergence rule*, not a hawkishness threshold: it means “we have asked enough matches that further matches are unlikely to reorder this document much.”

**Anonymized pairwise tournament.** Each comparison shows two stripped texts (Text A, Text B) and asks which is more hawkish. *Anonymization* here means `scripts/strip_meta.py` removes speaker titles, calendar dates, and chair surnames before the judge sees the text. Chair identity is not placed in the judge’s input. Presentation order of Text A / Text B is randomized each match so a left/right habit cannot pile onto one meeting.

**Macro-conditioned judgment.** The judge is *not* asked “which text uses more hawkish words in isolation.” Each text is paired with four Federal Reserve Economic Data (FRED) series as of that speech date: core personal consumption expenditures inflation (PCEPILFE, year-over-year when a twelve-month change is computable, otherwise the level); the civilian unemployment rate (UNRATE); real gross domestic product growth (GDPC1, quarter-over-quarter at a seasonally adjusted annual rate when available, otherwise year-over-year); and the CBOE Volatility Index close (VIXCLS). The instruction is to judge relative hawkishness *given those conditions*. A 2 percent inflation remark in 2012 is not treated as the same stance as a 2 percent remark in 2022.

**Gate 7 versus this replica (two claims).**

| | Gate 7 (main bench) | This replica |
|--|---------------------|--------------|
| Question | Do the main bench’s Bradley–Terry / Score series agree in rank with published FedLock `m` / `ma`? | If we *re-run a FedLock-style tournament* on the 95 openings, do Jev, Haiku, and published FedLock order meetings the same way? |
| Judge protocol | Fixed criterion `more hawkish about inflation`; no macro in the prompt; Bradley–Terry (and a direct Score pass) | Macro-conditioned relative hawkishness; TrueSkill; Swiss / uncertainty pairing |
| What is *not* claimed | A TrueSkill or macro-conditioned replication of FedLock | A 4,000-speech / ~60,000-comparison scale copy of FedLock |

**The three arms.**

| Arm | What it is | What it is not |
|-----|------------|----------------|
| **Jev** | TypeSafe SystemOne Choice, model `jev-latest`. Live calls in this run; answers cached under `runs/fedlock_replica/`. | Not the main-bench Bradley–Terry graph. |
| **Haiku** | Anthropic Claude `claude-haiku-4-5-20251001`, asked for a structured JSON winner and a soft probability. | Not Llama 3.3 70B (FedLock’s published judge). |
| **Published FedLock** | Frozen `m`, `ma`, `s`, `n` from `data/raw/fedlock/data.json`. | Llama is not re-invoked. This arm is a *reference ranking*, not a third live tournament. |

---

## 2. Procedure a reader can re-run (from cached outputs)

Do not mutate `data/pairs/gold_pairs.jsonl` or the cached replica logs. To *recompute* the tables in this note from what is already on disk:

1. Confirm the corpus: 95 openings in `data/clean/statements.jsonl`.
2. Confirm macro vintages in `data/raw/fred/` (PCEPILFE, UNRATE, GDPC1, VIXCLS) and the as-of join in `results/fedlock_replica/macro_asof.json`.
3. Confirm published FedLock scores in `data/raw/fedlock/data.json`, speech type `press_conference`.
4. Read the two tournament logs: `comparisons_jev.jsonl` (1,034 comparisons) and `comparisons_haiku.jsonl` (1,033 comparisons).
5. Read the fitted ratings: `trueskill_jev.csv` and `trueskill_haiku.csv` (columns `date`, `doc_id`, `mu`, `sigma`, `n_comps`).
6. Match openings to FedLock on the FedLock `d` field, trying calendar offsets 0, +1, −1, +2 days. This run matched **92 of 95** openings (`fedlock_matches.json`).
7. Rank-correlate the three μ / `m` / `ma` series. Agreement statistics are stored in `agreement.json` (Spearman and Kendall, each with a bootstrap standard error from 1,000 resamples and a percentile 95 percent confidence interval).
8. Read listed-price accounting from `cost_performance.json`.

To *rebuild* the tournament from the same protocol (optional; not required to read this note), the entry point is `scripts/run_fedlock_replica.py`. Stopping rule, priors, and pairing are listed in §3.

---

## 3. Methods

**Judge task.** Pairwise selection of the more hawkish monetary-policy stance **conditional on the four macro series attached to each text**, using the instruction string in `scripts/run_fedlock_replica.py` (`JUDGE_INSTRUCTIONS`). Texts are anonymized as defined above.

**Aggregation.** Microsoft TrueSkill with priors μ₀ = 50, σ₀ = 8.33. Pairing is Swiss-style with uncertainty targeting: the next match prefers documents that still have high σ (the rating is still loose) and opponents with a similar μ (so the match is informative). Soft probabilities from the judge update ratings by interpolating a decisive win and a decisive loss, weighted by the judge’s probability that A wins (confidence-weighted). The tournament stops when every document has σ < 2.0, or at about 30 comparisons per document, with a global cap of 2,850 comparisons.

**Date match to published FedLock.** Offsets 0, +1, −1, +2 on the FedLock `d` field: **92** of 95 openings matched.

### Protocol deviations / notes (observed)

- Corpus is 95 chair openings (the same jsort-style openings as the main bench), not FedLock’s ~4,000-speech pool.
- Soft TrueSkill via outcome interpolation of `rate_1vs1` under the judge’s p(A) / p(B) is a documented approximation to FedLock’s “updates by judge confidence,” not a bit-exact copy of an unpublished update kernel.
- VIXCLS and GDPC1 were downloaded into `data/raw/fred/` for this experiment so the four-series macro set is complete.
- One Haiku comparison failed JSON parse mid-tournament (truncated rationale). That round continued with 46 pairs. The parser was later hardened. Jev did not have this failure.
- Both live arms stopped on `all_sigma_lt_2` (every document’s σ below 2.0), at about 22 comparisons per document on average — below the 30-per-document and 2,850 global caps.

---

## 4. How to read the agreement table

**Spearman’s rank correlation** asks: if you sort meetings by one arm’s score and again by the other, how similar are the two orderings? +1 is identical ranks; 0 is no rank association; −1 is reversed ranks.

**Kendall’s rank correlation** asks a pairwise version of the same question: for two meetings, do the two arms agree on which meeting is more hawkish? It is typically smaller than Spearman on the same data; that is a property of the statistic, not a second sample.

**Standard error (s.e.)** on these correlations is the standard deviation of 1,000 bootstrap resamples of meetings (see `agreement.json`, `n_boot`). The 95 percent confidence interval is the percentile interval from the same resamples. This note writes “standard error” or “s.e.” It does not use the label STE.

**n** is the number of meetings in that contrast: 95 when both live arms have a rating; 92 when a published FedLock score must be present.

---

## 5. Results

### Rank agreement

- **Jev ↔ Haiku.** Spearman = +0.955 (s.e. = 0.012; 95% CI [+0.923, +0.971]; n = 95); Kendall = +0.830 (s.e. = 0.023; 95% CI [+0.784, +0.873]; n = 95).
- **Jev ↔ FedLock `m` (raw).** Spearman = +0.965 (s.e. = 0.011; 95% CI [+0.934, +0.978]; n = 92); Kendall = +0.850 (s.e. = 0.021; 95% CI [+0.806, +0.888]; n = 92).
- **Jev ↔ FedLock `ma` (era-adjusted).** Spearman = +0.790 (s.e. = 0.044; 95% CI [+0.681, +0.853]; n = 92); Kendall = +0.576 (s.e. = 0.043; 95% CI [+0.492, +0.658]; n = 92).
- **Haiku ↔ FedLock `m` (raw).** Spearman = +0.945 (s.e. = 0.013; 95% CI [+0.910, +0.962]; n = 92); Kendall = +0.798 (s.e. = 0.023; 95% CI [+0.753, +0.841]; n = 92).
- **Haiku ↔ FedLock `ma` (era-adjusted).** Spearman = +0.768 (s.e. = 0.042; 95% CI [+0.666, +0.828]; n = 92); Kendall = +0.550 (s.e. = 0.042; 95% CI [+0.463, +0.629]; n = 92).

### Cost and performance (listed prices; not an accuracy claim)

Prices used for the accounting: Jev $0.042 per million input tokens, output free; Haiku $1.0 per million input tokens and $5.0 per million output tokens.

| Arm | Comparisons | Input tokens | Output tokens | USD | Effective $/million tokens | $/comparison | Latency mean / median / 95th percentile (ms) | Comparisons/s |
|-----|------------:|-------------:|--------------:|----:|---------------------------:|-------------:|---------------------------------------------:|--------------:|
| Jev | 1034 | 3,376,150 | 28,768 | 0.1418 | 0.0416 | 0.000137 | 283 / 271 / 419 | 22.978 |
| Haiku | 1033 | 3,347,688 | 48,412 | 3.5897 | 1.0570 | 0.003475 | 732 / 687 / 988 | 8.156 |

Jev stop: `all_sigma_lt_2`; max σ = 1.986; fraction with σ < 2 = 1.000.  
Haiku stop: `all_sigma_lt_2`; max σ = 1.965; fraction with σ < 2 = 1.000.

---

## 6. Interpretation

Spearman / Kendall concordance between Jev and Haiku, under a shared FedLock-style protocol, measures whether two different live judges produce a stable *relative-hawkishness* ordering on this openings sample. Concordance with published FedLock `m` / `ma` asks whether that same protocol family, applied to chair openings rather than FedLock’s broader speech corpus and Llama 3.3 70B judge, recovers a similar ordering of meeting-day stance.

Agreement with raw `m` is tighter than with era-adjusted `ma` on both live arms (Jev ↔ `m` Spearman +0.965 versus Jev ↔ `ma` +0.790; Haiku ↔ `m` +0.945 versus Haiku ↔ `ma` +0.768). Era-adjusted `ma` removes quarterly means. Disagreement between the `m` and `ma` contrasts therefore partly reflects the era composition of the 2011–2026 openings window, not a second independent sample.

Cost and latency columns are accounting facts at the listed prices above. They are not accuracy claims and are not a gate.

This replica does not replace Gate 7. Gate 7 remains the main bench’s rank agreement with published FedLock scores under Bradley–Terry / Score. See [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md) and ANALYSIS §6.

---

## 7. Limitations

- **Scale.** FedLock reports ~60,000 comparisons on ~4,000 speeches. This run uses 95 openings and a 2,850-comparison cap. Convergence to σ < 2 for every document is not guaranteed at this scale; it happened to occur here (max σ = 1.986 on Jev, 1.965 on Haiku).
- **Document mismatch.** Openings are a subset of press-conference communication. FedLock `press_conference` scores may reflect fuller presser text.
- **Judge stack.** FedLock’s published scores use Llama 3.3 70B. This replica uses Jev and Haiku. Agreement with `m` / `ma` therefore mixes protocol fidelity with model differences.
- **Soft TrueSkill.** Confidence-weighted updates via outcome interpolation are an approximation to FedLock’s documented “updates by judge confidence,” not a bit-exact reimplementation of an unpublished kernel.
- **Macro vintage.** FRED series are taken as-of the speech date from the local dump (plus downloaded VIXCLS / GDPC1). Real-time vintages differ from revised series.

---

## 8. Artifacts

- `results/fedlock_replica/trueskill_{jev,haiku}.csv`
- `results/fedlock_replica/comparisons_{jev,haiku}.jsonl`
- `results/fedlock_replica/cost_performance.json`
- `results/fedlock_replica/agreement.json`
- `results/fedlock_replica/fedlock_matches.json`
- `results/fedlock_replica/macro_asof.json`
- `results/figures/fedlock_replica_*.png` when the replica plotting path is run (copied to `docs/figures/`)
