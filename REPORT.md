# fedjev-bench REPORT — pre-registered gates

**run_id:** `fedjev-2026-09-20`  
**phase:** Jev half complete — results filled  
**model:** jev-1.13.0  
**pricing:** $0.042 / Mtok input; output free  
**artifacts:** `results/gates.json` · `results/interpretation.json` · `results/fedlock_fidelity.md` · `results/cost.json` · `results/timing.json`

## Abstract

This report summarizes pre-registered gates evaluating TypeSafe/Jev pairwise rankings of FOMC chair openings under the criterion `more hawkish about inflation`. The measurement question is whether a textual hawkishness score exhibits construct validity on easy pairs, rank agreement with same-day target-rate changes on scheduled action days, and separation of holds from cuts on the text axis—where same-day funds-rate changes are necessarily uninformative. Gate 7 reports external consistency with FedLock without claiming replication. All headline associations include STE (and CIs where applicable).

## Analysis exclusions (pre-registered)

- **Exclude from main analysis:** 2020-03-03, 2020-03-15 (unscheduled / intermeeting cuts), and any other `exclude_main` / `is_scheduled=false` rows.
- **Flag, do not drop:** 2023-03-22 (SVB) — column `flag_svb`.

## Gates (registered before any Jev output)

| # | Gate | Metric / rule | Pass line |
|---|------|---------------|-----------|
| 1 | Easy-pair inversion | Stratum A; average both presentation orders | inversion ≤ 0.05 |
| 2 | Sentence discrimination | Stratum B; inversion + Brier on p(gold) | **report only** |
| 3 | Statement score vs action | Spearman(BT score, `d_same`) scheduled excl crisis; signal +0.30 (jsort pub. +0.46); action vs hold splits | Spearman ≥ +0.30 |
| 4 | Holds vs cuts | mean score holds (`d_same=0`) vs cuts (`d_same<0`) | mean(holds) > mean(cuts) |
| 5 | Forward path | Spearman vs `d_90` | **secondary** |
| 6 | Order/name stability | Stratum A names-in; Δ inversion | Δ ≤ 0.05 |
| 7 | FedLock consistency | Spearman vs FedLock `m` / `ma` | **report only** |

## Scoring protocol

- Criterion (exact): `more hawkish about inflation`
- Choice: Text A / Text B; meta stripped; both orders; inversion on averaged winner
- Secondary Score: five-level → `score_jev`
- Entry: `score.py` → `runs/jev/`; every answer logs tokens + `latency_ms`

## Results

### Gate pass/fail

| # | Gate | Result | Detail (with STE where defined) |
|---|------|--------|----------------------------------|
| 1 | Easy-pair inversion | **PASS** | 0.0000 (n=40, STE=0.0000) |
| 2 | Sentence discrimination | report | inv=0.1900 STE=0.0277; Brier=0.1384 STE=0.0156 (n=200) |
| 3 | Action ranking | **PASS** | BT all=+0.623 (n=46, STE=0.096) [+0.398, +0.787]; action=+0.851 (n=24, STE=0.074) [+0.652, +0.937] |
| 4 | Holds vs cuts | **PASS** | BT: holds=-0.7199 (STE=0.3345, n=22) > cuts=-1.2385 (STE=0.1528, n=8); gap=0.5186 (STE=0.3677) |
| 5 | Forward path | secondary | BT=+0.357 (n=44, STE=0.154) [+0.042, +0.627]; score_jev=+0.511 (n=91, STE=0.081) [+0.336, +0.652] |
| 6 | Order/name stability | **PASS** | Δ=0.0000; add-on $0.010955 |
| 7 | FedLock consistency | report | BT vs m=+0.679 (n=46, STE=0.112) [+0.436, +0.861]; vs ma=+0.594 (n=46, STE=0.104) [+0.361, +0.770]; score_jev vs m=+0.944 (n=90, STE=0.016) [+0.900, +0.966]; vs ma=+0.774 (n=90, STE=0.044) [+0.673, +0.839]; mean s=1.776; matched=92 |

### Inversion tables

