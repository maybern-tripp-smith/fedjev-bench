# fedjev-bench REPORT — pre-registered gates

**run_id:** `fedjev-2026-09-20`  
**phase:** Jev half complete — results filled  
**model:** jev-1.13.0  
**pricing:** $0.042 / Mtok input; output free  
**cost log:** `results/cost.json` · timing: `results/timing.json`

## Thesis

Rate changes label *policy*. Jev labels *text*. Gate 1 says whether Jev can see an obvious hawk vs dove document. Gate 3 says whether that text ranking tracks the decision on scheduled days. Gate 4 is the important disagreement: if Jev ranks 2023 holds and 2026 hawkish-hold-with-dissents above 2020 cuts while d_same=0, the model is reading tone and the rate series is the wrong sole GT. That is the result, not a bug to paper over.

## Analysis exclusions (pre-registered)

- **Exclude from main analysis:** 2020-03-03, 2020-03-15 (unscheduled / intermeeting cuts), and any other intermeeting moves (`exclude_main` / `is_scheduled=false`).
- **Flag, do not drop:** 2023-03-22 (SVB) — column `flag_svb`.

## Gates (registered before any Jev output)

| # | Gate | Metric / rule | Pass line |
|---|------|---------------|-----------|
| 1 | Easy-pair inversion | Stratum A; average both presentation orders | inversion ≤ 0.05 |
| 2 | Sentence discrimination | Stratum B; inversion + Brier on p(gold) | **report only** |
| 3 | Statement score vs action | Spearman(Jev statement score, `d_same`) on scheduled meetings, crisis excluded; signal line +0.30 (jsort published +0.46). Split `action_days` vs `hold_days`; on holds correlate with `(n_hawk_dissent − n_dove_dissent)` and `d_2y` instead | Spearman ≥ +0.30 on action/all scheduled (signal) |
| 4 | Holds vs cuts | Mean score on holds (`d_same=0`) vs mean score on cuts (`d_same<0`) | mean(holds) > mean(cuts) |
| 5 | Forward path | Spearman vs `d_90` | **secondary** |
| 6 | Order/name stability | Stratum A with names in + order flip; inversion delta | Δ inversion ≤ 0.05 |
| 7 | FedLock consistency | Spearman vs FedLock hawkishness scores (`data/raw/fedlock/`) | **report only** |

## Scoring protocol

- Criterion string (exact): `more hawkish about inflation`
- Choice: Text A / Text B (meta stripped via `scripts/strip_meta.py`); options A/B; both orders
- Secondary Score levels: much more dovish / somewhat dovish / neutral / somewhat hawkish / much more hawkish
- Entry: `score.py` → `runs/jev/`
- **Every answer logged** `usage.input_tokens`, `usage.output_tokens`, `latency_ms`; roll up to `results/cost.json` at $0.042/Mtok input

## Results

### Verdict

Gate 1 PASSES (Stratum A inversion=0.000). Gate 3 CLEARS the +0.30 signal (BT Spearman vs d_same all-scheduled=+0.623 (n=46) [+0.398, +0.787], action_days=+0.851 (n=24) [+0.652, +0.937]; score_jev secondary all=+0.589 (n=93) [+0.460, +0.701]). Gate 4 holds > cuts on BT: mean(holds)=-0.7199 (n=22) vs mean(cuts)=-1.2385 (n=8), gap=0.5186. Gate 6 PASSES (names-in Δ inversion=0.000).

### Gate pass/fail

| # | Gate | Result | Detail |
|---|------|--------|--------|
| 1 | Easy-pair inversion | **PASS** | rate=0.0000 (n=40, inverted=0) |
| 2 | Sentence discrimination | report | inv=0.1900, Brier=0.1384, p(gold)=0.7451 (n=200) |
| 3 | Action ranking | **PASS** | BT all=+0.623 (n=46) [+0.398, +0.787]; action=+0.851 (n=24) [+0.652, +0.937] |
| 4 | Holds vs cuts | **PASS** | BT: holds=-0.7199 (n=22) > cuts=-1.2385 (n=8)? gap=0.5186 |
| 5 | Forward path | secondary | BT vs d_90=+0.357 (n=44) [+0.042, +0.627]; score_jev=+0.511 (n=91) [+0.336, +0.652] |
| 6 | Order/name stability | **PASS** | names-in inv=0.0000; baseline=0.0000; Δ=0.0000 (n=40); order-flip=0.0000; add-on $0.010955 |
| 7 | FedLock consistency | report | BT=+0.685 (n=46) [+0.443, +0.863]; score_jev=+0.946 (n=90) [+0.900, +0.967]; matched meetings=92 |

