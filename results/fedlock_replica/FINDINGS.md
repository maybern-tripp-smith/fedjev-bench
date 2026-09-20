# FedLock-faithful protocol replication — Findings

**run_id:** `fedjev-fedlock-replica-2026-09-20`  
**Scope:** Separate experiment on the 95 chair-opening corpus. Faithful protocol relative to FedLock V3 documentation; **not** a 4k-speech / ~60k-comparison scale replication. Does not replace Gate 7 (external consistency under the main BT/Score protocol).

## Methods

The judge task follows FedLock V3: pairwise selection of the more hawkish monetary-policy stance **conditional on macroeconomic conditions** attached to each text (Core PCE from PCEPILFE year-over-year when computable else level; UNRATE; real GDP growth from GDPC1 quarter-over-quarter SAAR when available else year-over-year; VIXCLS). Texts are anonymized via `scripts/strip_meta.py` (speaker titles, dates, and chair surnames removed); Chair identity is not placed in judge state.

Aggregation uses Microsoft TrueSkill with priors μ₀=50, σ₀=8.33, stopping when all σ<2.0 or approximately 30 comparisons per document (global cap 2,850). Pairing is Swiss-style with uncertainty targeting (prefer high-σ players and similar μ). Soft probabilities from the judge update ratings by outcome interpolation (confidence-weighted). Presentation order of Text A/B is randomized each match.

Arms: (i) TypeSafe SystemOne Choice (`jev-latest`); (ii) Claude `claude-haiku-4-5-20251001` with structured JSON winner and soft probabilities; (iii) published FedLock `press_conference` fields `m`, `ma`, `s`, `n` from `data/raw/fedlock/data.json` (Llama not re-invoked).

FedLock date matching (deltas 0, +1, −1, +2 on `d`): **92** of 95 openings matched.

### Protocol deviations / notes

- Corpus is 95 chair openings (jsort-style), not FedLock’s ~4k-speech pool.
- Soft TrueSkill via outcome interpolation of rate_1vs1 under judge p_A / p_B (confidence-weighted).
- VIXCLS and GDPC1 downloaded into data/raw/fred/ for this experiment (full macro set).
- One Haiku comparison failed JSON parse mid-tournament (truncated rationale); round continued with 46 pairs. Parser later hardened.
- Both arms stopped on all σ<2.0 (~22 comparisons per document on average), below the 30/doc and 2,850 global caps.

## Results

### Rank agreement

- **Jev↔Haiku.** Spearman=+0.955 (STE=0.012; 95% CI [+0.923, +0.971]; n=95); Kendall=+0.830 (STE=0.023; 95% CI [+0.784, +0.873]; n=95).
- **Jev↔FedLock m.** Spearman=+0.965 (STE=0.011; 95% CI [+0.934, +0.978]; n=92); Kendall=+0.850 (STE=0.021; 95% CI [+0.806, +0.888]; n=92).
- **Jev↔FedLock ma.** Spearman=+0.790 (STE=0.044; 95% CI [+0.681, +0.853]; n=92); Kendall=+0.576 (STE=0.043; 95% CI [+0.492, +0.658]; n=92).
- **Haiku↔FedLock m.** Spearman=+0.945 (STE=0.013; 95% CI [+0.910, +0.962]; n=92); Kendall=+0.798 (STE=0.023; 95% CI [+0.753, +0.841]; n=92).
- **Haiku↔FedLock ma.** Spearman=+0.768 (STE=0.042; 95% CI [+0.666, +0.828]; n=92); Kendall=+0.550 (STE=0.042; 95% CI [+0.463, +0.629]; n=92).

### Cost and performance

| Arm | n_comps | input tok | output tok | USD | $/MTok eff. | $/comp | lat mean / p50 / p95 (ms) | comps/s |
|-----|--------:|----------:|-----------:|----:|------------:|-------:|---------------------------:|--------:|
| jev | 1034 | 3376150 | 28768 | 0.1418 | 0.0416 | 0.000137 | 283 / 271 / 419 | 22.978 |
| haiku | 1033 | 3347688 | 48412 | 3.5897 | 1.0570 | 0.003475 | 732 / 687 / 988 | 8.156 |

Jev stop: `all_sigma_lt_2`; max σ=1.986; fraction σ<2=1.000.
Haiku stop: `all_sigma_lt_2`; max σ=1.965; fraction σ<2=1.000.

## Interpretation

Spearman/Kendall concordance between Jev and Haiku under a shared FedLock-style protocol measures cross-judge stability of the relative-hawkishness construct on this openings sample. Concordance with published FedLock `m` / `ma` asks whether the same protocol family, applied to chair openings rather than FedLock’s broader speech corpus and Llama 3.3 70B judge, recovers a similar ordering of meeting-day stance. Era-adjusted `ma` removes quarterly means; disagreement between `m` and `ma` contrasts therefore partly reflects era composition of the 2011–2026 openings window.

Cost and latency columns are accounting facts for the listed prices (Jev $0.042/MTok input, output free; Haiku $1.0/MTok input, $5.0/MTok output). They are not accuracy claims.

## Limitations

- **Scale.** FedLock reports ~60k comparisons on ~4k speeches; this run uses the 95 openings corpus with a ~2,850-comparison cap. Convergence to σ<2 for every document is not guaranteed at this scale.
- **Document mismatch.** Openings are a subset of press-conference communication; FedLock `press_conference` scores may reflect fuller presser text.
- **Judge stack.** FedLock’s published scores use Llama 3.3 70B; this replica uses Jev and Haiku. Agreement with `m`/`ma` mixes protocol fidelity and model differences.
- **Soft TrueSkill.** Confidence-weighted updates via outcome interpolation are a documented approximation to FedLock’s “updates by judge confidence,” not a bit-exact reimplementation of an unpublished update kernel.
- **Macro vintage.** FRED series are taken as-of speech date from the local dump (plus downloaded VIXCLS/GDPC1); real-time vintage differs from revised series.

## Artifacts

- `results/fedlock_replica/trueskill_{jev,haiku}.csv`
- `results/fedlock_replica/comparisons_{jev,haiku}.jsonl`
- `results/fedlock_replica/cost_performance.json`
- `results/fedlock_replica/agreement.json`
- `results/figures/fedlock_replica_*.png` (copied to `docs/figures/`)

