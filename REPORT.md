# fedjev-bench — pre-registered gates

**run_id:** `fedjev-2026-09-20`  
**model:** jev-1.13.0  
**list price (this run):** $0.042 / Mtok input; output free  
**artifacts:** `results/gates.json` · `results/interpretation.json` · `results/fedlock_fidelity.md` · `results/cost.json` · `results/timing.json`

Long-form write-up and figures: [`ANALYSIS.md`](ANALYSIS.md). Scoreboard guide: [`HOW_TO_READ.md`](HOW_TO_READ.md). SVG/PNG: `results/figures/` (copied to `docs/figures/`).

## Abstract

This report records pre-registered gates for TypeSafe/Jev pairwise rankings of Federal Open Market Committee (FOMC) chair openings under the criterion `more hawkish about inflation`. The measurement questions are construct validity on easy pairs, rank agreement with same-day target-rate changes on scheduled action days, and separation of holds from cuts on the text axis—where `d_same` (the same-day funds-target change) is uninformative by construction. Gate 7 reports Spearman’s rank correlation with FedLock, an independent published text-scoring project ([methodology](https://jnathan9.github.io/fedlock/)): raw TrueSkill mean `m` and era-adjusted `ma`. Gate 7 reads those published scores. It does not re-run FedLock’s TrueSkill tournament or its macro-conditioned judge. A separate protocol-fidelity replica is `results/fedlock_replica/FINDINGS.md`. Associations include a standard error (s.e.) and, where computed, bootstrap percentile confidence intervals.

## Analysis exclusions (pre-registered)

- **Exclude from main analysis:** 2020-03-03, 2020-03-15 (unscheduled / intermeeting cuts), and any other `exclude_main` or `is_scheduled=false` rows.
- **Flag, do not drop:** 2023-03-22 (SVB) — column `flag_svb`.

## Gates (registered before any Jev output)

| # | Gate | Metric / rule | Pass line |
|---|------|---------------|-----------|
| 1 | Easy-pair inversion | Stratum A; average both presentation orders | inversion ≤ 0.05 |
| 2 | Sentence discrimination | Stratum B; inversion + Brier on p(gold) | **report only** |
| 3 | Statement score vs action | Spearman(BT score, `d_same`) scheduled excl. crisis; signal +0.30 (jsort pub. +0.46); action vs hold splits | Spearman ≥ +0.30 |
| 4 | Holds vs cuts | mean score holds (`d_same=0`) vs cuts (`d_same<0`) | mean(holds) > mean(cuts) |
| 5 | Forward path | Spearman vs `d_90` | **secondary** |
| 6 | Order/name stability | Stratum A names-in; Δ inversion | Δ ≤ 0.05 |
| 7 | FedLock consistency (published-score agreement; not a TrueSkill replication) | Spearman vs FedLock raw `m` (primary) and era-adjusted `ma` (sensitivity) | **report only** |

## Scoring protocol

- Criterion (exact): `more hawkish about inflation`
- Choice: Text A / Text B; meta stripped; both orders; inversion on averaged winner
- Secondary Score: five-level → `score_jev`
- Entry: `score.py` → `runs/jev/`; every answer logs tokens and `latency_ms`

## Results

### Gate pass/fail

| # | Gate | Result | Detail (STE where defined) |
|---|------|--------|----------------------------|
| 1 | Easy-pair inversion | **PASS** | 0.0000 (n=40, STE=0.0000) |
| 2 | Sentence discrimination | report | inv=0.1900 STE=0.0277; Brier=0.1384 STE=0.0156 (n=200) |
| 3 | Action ranking | **PASS** | BT all=+0.623 (n=46, STE=0.096) [+0.398, +0.787]; action=+0.851 (n=24, STE=0.074) [+0.652, +0.937] |
| 4 | Holds vs cuts | **PASS** | BT: holds=−0.7199 (STE=0.3345, n=22) > cuts=−1.2385 (STE=0.1528, n=8); gap=0.5186 (STE=0.3677) |
| 5 | Forward path | secondary | BT=+0.357 (n=44, STE=0.154) [+0.042, +0.627]; score_jev=+0.511 (n=91, STE=0.081) [+0.336, +0.652] |
| 6 | Order/name stability | **PASS** | Δ=0.0000; add-on $0.010955 |
| 7 | FedLock consistency (published scores; not a TrueSkill replication) | report | Bradley–Terry vs raw `m`=+0.679 (n=46, s.e.=0.112) [+0.436, +0.861]; vs era-adjusted `ma`=+0.594 (n=46, s.e.=0.104) [+0.361, +0.770]; score_jev vs `m`=+0.944 (n=90, s.e.=0.016) [+0.900, +0.966]; vs `ma`=+0.774 (n=90, s.e.=0.044) [+0.673, +0.839]; mean FedLock uncertainty `s`=1.776; matched meetings=92 |

### Inversion tables

| Stratum | n | inverted | inversion (STE) | mean p(gold) | mean Brier (STE) | order-flip |
|---------|--:|--------:|----------------:|-------------:|-----------------:|-----------:|
| A extreme | 40 | 0 | 0.0000 (0.0000) | 1.0000 | 0.0000 (0.0000) | 0.0000 |
| B Shah | 200 | 38 | 0.1900 (0.0277) | 0.7451 | 0.1384 (0.0156) | 0.1050 |
| C adjacent | 22 | 1 | 0.0455 (0.0444) | 0.8555 | 0.0459 (0.0178) | 0.0909 |

Inverted C: **C018**. Inverted A: none.

### Gate 3 detail (BT primary; bootstrap 1,000)

| Slice | Spearman ρ [STE; 95% CI] |
|-------|--------------------------|
| All scheduled (excl. crisis) | +0.623 (n=46, STE=0.096) [+0.398, +0.787] |
| action_days | +0.851 (n=24, STE=0.074) [+0.652, +0.937] |
| hold_days vs dissent net | −0.192 (n=22, STE=0.202) [−0.513, +0.274] |
| hold_days vs d_2y | −0.135 (n=22, STE=0.244) [−0.594, +0.349] |

Secondary score_jev: all=+0.589 (n=93, STE=0.063) [+0.460, +0.701]; action=+0.918 (n=30, STE=0.033) [+0.812, +0.953].

BT fit: n_statements=48, n_comparisons=124, converged=True, γ=−0.1378.

### Gate 4 holds vs cuts

| Score | mean holds (STE, n) | mean cuts (STE, n) | mean hikes (STE, n) | gap (STE) |
|-------|---------------------|--------------------|---------------------|-----------|
| BT | −0.7199 (0.3345, 22) | −1.2385 (0.1528, 8) | 1.8273 (0.5319, 16) | 0.5186 (0.3677) |
| score_jev | 1.4570 (0.1144, 63) | 1.0356 (0.1216, 9) | 3.0671 (0.1346, 21) | 0.4214 (0.1670) |

Gate 4 is a construct-validity result: same-day funds-rate changes are an incomplete label for textual hawkishness when the target is unchanged. The pre-registered pass rule is the point comparison of means. The BT gap 95 percent interval includes 0; the score_jev gap interval does not.

### FedLock fidelity (Gate 7)

See `results/fedlock_fidelity.md` for the re-implementation note. **FedLock** is an independent published tournament ([methodology](https://jnathan9.github.io/fedlock/)): Llama 3.3 70B compares anonymized speeches on hawkishness *given* contemporaneous macro conditions and aggregates with TrueSkill (Microsoft’s Bayesian skill-rating system). Gate 7 does not re-run that tournament. It asks whether this repository’s Bradley–Terry and Score series agree in rank with the published press-conference scores.

Shared with FedLock, in a limited sense: pairwise textual hawkishness as the object of measurement; name and date stripping on this repository’s Jev Choice calls; use of the published scores as an external reference. Not reproduced on the Gate 7 left-hand side: macro-conditioned prompts (core personal consumption expenditures inflation, unemployment, real gross domestic product growth, CBOE Volatility Index); TrueSkill aggregation; era-adjusted `ma` as the headline (it is a sensitivity); the full ~4,000-speech corpus; the Llama judge; Swiss / uncertainty-targeted pairing.

Matching prefers the date embedded in the FedLock title; when the match falls back to the FedLock `d` field, the offset (`d` − meeting) is +1 day on 89 of 90 main-analysis rows (1 row is offset 0). Primary contrast: raw `m`. Sensitivity: `ma`. Mean published uncertainty `s` on the matched main set = 1.7762. Matched meetings = 92; main-analysis matched = 90.

Gate 7 is agreement between two text measures. It is not a methodological replication. The separate TrueSkill replica (`run_id` `fedjev-fedlock-replica-2026-09-20`) is `results/fedlock_replica/FINDINGS.md` and ANALYSIS §12.

### Cost and timing

Main run ≈ $0.03120 (619 calls). Name ablation ≈ $0.011. Mean latency ≈ 214 ms at concurrency 6. Same-protocol Haiku Choice arm: ≈ $0.636 and ≈ 676 ms mean, versus Jev Choice ≈ $0.024 and ≈ 207 ms. Inversion rates match on Strata A and C.

### Artifacts

| Path | Role |
|------|------|
| `results/pair_judgments.jsonl` | Per gold pair, both orders averaged |
| `results/statement_scores.csv` | BT score/se/n_pairs + score_jev |
| `results/gates.json` | Gates with STE fields |
| `results/interpretation.json` | Estimator glossary and selected estimates |
| `results/fedlock_fidelity.md` | Gate 7 fidelity statement (published-score agreement; not a TrueSkill replication) |
| `results/fedlock_replica/FINDINGS.md` | Separate FedLock-faithful TrueSkill replica |
| `runs/jev/answers.jsonl` | Raw answers |


## Sensitivity (Khaled / jsort) — not a gate

Length audit and a 25-meeting passage-filter Score pilot. Frozen `run_id` unchanged; no full TrueSkill / Haiku re-run.

| Item | Result |
|------|--------|
| Openings n>8,000 chars | 39 / 95 (41.1%); mean 7,917; p50 7,547; p90 10,823; max 13,794 |
| Main run truncated at 8k? | **No** (full openings; 8k is jsort default only) |
| Pilot sample | 25 scheduled action-day openings; seed 20260920 |
| Filter | `jgrep --para "states a view on inflation or the stance of monetary policy"`; cap 8,000; `filter_empty` = 0 |
| ρ(filtered Score, `d_same`) | +0.927 (s.e.=0.029; n=25) |
| ρ(baseline Score, `d_same`) | +0.927 (s.e.=0.029; n=25) |
| Δρ vs `d_same` | +0.0002 (s.e.=0.0007) |
| ρ(filtered, FedLock `m`) | +0.955 (s.e.=0.033; n=24) |
| ρ(baseline, FedLock `m`) | +0.963 (s.e.=0.032; n=24) |
| ρ(filtered, baseline Score) | +0.991 (s.e.=0.011) |
| New Jev spend | ≈ $0.005 |

Artifacts: `results/khaled_sensitivity/` · ANALYSIS §13.



## Multi-axis extension — pre-registered gates (before looking)

**run_id:** `fedjev-multiaxis-2026-09-20` · **model:** Jev only · **protocol:** TrueSkill adaptive tournament (σ&lt;2), Choice with random presentation order (fedlock-replica style; ~1k comps / axis×design). **Not** full C(95,2). Budget target ~$2–3; hard cap $5.

**Corpus:** 95 chair openings (`data/clean/statements.jsonl`). Prepared remarks only. Q&amp;A drift **out of scope** (not vendored). Full-speech robustness: future work.

**Preprocess:** `jgrep --para` per axis (budget pinned; `--max-chars 8000`); empty-after-filter → flag + fall back to full stripped opening.

**Designs:** (1) text-only; (2) conditional (Core PCE YoY, UNRATE, GDP QoQ SAAR, VIX, NFCI).

**Frozen criteria (exact strings):**
1. more hawkish about inflation *(baseline)*
2. places more weight on employment downside than on inflation upside
3. more willing to treat a price-level shift from tariffs, energy, or supply as transitory and look through it
4. more explicit about the likely future path of policy; less purely data-dependent
5. more eager to shrink the balance sheet and less worried that QT will impair reserves or market function
6. more concerned that financial conditions are not restrictive enough, rather than worried they will overshoot
7. sees upside inflation risks as larger than downside labor-market risks

| Gate | Metric | Pass / report |
|------|--------|---------------|
| M1 | Spearman(μ, `d_same`) on scheduled action days (excl. crisis) | pass if ρ ≥ +0.30 (with s.e. + bootstrap CI) |
| M2 | Hold vs cut mean-μ gap | pass if mean(holds) &gt; mean(cuts) |
| M3 | Spearman vs same-day 2y move (`d_2y` / DGS2 day change); USD / NFCI if available | report; document if missing |
| M4 | Next-meeting SEP medians | skip with note if not vendored |
| M5 | QT pace / BS label (axis 5) | report if available; else note |
| M6 | FedLock `m` agreement | **axis 1 only** (secondary) |
| M7 | Factor / redundancy | report: is axis 1 PC1? any economically meaningful PC2? near-duplicates (|ρ|≥0.90) to drop? |
| M8 | Alternative vs axis 1 | fail-as-redundant if alt gate ρ statistically indistinguishable from axis 1 *and* |rank corr|≥0.90 |

Scores kept raw and era-adjusted (subtract quarterly mean, re-center). Results: `results/multiaxis/`.

### Multi-axis results (after looking)

**Spend:** ≈ $1.53 · **comps/axis×design:** ~987–1,200 · **PC1:** axis 1 both designs (50.6% text / 55.5% conditional) · **PC2:** ~17–20% (guidance/FCI; look-through vs FCI) · **drop as near-dup:** axis 7 (and axis 2 under conditional as mirror) · **order-swap flip rate:** 0.0 (n=30). Full tables: [`results/multiaxis/FINDINGS.md`](results/multiaxis/FINDINGS.md).



## Interpretation (brief)

Gates 1, 3, 4, and 6 pass under the pre-registered rules. Action-day Bradley–Terry Spearman exceeds the jsort +0.46 published point estimate. Gate 4 documents incomplete behavioral labeling under holds (`d_same` is zero when the target is unchanged). Gate 7 shows rank agreement with an independent FedLock text score — especially Score versus raw `m` (ρ = +0.944, s.e. = 0.016, n = 90) — and is not a FedLock replication. The TrueSkill replica is a different experiment.

Limitations: sparse BT graph; incomplete dissent scrape; openings are not full pressers; Gate 4 BT gap interval includes zero. Experiments 3–7 (composite Scores, multi-label Nouls, calibration, span Choice, macro-relative scoring) are reserved; `results/experiments/` is not in this repository. Figures in `ANALYSIS.md` plot only series that exist in `results/` and `data/`.
