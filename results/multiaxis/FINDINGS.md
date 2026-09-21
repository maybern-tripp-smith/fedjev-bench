# Multi-axis FINDINGS

**run_id:** `fedjev-multiaxis-2026-09-20`  
**model:** Jev only (`jev-latest`) — Haiku not run  
**spend (tracked):** $1.5329  

## Scope

Prepared chair press-conference **openings** only (n=95). Q&A drift is **out of scope** (Q&A not vendored). Full-speech robustness is **future work**.

## Designs

1. **Text-only** — no macro in the judge state.
2. **Conditional** — same-era Core PCE year-over-year, unemployment rate, real GDP growth (QoQ SAAR), VIX, and Chicago Fed National Financial Conditions Index (NFCI) attached; ask which passage is higher on the axis *given* conditions.

## Does “something else” survive after tightness?

### text

- PC1 variance share: **50.6%**; dominant loading axis: `ax1_inflation_hawkish`.
- PC2 variance share: **19.7%**.
- PC1 loadings: `{"ax1_inflation_hawkish": 0.506, "ax2_emp_vs_infl": -0.462, "ax3_lookthrough": -0.306, "ax4_forward_path": -0.11, "ax5_qt_eager": 0.433, "ax6_fci_restrictive": -0.002, "ax7_infl_vs_labor_risk": 0.487}`
- PC2 loadings: `{"ax1_inflation_hawkish": -0.056, "ax2_emp_vs_infl": -0.122, "ax3_lookthrough": 0.187, "ax4_forward_path": -0.611, "ax5_qt_eager": -0.059, "ax6_fci_restrictive": -0.755, "ax7_infl_vs_labor_risk": -0.027}`
- Near-duplicates to axis 1 (|rho|>=0.90): `ax7_infl_vs_labor_risk`.

### conditional

- PC1 variance share: **55.5%**; dominant loading axis: `ax1_inflation_hawkish`.
- PC2 variance share: **17.0%**.
- PC1 loadings: `{"ax1_inflation_hawkish": 0.496, "ax2_emp_vs_infl": -0.465, "ax3_lookthrough": -0.266, "ax4_forward_path": -0.041, "ax5_qt_eager": 0.445, "ax6_fci_restrictive": 0.2, "ax7_infl_vs_labor_risk": 0.478}`
- PC2 loadings: `{"ax1_inflation_hawkish": -0.065, "ax2_emp_vs_infl": 0.253, "ax3_lookthrough": -0.592, "ax4_forward_path": 0.003, "ax5_qt_eager": -0.199, "ax6_fci_restrictive": 0.724, "ax7_infl_vs_labor_risk": -0.132}`
- Near-duplicates to axis 1 (|rho|>=0.90): `ax2_emp_vs_infl`, `ax7_infl_vs_labor_risk`.

## Gate snapshot (action-day Spearman vs `d_same`)

| tag | rho | s.e. | n | pass (>=0.30) |
|-----|----:|-----:|--:|:-------------:|
| `ax1_inflation_hawkish__conditional` | +0.827 | 0.073 | 30 | PASS |
| `ax1_inflation_hawkish__text` | +0.702 | 0.121 | 30 | PASS |
| `ax2_emp_vs_infl__conditional` | -0.866 | 0.047 | 30 | fail |
| `ax2_emp_vs_infl__text` | -0.870 | 0.048 | 30 | fail |
| `ax3_lookthrough__conditional` | -0.451 | 0.147 | 30 | fail |
| `ax3_lookthrough__text` | -0.505 | 0.151 | 30 | fail |
| `ax4_forward_path__conditional` | +0.513 | 0.109 | 30 | PASS |
| `ax4_forward_path__text` | +0.414 | 0.125 | 30 | PASS |
| `ax5_qt_eager__conditional` | +0.715 | 0.101 | 30 | PASS |
| `ax5_qt_eager__text` | +0.612 | 0.116 | 30 | PASS |
| `ax6_fci_restrictive__conditional` | +0.650 | 0.133 | 30 | PASS |
| `ax6_fci_restrictive__text` | +0.765 | 0.095 | 30 | PASS |
| `ax7_infl_vs_labor_risk__conditional` | +0.815 | 0.072 | 30 | PASS |
| `ax7_infl_vs_labor_risk__text` | +0.699 | 0.106 | 30 | PASS |

## Tournament cost / comps

| tag | n_comps | stop | max sigma | near-0.5 |
|-----|--------:|------|----------:|---------:|
| `ax1_inflation_hawkish__text` | 1200 | max_comps | 2.382 | 149 |
| `ax1_inflation_hawkish__conditional` | 1128 | all_sigma_lt_2 | 1.998 | 228 |
| `ax2_emp_vs_infl__text` | 1200 | max_comps | 2.324 | 178 |
| `ax2_emp_vs_infl__conditional` | 1175 | all_sigma_lt_2 | 1.994 | 149 |
| `ax3_lookthrough__text` | 1034 | all_sigma_lt_2 | 1.996 | 213 |
| `ax3_lookthrough__conditional` | 987 | all_sigma_lt_2 | 1.978 | 255 |
| `ax4_forward_path__text` | 1081 | all_sigma_lt_2 | 1.983 | 157 |
| `ax4_forward_path__conditional` | 1081 | all_sigma_lt_2 | 1.956 | 207 |
| `ax5_qt_eager__text` | 1175 | all_sigma_lt_2 | 1.975 | 211 |
| `ax5_qt_eager__conditional` | 1034 | all_sigma_lt_2 | 1.986 | 172 |
| `ax6_fci_restrictive__text` | 987 | all_sigma_lt_2 | 1.989 | 309 |
| `ax6_fci_restrictive__conditional` | 987 | all_sigma_lt_2 | 1.980 | 284 |
| `ax7_infl_vs_labor_risk__text` | 1200 | max_comps | 2.220 | 138 |
| `ax7_infl_vs_labor_risk__conditional` | 1200 | max_comps | 2.128 | 159 |

## Interpretation (non-causal)

Text ranks do **not** cause rate changes. Associations with `d_same` and yield moves are construct-validity checks on whether an axis separates meetings the way a funds-target observer would expect — not structural estimates.

## Artifacts

- `results/multiaxis/scores/*.csv`, `ranked/*.csv`, `comparisons/*.jsonl`
- `results/multiaxis/corr_{text,conditional}.csv`, `loadings_*.csv`
- `results/multiaxis/gates.json`, `analysis_summary.json`, `cost.json`
- Figures: `multiaxis_corr_*.png`, `multiaxis_loadings_*.png`, `multiaxis_timeseries_*.png`, `multiaxis_gates_dsame.png`

## Bottom line

**Something else survives only as a smaller second factor**, not as a replacement for inflation-hawkish language. Axis 1 is PC1. Drop axis 7 as a near-duplicate. Treat axes 2–3 as failing the funds-target construct check (and note heavy empty-filter fallback). Axes 4–6 are partially informative but load more on PC2 than on a new dominant dimension.
