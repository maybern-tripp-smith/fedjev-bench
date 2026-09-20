# fedjev-bench — Analysis

**run_id:** `fedjev-2026-09-20`  
**model:** jev-1.13.0 (TypeSafe SystemOne)  
**criterion (exact):** `more hawkish about inflation`  
**repository:** [maybern-tripp-smith/fedjev-bench](https://github.com/maybern-tripp-smith/fedjev-bench)  
**pages:** [https://maybern-tripp-smith.github.io/fedjev-bench/](https://maybern-tripp-smith.github.io/fedjev-bench/)

Companion gate report: [`REPORT.md`](REPORT.md). Machine-readable results: [`results/gates.json`](results/gates.json). Number semantics: [`results/interpretation.json`](results/interpretation.json). FedLock relationship: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

---

## Abstract

Same-day changes in the federal funds target are a convenient but incomplete label for the hawkishness of Federal Open Market Committee (FOMC) communication. Policy actions and textual stance often co-move on scheduled action days, yet need not coincide when the Committee holds the target rate. This repository reports a pre-registered evaluation of TypeSafe/Jev on chair press-conference openings: pairwise Choice under the fixed criterion string `more hawkish about inflation` (both presentation orders), Bradley–Terry (BT) aggregation, and a secondary direct Score pass. Seven gates probe construct validity (easy-pair discrimination), rank agreement with same-day rate moves, separation of holds from cuts on the text axis, forward-path correlation, order/name stability, and external consistency with FedLock press-conference scores. Primary quantities are reported with standard errors (STE) and, where applicable, bootstrap percentile confidence intervals. Gate 4 is interpreted as evidence that same-day funds-rate changes are an incomplete label for textual hawkishness under holds—not as a claim that text “overrides” policy.

## Contributions

1. A frozen three-stratum gold set (extreme document pairs, Shah hawk/dove sentences, adjacent scheduled meetings) with pre-registered pass lines.
2. Dual-order Choice protocol with meta stripping, BT scores with fit SEs, and first-class cost/latency artifacts.
3. An honest Gate 7: Spearman agreement with FedLock raw (`m`) and era-adjusted (`ma`) scores, with an explicit fidelity statement of what is and is not reproduced.
4. Uncertainty reporting (bootstrap STE for Spearman; binomial STE for inversion rates; STE for means/Brier and Gate 4 gaps).
5. A head-to-head Choice comparison with Claude Haiku 4.5 under the same pairs and criterion (winner agreement primary; dollars and latency separate axes).

---

## 1. Introduction

Empirical work on FOMC language often treats the realized same-day target-rate change (`d_same`) as a behavioral proxy for how hawkish a communication “was.” That proxy conflates two constructs:

1. **Behavioral / policy measure** — the Committee’s voted action (hike, hold, cut; dissents).
2. **Textual measure** — the stance expressed in the Chair’s opening remarks about inflation, the labor market, and the policy path.

On scheduled action days the two frequently align. On holds (`d_same = 0`), and across regimes (e.g., 2020 easing communications versus 2022–23 holds with hawkish inflation language), alignment is not guaranteed. The evaluation question studied here is therefore:

> Under a fixed pairwise criterion, does a text-ranking model recover (i) obvious hawk-versus-dove document orderings, (ii) rank agreement with `d_same` on scheduled action days, and (iii) a text-score ordering in which holds sit above cuts—indicating that same-day rate changes are an incomplete label for textual hawkishness when the target is unchanged?

Gates were registered before any Jev output. Pass/fail applies to Gates 1, 3, 4, and 6; Gates 2, 5, and 7 are report-only or secondary.

---

## 2. Related work

| Work | Contribution | Use in this bench |
|------|--------------|-------------------|
| **jsort** ([keltokhy/jsort](https://github.com/keltokhy/jsort)) | Statement ranking; published Spearman vs same-day move ≈ **+0.46** | Label formulas (`d_same`, `d_90`, `d_2y`); Gate 3 signal (+0.30) and published reference (+0.46) |
| **Shah et al.** ([gtfintechlab/fomc-hawkish-dovish](https://github.com/gtfintechlab/fomc-hawkish-dovish); CC BY-NC 4.0) | Sentence-level hawk/dove/neutral labels | Stratum B; Gate 2 report-only |
| **FedLock** ([jnathan9.github.io/fedlock](https://jnathan9.github.io/fedlock/)) | Independent LLM pairwise + TrueSkill hawkishness scores | Gate 7 external consistency (report-only); see §6 |

---

## 3. Data

| Corpus | Path | Role |
|--------|------|------|
| Chair presser openings | `data/clean/statements.jsonl` (~95 docs) | Document-level Choice + Score |
| Shah sentences | `data/clean/sentences.jsonl` | Stratum B |
| Meeting calendar + FRED labels | `data/labels/meetings.parquet` | `d_same`, `d_90`, `d_2y`, dissent counts, exclusions |
| FedLock snapshot | `data/raw/fedlock/data.json` | Gate 7 (`m`, `ma`, `s`, `st`) |
| FRED CSVs | `data/raw/fred/` | DFEDTARU, DGS2 |

**Labels (jsort-aligned):** `d_same` = DFEDTARU[t+1] − DFEDTARU[t−1]; `y_action` = sign(`d_same`); `d_90` = DFEDTARU[t+90] − DFEDTARU[t]; `d_2y` = DGS2[t] − DGS2[t−1].

**Exclusions (pre-registered):** drop 2020-03-03 and 2020-03-15 (unscheduled) and other `exclude_main` / unscheduled rows from main analysis; flag 2023-03-22 (SVB) without dropping.

**Gold strata (frozen):** A extreme n=40; B Shah n=200 (seed 20260920); C adjacent n=22. Manifest: `data/pairs/PAIR_MANIFEST.md`.

---

## 4. Method

**Choice (primary).** Criterion: `more hawkish about inflation`. Both orders `ab`/`ba`; probabilities mapped to gold sides and averaged. Inversion = averaged winner ≠ gold. Meta stripping via `scripts/strip_meta.py`.

**Score (secondary).** Five-level ordinal → continuous `score_jev`.

**Bradley–Terry.** Strata A+C Choice probabilities (Shah excluded). This run: n_statements=**48**, n_comparisons=**124**, converged=True, position bias γ=**-0.1378**. Graph is sparse; BT `se` in `statement_scores.csv` is fit uncertainty, not meeting-sampling STE.

**Uncertainty.** Spearman: bootstrap STE (SD of 1000 meeting resamples) + percentile 95% CI. Inversion: binomial STE √[p(1−p)/n]. Brier / Gate 4 means: STE = sd/√n; Gate 4 gap STE = √(ste_h² + ste_c²).

---

## 5. Pre-registered gates and results

| # | Gate | Pass line | Result |
|---|------|-----------|--------|
| 1 | Easy-pair inversion (A) | ≤ 0.05 | **PASS** — rate=0.0000 (n=40, STE=0.0000) |
| 2 | Sentence discrimination (B) | report | inv=0.1900 STE=0.0277; Brier=0.1384 STE=0.0156 (n=200) |
| 3 | Action ranking | Spearman ≥ +0.30 | **PASS** — BT all=+0.623 (n=46, STE=0.096) [+0.398, +0.787]; action=+0.851 (n=24, STE=0.074) [+0.652, +0.937] |
| 4 | Holds vs cuts | mean(holds) > mean(cuts) | **PASS** — BT gap=+0.519 STE=0.368 (n_h=22, n_c=8) |
| 5 | Forward path (`d_90`) | secondary | BT=+0.357 (n=44, STE=0.154) [+0.042, +0.627]; score_jev=+0.511 (n=91, STE=0.081) [+0.336, +0.652] |
| 6 | Order/name stability | Δ inv ≤ 0.05 | **PASS** — Δ=0.0000 |
| 7 | FedLock consistency | report | BT vs m=+0.679 (n=46, STE=0.112) [+0.436, +0.861]; vs ma=+0.594 (n=46, STE=0.104) [+0.361, +0.770]; score_jev vs m=+0.944 (n=90, STE=0.016) [+0.900, +0.966]; vs ma=+0.774 (n=90, STE=0.044) [+0.673, +0.839] |

### 5.1 Inversion by stratum

| Stratum | n | inverted | inversion (STE) | mean p(gold) | mean Brier (STE) | order-flip |
|---------|--:|--------:|----------------:|-------------:|-----------------:|-----------:|
| A extreme | 40 | 0 | 0.000 (0.000) | 1.000 | 0.000 (0.000) | 0.000 |
| B Shah | 200 | 38 | 0.190 (0.028) | 0.745 | 0.138 (0.016) | 0.105 |
| C adjacent | 22 | 1 | 0.045 (0.044) | 0.855 | 0.046 (0.018) | 0.091 |

Stratum A: no inversions. Stratum C inverted pair: **C018**. Gate 2 (19% inversion) is a sentence-level stress test, not a pass/fail of the document-level claim.

### 5.2 Gate 3 — rank agreement with policy actions

| Slice | BT Spearman ρ [STE; 95% CI] | n |
|-------|------------------------------|--:|
| All scheduled (excl crisis) | +0.623 (n=46, STE=0.096) [+0.398, +0.787] | 46 |
| action_days (`d_same`≠0) | +0.851 (n=24, STE=0.074) [+0.652, +0.937] | 24 |
| hold_days vs (n_hawk−n_dove) | -0.192 (n=22, STE=0.202) [-0.513, +0.274] | 22 |
| hold_days vs `d_2y` | -0.135 (n=22, STE=0.244) [-0.594, +0.349] | 22 |

Secondary `score_jev`: all=+0.589 (n=93, STE=0.063) [+0.460, +0.701]; action=+0.918 (n=30, STE=0.033) [+0.812, +0.953].

Action-day ρ exceeds all-scheduled ρ because holds contribute no variation in `d_same` (identically zero); Spearman versus `d_same` on holds alone is therefore undefined and not computed. Hold-day associations with dissent net and `d_2y` remain weak—consistent with holds mixing hawkish- and dovish-hold communications.

jsort published reference: Spearman ≈ +0.46 (STE not re-estimated here). BT action-day ρ=+0.851 (STE=0.074) clears both the +0.30 signal line and that reference point estimate.

### 5.3 Gate 4 — holds versus cuts on the text axis

| Score | mean holds (STE, n) | mean cuts (STE, n) | mean hikes (STE, n) | gap holds−cuts (STE) |
|-------|---------------------|--------------------|---------------------|----------------------|
| BT | -0.720 (0.335, 22) | -1.239 (0.153, 8) | 1.827 (0.532, 16) | +0.519 (0.368) |
| score_jev | 1.457 (0.114, 63) | 1.036 (0.122, 9) | 3.067 (0.135, 21) | +0.421 (0.167) |

**Interpretation.** Under holds, `d_same` is identically zero and therefore cannot encode hawkish- versus dovish-hold communications. A higher mean text score on holds than on cuts indicates that the textual measure separates these regimes where the same-day behavioral label cannot. This is evidence of incomplete labeling of textual hawkishness by funds-rate changes under holds; it is not a normative claim about policy correctness. Note the BT gap 95% CI includes zero ([-0.202, +1.239]); the `score_jev` gap CI does not ([+0.094, +0.749]). Pre-registered pass is the point comparison mean(holds) > mean(cuts).

### 5.4 Gate 6 — name ablation

Baseline inversion (stripped) = 0.0000; names-in = 0.0000; Δ = 0.0000 ≤ 0.05 → **PASS**. Add-on cost $0.010955 (80 calls). Caveat: openings rarely embed strip-able Chair names/ISO dates; Δ=0 informs order stability more than name confounding.

---

## 6. Relationship to FedLock (fidelity)

Full note: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

FedLock V3 ([methodology](https://jnathan9.github.io/fedlock/)): pairwise tournament with Llama 3.3 70B on anonymized speeches; macro context (Core PCE, unemployment, GDP growth, VIX) in the judge prompt; TrueSkill (μ₀=50, σ₀≈8.33 → σ<2); ~60k comparisons / ~4k speeches; fields `m` (raw μ), `ma` (era-adjusted), `s` (σ), `n`, `st`.

**Faithfully shared:** pairwise text hawkishness as a construct; name/meta stripping on *our* Jev Choice calls; use of FedLock `press_conference` scores as an external consistency check.

**Not reproduced:** macro-conditioned judge prompts; TrueSkill; era adjustment as Gate 7 primary (we report `ma` as sensitivity); full speech corpus; Llama judge; Swiss / uncertainty-targeted matching.

**Implication:** Gate 7 ρ measures agreement between two independent text-scoring systems on meeting-day hawkishness. It does not constitute a FedLock replication.

**Matching:** prefer title-embedded meeting date; else FedLock `d` with deltas 0, +1, −1, +2. Matched meetings=92; main-analysis matched=90; same-calendar-day on `d` field=1; delta distribution={'0': 1, '1': 89}; match-via={'title_date': 90}; mean FedLock `s` on matched=1.7762.

| Contrast | ρ | STE | n | 95% CI |
|----------|--:|----:|--:|--------|
| BT vs `m` | +0.679 | 0.112 | 46 | [+0.436, +0.861] |
| BT vs `ma` | +0.594 | 0.104 | 46 | [+0.361, +0.770] |
| score_jev vs `m` | +0.944 | 0.016 | 90 | [+0.900, +0.966] |
| score_jev vs `ma` | +0.774 | 0.044 | 90 | [+0.673, +0.839] |

Agreement with raw `m` is stronger than with era-adjusted `ma`, especially for `score_jev`. Corpus mismatch: chair openings ≠ necessarily full FedLock presser transcripts.

---

## 7. How to read these numbers

| Quantity | Meaning here |
|----------|----------------|
| Spearman ρ vs `d_same` | Rank agreement between meeting-level text hawkishness and same-day target move |
| Why action-day ρ > all-scheduled | Holds add no `d_same` variation; they dilute the pooled correlation |
| Hold-day ρ vs `d_same` | Undefined / not computed (`d_same` constant 0) |
| Gate 4 gap | Mean text score(holds) − mean text score(cuts): holds look less dovish than cuts on the text axis |
| Inversion 0 on Stratum A | Easy document pairs: averaged two-order winner matched gold. Does not imply hard-pair calibration or policy forecasting |
| BT `se` | Uncertainty from the pairwise BT likelihood, not bootstrap over meetings |
| Haiku vs Jev | Winner agreement (inversion) is primary; USD and latency_ms are separate axes. Latency is per-call API time; wall clock is concurrent |
| STE | Standard error as defined above for each estimator family |

---

## 8. Cost and latency

Pricing (jev-1.13.0): **$0.042 / Mtok input**; output free. Main run ≈ **$0.03120** (619 calls; 524 Choice + 95 Score). Name ablation add-on ≈ $0.011. Grand total ≈ **$0.042**. Mean per-call latency ≈ 214 ms (concurrency 6); wall ≈ sum/6 if perfect parallel (~22 s). See `results/cost.json`, `results/timing.json`.

### Haiku 4.5 comparison (Choice only)

| | Jev 1.13.0 | Haiku 4.5 |
|--|------------|-----------|
| Stratum A / C inversion | 0.000 / 0.045 | 0.000 / 0.045 |
| Stratum B inversion | 0.190 | 0.170 |
| Choice USD | ≈ $0.024 | ≈ $0.636 (~27×) |
| Mean latency | ≈ 207 ms | ≈ 676 ms (~3.3×) |

Winner agreement nearly ties on A/C; Haiku is slightly lower-inversion on Shah with higher order-flip. Economics and latency favor Jev on this protocol; accuracy is not a large differentiator.

---

## 9. Discussion

**Construct validity (Gate 1).** Zero inversion on Stratum A indicates that, under the fixed criterion and dual-order protocol, Jev recovers obvious hawk-versus-dove document orderings.

**Behavioral alignment on action days (Gate 3).** BT ranks track `d_same` on scheduled action days at levels that exceed the pre-registered +0.30 signal and the jsort +0.46 published point reference, with bootstrap CIs excluding zero.

**Incomplete behavioral labels under holds (Gate 4).** When the target is unchanged, `d_same` cannot distinguish hawkish-hold from dovish-hold text. Higher mean text scores on holds than on cuts are therefore informative about the textual construct precisely where the behavioral label is uninformative. This supports treating same-day funds-rate changes as an incomplete label for textual hawkishness under holds—not as a rhetorical “disagreement” between model and market.

**External textual consistency (Gate 7).** Independent FedLock scores agree with Jev, especially the Score pass versus raw `m`. Combined with the fidelity statement in §6, this supports a shared text signal rather than FedLock replication.

**Efficiency.** Relative to Haiku 4.5 on the same Choice protocol, Jev offers comparable winner agreement at substantially lower listed cost and latency.

**Limitations.** Sparse BT graph (n=48 statements / 124 comparisons); incomplete dissent scrape; openings ≠ full pressers; single criterion and model version; Gate 4 BT gap CI includes zero; experiments on composite scores, multi-label judgments, calibration, span Choice, and macro-relative scoring are reserved for follow-on work (see §11).

---

## 10. Reproducibility

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install typesafe-sdk pandas pyarrow openpyxl scipy matplotlib
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
```

Frozen inputs: `data/pairs/gold_pairs.jsonl`, `data/clean/`, `data/labels/`. Outputs: `results/`, `runs/jev/`.

---

## 11. Reserved: follow-on experiments (3–7)

*Findings to be appended by a separate worker. Do not delete existing gates or results.*

| # | Experiment | Status |
|---|------------|--------|
| 3 | Composite Scores | pending |
| 4 | Multi-label Nouls | pending |
| 5 | Calibration | pending |
| 6 | Span Choice | pending |
| 7 | Macro-relative scoring | pending |

---

## 12. Ethics and licenses

| Asset | Status |
|-------|--------|
| Code | MIT |
| FOMC openings | U.S. government works; cite federalreserve.gov; no Fed endorsement |
| FRED | St. Louis Fed terms |
| Shah | CC BY-NC 4.0 — attribution; non-commercial; full dump not vendored |
| jsort | MIT |
| FedLock | Upstream site terms; snapshot for Gate 7 only |

Research instrumentation only; not investment advice.

## Citation

See [`CITATION`](CITATION).