### Inversion tables (both orders averaged → original A/B)

| Stratum | source | n | inverted | inversion rate | mean p(gold) | mean Brier | order-flip rate |
|---------|--------|--:|--------:|---------------:|-------------:|-------------:|----------------:|
| A easy | extreme | 40 | 0 | 0.0000 | 1.0000 | 0.0000 | 0.0000 |
| B Shah | shah | 200 | 38 | 0.1900 | 0.7451 | 0.1384 | 0.1050 |
| C adjacent | adjacent | 22 | 1 | 0.0455 | 0.8555 | 0.0459 | 0.0909 |

**Inverted Stratum A pairs:** none

**Inverted Stratum C pairs:** C018

### Gate 3 detail (BT primary; bootstrap 1000 meetings)

| Slice | Spearman ρ [95% CI] |
|-------|---------------------|
| All scheduled (excl crisis) | +0.623 (n=46) [+0.398, +0.787] |
| All scheduled excl SVB 2023-03-22 | +0.623 (n=46) [+0.398, +0.787] |
| action_days (d_same≠0) | +0.851 (n=24) [+0.652, +0.937] |
| action_days excl SVB | +0.851 (n=24) [+0.652, +0.937] |
| hold_days vs (n_hawk−n_dove) dissent | -0.192 (n=22) [-0.513, +0.274] |
| hold_days vs d_2y | -0.135 (n=22) [-0.594, +0.349] |
| holds vs dissent excl SVB | -0.192 (n=22) [-0.513, +0.274] |
| holds vs d_2y excl SVB | -0.135 (n=22) [-0.594, +0.349] |

Secondary Score-pass (`score_jev`): all=+0.589 (n=93) [+0.460, +0.701]; action=+0.918 (n=30) [+0.812, +0.953]; holds vs dissent=-0.064 (n=63) [-0.290, +0.175]; holds vs d_2y=+0.071 (n=63) [-0.199, +0.330].

BT fit: n_statements=48, n_comparisons=124 (strata A+C Choice probs; Shah excluded), converged=True, γ(position)=-0.1378.

### Gate 4 holds vs cuts

| Score | mean holds (n) | mean cuts (n) | mean hikes (n) | gap (holds−cuts) |
|-------|----------------|---------------|----------------|------------------|
| BT | -0.7199 (22) | -1.2385 (8) | 1.8273 (16) | 0.5186 |
| score_jev | 1.4570 (63) | 1.0356 (9) | 3.0671 (21) | 0.4214 |


### Gate 6 name ablation (Stratum A, raw_text / names left in)

| | |
|--|--:|
| Baseline inversion (stripped) | 0.0000 |
| Names-in inversion | 0.0000 |
| Δ inversion | 0.0000 |
| Pass line | ≤ 0.05 |
| Result | **PASS** |
| n pairs / calls | 40 / 80 |
| Order-flip rate | 0.0000 |
| Add-on input tokens | 260,824 |
| Add-on USD | $0.010955 |
| Cache key suffix | `names=1` |
| Answers log | `runs/jev/answers_names.jsonl` |
| Judgments | `results/pair_judgments_names.jsonl` |

Main analysis still uses meta-stripped text. Name ablation re-ran Stratum A Choice both orders with `raw_text` unstripped; cache keys include `|names=1` to avoid colliding with stripped cache. Note: presser openings rarely embed Chair names/dates, so strip_meta changes are small for most Stratum A docs — the ablation still verifies order stability under the unstripped presentation.

### Cost

| | |
|--|--:|
| Total USD | $0.031204 |
| Input tokens | 742,941 |
| Output tokens | 18,049 (free) |
| n_calls (cache-backed) | 619 |
| n_choice / n_score | 524 / 95 |
| USD / gold pair | $0.000119 |
| Name ablation add-on | $0.010955 (80 calls) |
| Grand total (main+ablation) | $0.042158 |

