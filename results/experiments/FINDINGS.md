# Experiments 3–7 — Findings (draft for ANALYSIS)

**run_id:** `fedjev-2026-09-20`  
**model:** `jev-latest` (TypeSafe SystemOne; resolved model ids logged per call)  
**criterion family:** inflation / hawkishness  
**cost (this experiment suite):** $0.04453 over 385 logical calls (0 cache hits; 1060179 input tokens at $0.042/MTok input).

This section reports five follow-up probes that hold the corpus, gold pairs, and primary criterion family fixed while varying the question interface (multi-Score composite, multi-label Noul, paraphrase Choice, span Choice, and macro-conditioned Choice). Gold labels are unchanged: Stratum A extremes remain rate-path constructed; document-level `d_same` remains the FRED same-day funds-target move. All live calls use `jev-latest` via `typesafe-sdk`; answers are cached under `runs/jev/exp_cache/`.

---

## Experiment 3 — Composite atomic Scores

### Methods

For each of 95 presser-opening statements (meta-stripped), a single SystemOne request elicited four ordered Scores (levels 0–4) jointly with the Exp4 Nouls (cost sharing). Dimensions and equal weights:

| Dimension | Weight | Construct |
|-----------|-------:|-----------|
| `inflation_urgency` | 0.25 | Urgency of the inflation fight |
| `tightness_preference` | 0.25 | Preference for tighter policy |
| `reaction_toughness` | 0.25 | Toughness of reaction function / willingness to accept growth pain |
| `guidance_firmness` | 0.25 | Firmness of forward guidance / higher-for-longer tone |

Composite = equal-weight mean of the four scores ($w_d = 1/4$). Correlations use Spearman rho with bootstrap STE (1,000 resamples, seed 20260920) on scheduled, non-excluded, non-crisis meetings (n=93). Ablation drops one dimension and re-averages the remaining three with equal weight.

### Results

- Composite vs `d_same`: rho=0.562 (n=93, STE=0.063)
- Composite vs `d_same` (action days only): rho=0.893 (n=30, STE=0.037)
- Composite vs existing `score_jev`: rho=0.962 (n=93, STE=0.010)
- Composite vs FedLock press-conference `m` (meeting±1d match): rho=0.957 (n=90, STE=0.012)

Leave-one-dimension-out (Delta-rho vs full composite on `d_same`):

- Drop `inflation_urgency`: rho=0.634 (n=93, STE=0.055); Delta-rho vs full = 0.072
- Drop `tightness_preference`: rho=0.502 (n=93, STE=0.073); Delta-rho vs full = -0.060
- Drop `reaction_toughness`: rho=0.607 (n=93, STE=0.057); Delta-rho vs full = 0.045
- Drop `guidance_firmness`: rho=0.513 (n=93, STE=0.069); Delta-rho vs full = -0.048

Artifacts: `results/experiments/exp3_composite.json`, `exp3_composite.csv`.

### Interpretation

The four-way composite is a structured absolute score of communicated stance, not a pairwise Choice aggregate. Concordance with `score_jev` tests whether the richer rubric collapses to the single hawkishness Score used in the main run; concordance with `d_same` and FedLock `m` situates the composite in the same external comparisons as Gates 3 and 7. Ablation Delta-rho identifies which atomic construct carries most of the association with the rate move.

### Limitations

Equal weights are a pre-specified convenience, not estimated from data. Score levels are verbal rubrics whose interval scaling is assumed when averaging. `d_same` labels policy outcomes, not text; holds can be text-hawkish, so modest rho is expected and is not by itself a failure of the composite.

---

## Experiment 4 — Multi-label Nouls

### Methods

The same packed SystemOne call returned four Nouls (yes-probability in [0,1]): `signals_cut_soon`, `signals_higher_for_longer`, `acknowledges_banking_stress`, `blames_supply_shocks`. Eras are calendar partitions (2020; 2022 hike year; 2023-03-22 SVB meeting; other 2023; 2024; 2025–26; residual). Multi-label cases are documents with at least two Nouls >= 0.6. Pairwise Spearman among Nouls documents mutual non-exclusivity.

### Results

Mean Noul by era:

- **2020** (n=9): signals_cut_soon=0.24, signals_higher_for_longer=0.05, acknowledges_banking_stress=0.18, blames_supply_shocks=0.20
- **2022_hikes** (n=8): signals_cut_soon=0.03, signals_higher_for_longer=0.77, acknowledges_banking_stress=0.04, blames_supply_shocks=0.49
- **2023_SVB** (n=1): signals_cut_soon=0.12, signals_higher_for_longer=0.61, acknowledges_banking_stress=0.99, blames_supply_shocks=0.08
- **2023_other** (n=7): signals_cut_soon=0.07, signals_higher_for_longer=0.89, acknowledges_banking_stress=0.20, blames_supply_shocks=0.07
- **2024** (n=8): signals_cut_soon=0.46, signals_higher_for_longer=0.60, acknowledges_banking_stress=0.04, blames_supply_shocks=0.12
- **2025_26** (n=14): signals_cut_soon=0.29, signals_higher_for_longer=0.44, acknowledges_banking_stress=0.04, blames_supply_shocks=0.62
- **other** (n=48): signals_cut_soon=0.11, signals_higher_for_longer=0.13, acknowledges_banking_stress=0.09, blames_supply_shocks=0.37

**2023-03-22 (SVB) banking Noul:** `acknowledges_banking_stress` = 0.99  
(other Nouls that meeting: cut_soon=0.12, H4L=0.61, supply=0.08; doc `stmt-2023-03-22`).