| Stratum | n | inverted | inversion (STE) | mean p(gold) | mean Brier (STE) | order-flip |
|---------|--:|--------:|----------------:|-------------:|-----------------:|-----------:|
| A extreme | 40 | 0 | 0.0000 (0.0000) | 1.0000 | 0.0000 (0.0000) | 0.0000 |
| B Shah | 200 | 38 | 0.1900 (0.0277) | 0.7451 | 0.1384 (0.0156) | 0.1050 |
| C adjacent | 22 | 1 | 0.0455 (0.0444) | 0.8555 | 0.0459 (0.0178) | 0.0909 |

Inverted C: **C018**. Inverted A: none.

### Gate 3 detail (BT primary; bootstrap 1000)

| Slice | Spearman ρ [STE; 95% CI] |
|-------|--------------------------|
| All scheduled (excl crisis) | +0.623 (n=46, STE=0.096) [+0.398, +0.787] |
| action_days | +0.851 (n=24, STE=0.074) [+0.652, +0.937] |
| hold_days vs dissent net | -0.192 (n=22, STE=0.202) [-0.513, +0.274] |
| hold_days vs d_2y | -0.135 (n=22, STE=0.244) [-0.594, +0.349] |

Secondary score_jev: all=+0.589 (n=93, STE=0.063) [+0.460, +0.701]; action=+0.918 (n=30, STE=0.033) [+0.812, +0.953].

BT fit: n_statements=48, n_comparisons=124, converged=True, γ=-0.1378.

### Gate 4 holds vs cuts

| Score | mean holds (STE, n) | mean cuts (STE, n) | mean hikes (STE, n) | gap (STE) |
|-------|---------------------|--------------------|---------------------|-----------|
| BT | -0.7199 (0.3345, 22) | -1.2385 (0.1528, 8) | 1.8273 (0.5319, 16) | 0.5186 (0.3677) |
| score_jev | 1.4570 (0.1144, 63) | 1.0356 (0.1216, 9) | 3.0671 (0.1346, 21) | 0.4214 (0.1670) |

Gate 4 is evidence that same-day funds-rate changes are an incomplete label for textual hawkishness under holds. Pre-registered pass: point means. BT gap 95% CI includes 0; score_jev gap CI does not.

### FedLock fidelity (Gate 7)

See `results/fedlock_fidelity.md`. Shared: pairwise text hawkishness; our anonymization; external score check. Not reproduced: macro-conditioned prompts; TrueSkill; `ma` as primary; full corpus; Llama judge; Swiss matching. Matching prefers title date; delta(`d`−meeting) mostly +1 when falling back to `d` field. Primary contrast uses raw `m`; `ma` is sensitivity.

### Cost and timing

Main run ≈ $0.03120 (619 calls). Name ablation ≈ $0.011. Mean latency ≈ 214 ms @ concurrency 6. Haiku Choice comparison: ≈ $0.636 and ≈ 676 ms mean vs Jev Choice ≈ $0.024 and ≈ 207 ms; inversions nearly tied on A/C.

### Artifacts

| Path | Role |
|------|------|
| `results/pair_judgments.jsonl` | Per gold pair, both orders averaged |
| `results/statement_scores.csv` | BT score/se/n_pairs + score_jev |
| `results/gates.json` | Gates with STE fields |
| `results/interpretation.json` | Estimator glossary + headline metrics |
| `results/fedlock_fidelity.md` | Gate 7 fidelity statement |
| `runs/jev/answers.jsonl` | Raw answers |

## Discussion (brief)

Gates 1/3/4/6 pass under pre-registered rules. Action-day BT Spearman exceeds the jsort +0.46 reference point estimate. Gate 4 documents incomplete behavioral labeling under holds. Gate 7 shows independent text-system agreement (especially Score vs `m`) without FedLock replication. Limitations: sparse BT graph, partial dissent scrape, openings ≠ full pressers. Follow-on experiments 3–7 (composite Scores, multi-label Nouls, calibration, span Choice, macro-relative) are stubbed in ANALYSIS §11.