By stratum: extreme $0.01096; shah $0.00675; adjacent $0.00605; score_docs $0.00744.

### Timing

Concurrency: **6** (`score.py` ThreadPoolExecutor). Full-run wall clock was not separately logged; figures below are per-call `latency_ms` from `runs/jev/answers.jsonl` (deduped to one record per logical call).

| Scope | n | mean ms | p50 | p95 | max | sum ms |
|-------|--:|--------:|----:|----:|----:|-------:|
| Overall | 619 | 214.1 | 202.0 | 321.3 | 644 | 132550 |
| Choice | 524 | 207.3 | 196.0 | 304.2 | 644 | 108628 |
| Score | 95 | 251.8 | 237.0 | 356.1 | 452 | 23922 |
| extreme | 80 | 263.8 | 241.0 | 455.2 | 644 | 21103 |
| shah | 400 | 191.7 | 187.0 | 256.0 | 383 | 76679 |
| adjacent | 44 | 246.5 | 245.5 | 324.9 | 351 | 10846 |
| score_docs | 95 | 251.8 | 237.0 | 356.1 | 452 | 23922 |

Approx wall if perfect parallel (sum/6): **22091 ms** (~22.1s).

### Artifacts

| Path | Role |
|------|------|
| `results/pair_judgments.jsonl` | Per gold pair, both orders averaged, Brier on p(gold) |
| `results/statement_scores.csv` | BT `score`/`se`/`n_pairs` + `score_jev` |
| `results/gates.json` | Machine-readable gate results |
| `results/cost.json` | Token/USD rollup |
| `results/timing.json` | Latency summary |
| `runs/jev/answers.jsonl` | Raw Jev answers |


## Comparison: Haiku 4.5

**Comparison arm only** — primary gate pass/fail remains Jev. Same 262 gold pairs × both orders (524 Choice calls), criterion `more hawkish about inflation`, meta stripped via `scripts/strip_meta.py`.

| Metric | Jev 1.13.0 | Haiku 4.5 (`claude-haiku-4-5-20251001`) | Ratio H/J |
|--------|-----------:|----------------------------------------:|----------:|
| Gate 1 inv (extreme) | 0.0000 (0/40) | 0.0000 (0/40) | — |
| Gate 2 inv (shah) | 0.1900 (38/200) | 0.1700 (34/200) | — |
| Gate 2 mean Brier | 0.1384 | 0.1437 | 1.04× |
| Gate 2 mean p(gold) | 0.7452 | 0.6886 | — |
| Adjacent inv | 0.0455 (1/22) | 0.0455 (1/22) | — |
| Adjacent mean Brier | 0.0460 | 0.1089 | 2.37× |
| Choice $ total | $0.0238 | $0.6363 | **26.8×** |
| Latency p50 (ms) | 196 | 621 | **3.17×** |
| Latency mean (ms) | 207 | 676 | **3.26×** |
| Latency p95 (ms) | 304 | 938 | 3.08× |
| Wall time (Choice) | ~18.1s (sum/6) | ~49.1s (cache mtime span) | ~2.7× |

**Pricing used:** Haiku 4.5 $1/MTok in + $5/MTok out → 500,252 in + 27,208 out = **$0.636292**. Jev Choice-only stratum sum ≈ **$0.023766** (full Jev run incl. Score: $0.031204).

**Probabilities:** Haiku returned calibrated soft `p_A`/`p_B` (sum≈1) on all 524 calls — Brier is comparable to Jev's distributional scores (not one-hot fallback).

**Order flips:** Haiku shah order-flip 0.24 vs Jev 0.105 (higher instability under A/B swap).

**Artifacts:** `runs/haiku/answers.jsonl`, `runs/haiku/cache/`, `results/haiku_pair_judgments.jsonl`, `results/haiku_comparison.json`, `results/haiku_cost.json`, `results/haiku_timing.json`.

**Takeaway:** Accuracy nearly ties Jev on easy/adjacent and is slightly better on Shah inversion; Haiku is ~27× more expensive per Choice dollar and ~3× slower per call.