Documents with >=2 high Nouls: n=9 (threshold 0.6). Pairwise Noul Spearman is reported in `exp4_nouls.json` (`noul_pair_spearman`).

### Interpretation

Nouls are not mutually exclusive by construction: a text may both acknowledge banking stress and retain a higher-for-longer signal. Era means are descriptive; the SVB meeting is a targeted face-validity check for `acknowledges_banking_stress`.

### Limitations

Era bins are coarse and unbalanced. Noul probabilities are calibrated only insofar as SystemOne's Noul primitive is; we do not claim frequentist coverage. Supply-shock attribution (`blames_supply_shocks`) can co-occur with hawkish urgency when the Committee describes shocks yet still tightens.

---

## Experiment 5 — Calibration / paraphrase consistency

### Methods

Stratum A (40 extreme pairs) times both presentation orders. Baseline instructions (main run, cached): "Which of Text A or Text B is more hawkish about inflation". Two meaning-preserving paraphrases (exact strings logged):

1. "Which of Text A or Text B argues for a tighter stance against inflation"
2. "Which of Text A or Text B is less accommodative on inflation"

Metrics: inversion rate vs gold; mean |p_gold,para - p_gold,baseline|; order-flip rate per paraphrase; reliability diagram (10 equal-width bins of p_gold vs empirical non-inversion frequency) and ECE.

### Results

- Baseline: inversion=0.0 (n=40, STE=0.0); order-flip=0.0; ECE=0.0; mean p_gold=1.0.

Paraphrases:

- `para_tighter_stance` — instructions: "Which of Text A or Text B argues for a tighter stance against inflation". Inversion 0.0 (n=40, STE=0.0). Order-flip rate 0.0. Mean |p_gold - p_gold_baseline| = 0.0. ECE = 0.0.
- `para_less_accommodative` — instructions: "Which of Text A or Text B is less accommodative on inflation". Inversion 0.0 (n=40, STE=0.0). Order-flip rate 0.0. Mean |p_gold - p_gold_baseline| = 0.002250000000000002. ECE = 0.0022499999999998632.

Artifact: `results/experiments/exp5_calibration.json`.

### Interpretation

Low inversion under paraphrase indicates criterion-string robustness within the inflation-hawkishness family. ECE and reliability bins summarize whether reported p_gold tracks empirical accuracy; large mean |Delta p| with stable winners would indicate confidence instability without rank changes.

### Limitations

Stratum A is deliberately easy (rate extremes); calibration on hard / adjacent pairs may differ. Paraphrases were author-chosen, not sampled from a paraphrase model. Baseline and paraphrase calls are not contemporaneous (baseline from the main run cache).

---

## Experiment 6 — Evidence-span Choice

### Methods

50 items (cap 50, seed 20260920): one Shah hawkish sentence as gold plus 3–5 distractors drawn preferentially from the same (year, doc_type) pool of neutrals/doves, else from the global dove/neutral pool. Choice options are span ids (`S1`…); instructions: "Which span is more hawkish about inflation". No free-form generation.

### Results

- Inversion rate: 0.48 (n=50, STE=0.07065408693062278, n_inverted=24)
- Mean p(gold): 0.4836000000000001 (STE=0.05465868864963703)
- Approx. live cost: $0.00118831

Artifact: `results/experiments/exp6_span_choice.json`.

### Interpretation

Span Choice tests whether Jev can select a hawkish inflation span among local distractors, complementary to pairwise document Choice. Chance baseline depends on option count (3–5 distractors implies 4–6 options; chance p approximately 1/K).

### Limitations

Shah labels are sentence-level and domain-specific; "nearby" is operationalized as same year and document type, not true transcript adjacency (positional offsets are unavailable in `sentences.jsonl`). Distractor difficulty is uncontrolled beyond label class.

---

## Experiment 7 — Macro-relative vs text-absolute

### Methods

Stratum A times both orders. **Absolute arm:** text-only Choice with the main-run criterion (cached). **Macro arm:** state includes `Text A`, `Text B`, and `macro_A` / `macro_B` with FRED as-of each document date — core PCE (PCEPILFE 12-month YoY when available, else level), UNRATE, and DGS10 as the risk/rate proxy (VIXCLS absent from the local FRED dump). Instructions: "Which of Text A or Text B is more hawkish about inflation given the macro conditions provided for each text". Gold remains the rate-extreme label.

### Results

- Macro-arm inversion vs gold: 0.0 (n=40, STE=0.0)
- Absolute-arm inversion vs gold: 0.0 (n=40, STE=0.0)
- Agreement rate (absolute vs macro winners): 1.0 (n=40)
- Spearman(p_gold,abs, p_gold,macro): n/a
- Mean p_gold absolute / macro: 1.0 / 0.999125

Artifact: `results/experiments/exp7_macro_relative.json`.

### Interpretation

Disagreement between arms isolates cases where macro context shifts the preferred text relative to a text-only reading. Agreement with rate-extreme gold under the macro arm is only a partial diagnostic: gold ignores the provided macro by construction.

### Limitations

Gold is not macro-conditional. Macro features are sparse (three series) and contemporaneous as-of dates may not match real-time information sets (publication lags). DGS10 substitutes for VIX. Extreme pairs may leave little room for macro to overturn an already lopsided text comparison.

---

## Cross-experiment notes

- **Cost / latency:** see `results/experiments/SUMMARY.json` (`total`, `by_experiment`).
- **Caching:** `runs/jev/exp_cache/`; append-only answer log `runs/jev/experiments_answers.jsonl`.
- **Non-interference:** `data/pairs/gold_pairs.jsonl` was not modified; no Haiku judge was used in these experiments.
