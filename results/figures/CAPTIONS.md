# Figure captions

Research-note captions for publication figures under `results/figures/` (mirrored in `docs/figures/`). All quantities are taken from the frozen `fedjev-2026-09-20` run artifacts. STE denotes the reported standard error (bootstrap SD for Spearman; binomial √[p(1−p)/n] for rates; sd/√n for means unless otherwise noted).

## `gate3_score_vs_dsame.png`

Figure. Same-day change in the funds target (`d_same`, percentage points) against Bradley–Terry statement scores (left panel) and Score-pass `score_jev` (right panel). Points are scheduled meetings excluding pre-specified crisis dates; navy markers denote action days (`y_action` ≠ 0) and gray markers denote holds. On action days, Spearman ρ(BT, `d_same`) = 0.85 (STE 0.07, n=24); pooled across scheduled meetings, ρ = 0.62 (STE 0.10, n=46). For `score_jev`, action-day ρ = 0.92 (STE 0.03, n=30) and pooled ρ = 0.59 (STE 0.06, n=93). Interpretation: when the Committee changes the target, textual hawkishness ranks co-move with the signed same-day move; under holds, `d_same` is identically zero and cannot identify stance.

## `gate1_2_inversion_bars.png`

Figure. Inversion rates (averaged two-order winner ≠ gold) with binomial STE √[p(1−p)/n] by stratum for Jev and Claude Haiku 4.5 on identical pairs. Sample sizes: Stratum A (extreme) n=40; B (Shah) n=200; C (adjacent) n=22. Stratum A inversion is 0.000 for both models (Gate 1 pass line ≤ 0.05). Stratum B rates are 0.190 (Jev) and 0.170 (Haiku). Interpretation: easy document-pair discrimination is shared; residual error concentrates in the sentence-level stress test.

## `gate4_holds_cuts_hikes.png`

Figure. Mean BT score and `score_jev` (± STE) by same-day action class (cuts, holds, hikes). BT sample sizes: cuts=8, holds=22, hikes=16; `score_jev`: 9/63/21. Holds−cuts gap: BT = 0.519 (STE 0.368); `score_jev` = 0.421 (STE 0.167). Interpretation: under holds, `d_same` conveys no information about hawkish versus dovish communication; higher mean text scores on holds than on cuts therefore indicate that same-day funds-rate changes are an incomplete label for textual hawkishness in that regime (pre-registered contrast is the point comparison of means).

## `gate7_fedlock_scatter.png`

Figure. FedLock press-conference raw score `m` versus Jev `score_jev` for matched scheduled meetings (title-embedded meeting date preferred; otherwise FedLock `d` with deltas 0, +1, −1, +2). n = 90. Spearman ρ = 0.944 (STE 0.016; 95% bootstrap CI [0.900, 0.966]). Interpretation: two independently constructed text-scoring systems agree on meeting-day hawkishness. The figure reports external consistency; it is not a methodological replication of FedLock (different corpus, judge model, and aggregator; see the fidelity note).

## `haiku_vs_jev_cost_latency.png`

Figure. Listed Choice API cost (USD) and per-call latency p50 (ms) for Jev versus Claude Haiku 4.5 on the same n = 524 Choice calls. Jev Choice cost ≈ $0.024, p50 ≈ 196 ms; Haiku cost ≈ $0.636, p50 ≈ 621 ms. Interpretation: on this protocol, winner agreement on Strata A/C is nearly tied (see inversion table); cost and latency are separate evaluation axes and favor Jev at published list prices.

## `exp3_composite_vs_dsame.png`

Figure. Equal-weight four-dimension composite Score versus `d_same` for scheduled main-analysis meetings (n = 93). Spearman ρ = 0.562 (STE 0.063); on action days, ρ = 0.893 (STE 0.037, n = 30). Interpretation: a structured absolute Score of communicated stance co-moves with same-day policy actions; holds again pin `d_same` at zero, so pooled association is attenuated relative to action days.

## `exp3_ablation.png`

Figure. Leave-one-dimension-out change in Spearman ρ versus `d_same` relative to the full equal-weight composite (full ρ = 0.562, n = 93). Dimension-wise Δρ: inflation urgency Δρ=+0.072; tightness preference Δρ=-0.060; reaction toughness Δρ=+0.045; guidance firmness Δρ=-0.048. Interpretation: negative Δρ indicates that the omitted dimension carried association with the rate move; positive Δρ indicates that the remaining three dimensions fit `d_same` at least as well under equal weights.

## `exp4_noul_by_era.png`

Figure. Mean Noul probabilities (± STE) by calendar era for four non-exclusive labels (signals_cut_soon, signals_higher_for_longer, acknowledges_banking_stress, blames_supply_shocks). Per-era sample sizes are annotated under the category axis. Interpretation: label mass shifts with the policy cycle (higher-for-longer during the hiking era; banking-stress mass around SVB) without imposing mutual exclusivity among labels.

## `exp5_reliability.png`

Figure. Reliability diagram for the baseline criterion: bin-mean reported p_gold versus empirical non-inversion frequency on Stratum A pairs (n = 40). Expected calibration error (ECE) = 0.000. Interpretation: these pairs are easy (p_gold ≈ 1), so probability mass concentrates in the uppermost bin; apparent calibration should not be extrapolated to harder strata without additional evidence.

## `exp6_span_pgold.png`

Figure. Distribution of p_gold on the gold span across Exp. 6 items (n = 50). Inversion rate = 0.48 (STE 0.07); mean p_gold = 0.48. Interpretation: under this distractor design, span Choice is near chance, indicating that document-level discrimination does not automatically transfer to short-span selection.

## `exp7_macro_agreement.png`

Figure. Inversion rates under absolute versus macro-conditioned Choice instructions, and winner agreement between arms (± binomial STE), on Stratum A pairs (n = 40). Both inversion rates are 0.00; winner agreement = 1.00. Interpretation: on rate-extreme gold pairs, providing macro context does not overturn the absolute hawkishness ordering. This is a limited diagnostic rather than a pure test of macro-conditional judgment, because gold remains rate-extreme by construction.
