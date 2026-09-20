# How to read the results

This is a scoreboard guide for `run_id` `fedjev-2026-09-20`. It is not a second analysis.

The question is measurement. Did TypeSafe/Jev — the model under test — recover a usable ranking of Chair openings under one fixed pairwise question: `more hawkish about inflation`?

Numbers below are copied from [`REPORT.md`](REPORT.md) and [`results/gates.json`](results/gates.json). None were invented for this page. Machine-readable glossary: [`results/interpretation.json`](results/interpretation.json).

This note writes “standard error” or “s.e.” It does not use the label STE.

---

## If you only look at three numbers

1. **Easy-pair inversion = 0.000** (n = 40, s.e. 0.000). Gate 1. On the 40 obvious hawk-versus-dove document pairs, the averaged two-order winner never missed the labeled side.
2. **Action-day Spearman ρ = +0.851** (n = 24, s.e. 0.074). Gate 3. When the Committee hiked or cut, Bradley–Terry ranks tracked the signed same-day funds-target move. The 95 percent interval is [+0.652, +0.937].
3. **Score versus FedLock raw `m` = +0.944** (n = 90, s.e. 0.016). Gate 7. A direct Score pass and an independent published text score order meetings almost the same way. That is agreement of two text measures. It is not a TrueSkill replication.

None of these three is a forecast of the next meeting. None is a causal effect of words on rates.

---

## What is being measured

Two constructs are kept apart.

The **behavioral label** is `d_same`: the same-day change in the federal funds target (hike, hold, or cut). On a hold the target did not move, so `d_same` is identically zero. A zero cannot encode hawkish-hold versus dovish-hold wording.

The **textual measure** is the stance in the Chair’s opening remarks, recovered under that fixed pairwise criterion.

The Federal Open Market Committee (FOMC) is the Federal Reserve committee that sets the funds target. The documents here are Chair press-conference *openings*, not necessarily the full press conference.

**Choice** is the primary interface. The model sees two texts and picks which is more hawkish about inflation. Each pair is shown in both orders (A-then-B and B-then-A). An **inversion** is a pair whose *averaged* winner does not match the pre-labeled (“gold”) side.

**Bradley–Terry** is a pairwise strength model. It turns those Choice probabilities into one score per document on a fixed gold-pair graph (Strata A and C; 48 statements, 124 comparisons in this run).

**Score** is a secondary pass: a five-level rating mapped to a continuous `score_jev` for each opening.

**Spearman’s rank correlation (ρ)** asks whether two series produce a similar *ordering* of meetings. It does not ask whether the units match.

A **standard error** is the uncertainty attached to a point estimate. For rank correlations it is the standard deviation of 1,000 bootstrap meeting resamples. For inversion rates it is the binomial formula √[p(1−p)/n]. For means it is the sample standard deviation divided by √n. A 95 percent confidence interval, where reported, is the bootstrap percentile interval from the same resamples.

---

## What “PASS” versus “report” means here

Gates were registered before any Jev output. A **PASS** means the pre-registered rule was met on this run. It is not a journal accept/reject, and it is not a claim that the construct is “solved.”

| # | Gate | Rule on this design | Status |
|---|------|---------------------|--------|
| 1 | Easy-pair inversion | inversion ≤ 0.05 on Stratum A | **PASS** |
| 2 | Sentence discrimination | no pass line | report |
| 3 | Action ranking | Spearman(Bradley–Terry, `d_same`) ≥ +0.30 on scheduled meetings | **PASS** |
| 4 | Holds versus cuts | mean text score(holds) > mean text score(cuts) | **PASS** |
| 5 | Forward path | no pass line | secondary |
| 6 | Order / name stability | change in Stratum A inversion ≤ 0.05 when names stay in | **PASS** |
| 7 | FedLock consistency | no pass line | report |

**Report** (or **secondary**) means: publish the estimate with a standard error. Do not treat the number as a pass/fail of the document-level claim.

Gate 2 is a sentence-level stress test (Shah hawk-versus-dove sentences). Gate 5 correlates text with the subsequent 90-day change in the funds target (`d_90`). Gate 7 correlates two text scores. None of those three can fail the bench under the registered rules.

---

## What question each gate answers

**Gate 1 — easy pairs.** If you put an obvious hawk opening next to an obvious dove opening, does the ranking recover that order? This is construct validity on the easy cases. It is not a test of hard adjacent meetings.

**Gate 2 — sentences.** Can the same criterion separate hawk versus dove *sentences* from Shah et al.? Published here: inversion 0.190 (s.e. 0.028, n = 200). That is a stress test. It is not a pass/fail of the document-level claim.

**Gate 3 — action ranking.** On scheduled meetings, do text ranks agree with the signed same-day funds-target move? The registered pass line is +0.30. A published reference from jsort is about +0.46 (standard error not re-estimated here). Action-day ρ is the cleaner slice: holds contribute no variation in `d_same`.

**Gate 4 — holds versus cuts.** When the target is unchanged, `d_same` cannot tell hawkish-hold from dovish-hold text. Do mean text scores still place holds above cuts? A yes is evidence that the *behavioral label* is incomplete on holds. It is not a judgment that the text is “right” or that the voted action was wrong.

**Gate 5 — forward path.** Do text ranks co-move with the funds target over the next 90 days? Secondary. A modest positive ρ is association, not a forecast evaluation.

**Gate 6 — names and order.** Does leaving Chair names in the text change the easy-pair inversion rate by more than 0.05? A zero change is also a check that reversing presentation order did not flip easy winners. Openings rarely embed names the stripper can remove, so the zero is more informative about order than about name confounding.

**Gate 7 — FedLock.** Do this repository’s scores agree in rank with FedLock’s published press-conference scores (raw TrueSkill mean `m`; era-adjusted `ma` as a sensitivity)? FedLock is an independent published text-scoring project. Gate 7 *reads* those published numbers. It does not re-run FedLock’s tournament. See [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

---

## How to read inversion rates

Inversion is a miss rate on labeled pairs, after averaging both presentation orders.

- **0** means every averaged winner matched gold.
- **0.05** is the Gate 1 pass line (at most one miss in twenty easy pairs).
- **0.50** is a coin flip on balanced pairs.

This run:

| Stratum | What it is | n | Inverted | Inversion (s.e.) |
|---------|------------|--:|---------:|-----------------:|
| A extreme | obvious hawk versus dove documents | 40 | 0 | 0.000 (0.000) |
| B Shah | hawk versus dove sentences | 200 | 38 | 0.190 (0.028) |
| C adjacent | neighboring scheduled meetings with a nonzero `d_same` | 22 | 1 | 0.045 (0.044) |

The one inverted adjacent pair is **C018**. Accuracy is 1 − inversion (A: 1.000; B: 0.810; C: 0.955).

An **order-flip** is a pair whose winner changes when A and B are swapped. Order-flips on A were 0.000. On B they were 0.105. On C they were 0.091.

**Brier score** here is the mean squared error of the gold-side probability. Lower is better. A: 0.000 (n = 40). B: 0.138 (s.e. 0.016, n = 200). C: 0.046 (s.e. 0.018, n = 22).

Zero inversion on A does not imply well-calibrated probabilities on hard pairs. It does not imply the model can forecast policy.

---

## How to read rank correlations

Spearman ρ = +1 means the two series order meetings the same way. ρ = 0 means no rank association. ρ = −1 means they order meetings in opposite ways.

Read three things together: the point estimate, the standard error, and the 95 percent interval. An interval that includes zero is compatible with no rank association in that slice.

**Why action-day ρ exceeds all-scheduled ρ.** Holds have `d_same` = 0. They add meetings with no variation in the behavioral label. That dilutes the pooled correlation. It is an algebra fact, not a second finding.

**Why hold-day ρ versus `d_same` is not computed.** Spearman needs variation in both series. On holds, `d_same` is constant. The correlation is undefined.

Gate 3 (Bradley–Terry versus `d_same`):

| Slice | Spearman ρ | s.e. | n | 95% interval |
|-------|-----------:|-----:|--:|--------------|
| All scheduled (crisis dates dropped) | +0.623 | 0.096 | 46 | [+0.398, +0.787] |
| Action days only | +0.851 | 0.074 | 24 | [+0.652, +0.937] |
| Holds versus net dissents | −0.192 | 0.202 | 22 | [−0.513, +0.274] |
| Holds versus same-day 2-year yield change | −0.135 | 0.244 | 22 | [−0.594, +0.349] |

The secondary Score pass is similar in sign: all-scheduled +0.589 (n = 93, s.e. 0.063); action-day +0.918 (n = 30, s.e. 0.033).

Hold-day associations with dissents and the 2-year yield have intervals that include zero. That is consistent with holds mixing hawkish-hold and dovish-hold communications. The dissent scrape is also incomplete, so those two rows are noisy.

Gate 5 (versus `d_90`): Bradley–Terry +0.357 (n = 44, s.e. 0.154) [+0.042, +0.627]; Score +0.511 (n = 91, s.e. 0.081) [+0.336, +0.652]. Intervals exclude zero. The gate remains secondary.

The Bradley–Terry `se` column in `results/statement_scores.csv` is different. That is fit uncertainty from the pairwise likelihood, not a bootstrap over meetings. The comparison graph is sparse. Do not treat a document’s Bradley–Terry `se` as a meeting-sampling standard error.

---

## How to read Score gaps

The Gate 4 gap is mean text score on holds minus mean text score on cuts.

| Score | Mean holds (s.e., n) | Mean cuts (s.e., n) | Gap (s.e.) | 95% interval on the gap |
|-------|----------------------|---------------------|------------|-------------------------|
| Bradley–Terry | −0.720 (0.335, 22) | −1.239 (0.153, 8) | +0.519 (0.368) | [−0.202, +1.239] |
| `score_jev` | 1.457 (0.114, 63) | 1.036 (0.122, 9) | +0.421 (0.167) | [+0.094, +0.749] |

The registered pass rule is the *point* comparison: mean(holds) > mean(cuts). Both series pass.

The Bradley–Terry gap interval includes zero. The Score gap interval does not. So the sign of the Bradley–Terry gap is the registered result; the precision of that gap is limited (eight cut meetings on the Bradley–Terry graph).

Hikes sit well above both: Bradley–Terry mean +1.827 (s.e. 0.532, n = 16); Score mean 3.067 (s.e. 0.135, n = 21). That is expected if hikes are the hawkish tail of the same-day action. It is not the Gate 4 test.

---

## How to read cost and latency

Cost and latency are accounting facts. They are not gate criteria.

List price for jev-1.13.0 in this run: $0.042 per million input tokens; output free.

- Main run ≈ $0.03120 (619 calls: 524 Choice + 95 Score).
- Name-ablation add-on ≈ $0.011 (80 calls).
- Grand total ≈ $0.042.
- Mean per-call latency ≈ 214 ms at concurrency 6.

Same-protocol Choice comparison against Claude Haiku 4.5 (524 Choice calls):

| | Jev 1.13.0 | Haiku 4.5 |
|--|------------|-----------|
| Stratum A / C inversion | 0.000 / 0.045 | 0.000 / 0.045 |
| Stratum B inversion | 0.190 | 0.170 |
| Choice USD | ≈ $0.024 | ≈ $0.636 (about 27×) |
| Mean latency | ≈ 207 ms | ≈ 676 ms (about 3.3×) |

Winner agreement (inversion) is the accuracy comparison. Listed dollars and milliseconds are separate axes. On Strata A and C the inversion rates match. On Shah, Haiku inversion is 0.170 versus 0.190 for Jev, with a higher Haiku order-flip rate (0.24 versus 0.105). That is not a gate.

---

## Strong, weak, and inconclusive evidence — for this design

These bars are the bars that were registered. They are not universal grades for every hawkishness paper.

**Strong, on this protocol.**

- Gate 1 inversion at or near 0, and well below 0.05, on n = 40 easy pairs.
- Gate 3 action-day ρ above the +0.30 pass line *and* above the jsort +0.46 reference, with a 95 percent interval that excludes zero.
- Gate 6 inversion change at or near 0.
- Gate 7 Score-versus-`m` near a rank ceiling, with a tight standard error, *read as consistency between two text scores*.

This run meets those descriptions: inversion 0.000; action-day ρ +0.851 (s.e. 0.074); name/order Δ 0.000; Score versus `m` +0.944 (s.e. 0.016, n = 90).

**Weak, on this protocol.**

- Gate 1 inversion above 0.05 (easy pairs fail).
- Gate 3 action-day ρ below +0.30, or an interval that includes zero or goes negative.
- Gate 4 mean(holds) ≤ mean(cuts) — the text axis would not separate the two regimes where `d_same` is uninformative.
- Gate 6 inversion change above 0.05.

**Inconclusive, even when a gate PASSes.**

- The Gate 4 Bradley–Terry gap interval includes zero. The point estimate passes; the gap is imprecisely estimated.
- Gate 2 at 19 percent inversion. Useful as a sentence stress test. Not a verdict on documents.
- Hold-day dissent and 2-year-yield correlations. Wide intervals; incomplete dissent scrape.
- Gate 5. Secondary by design; modest ρ; not a trading rule.
- Gate 7. Report-only. High agreement does not validate either scoring system against “true” hawkishness. There is no such index in this repository.
- A sparse Bradley–Terry graph (48 statements, 124 comparisons). Document-level Bradley–Terry scores are not a dense tournament.

---

## What these results do not prove

**Holds make `d_same` an incomplete label.** That is a statement about the *behavioral* series. When the target is unchanged, the same-day move cannot encode hawkish-hold versus dovish-hold language. Gate 4 is construct validity for that claim. It does not prove that text “overrides” the voted action.

**Gate 7 is agreement with FedLock text scores.** Spearman between this repository’s Bradley–Terry / Score series and FedLock’s published `m` / `ma`. It is not a TrueSkill replication. It does not re-run Llama 3.3 70B, macro-conditioned prompts, Swiss pairing, or FedLock’s ~60,000-comparison / ~4,000-speech tournament. Details: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

**The replica is a separate experiment.** `run_id` `fedjev-fedlock-replica-2026-09-20` re-runs a FedLock-style TrueSkill tournament on the 95 openings (Jev arm and Haiku arm) and compares those ratings to published `m` / `ma`. That is protocol fidelity on a 95-document corpus. It is not Gate 7, and it is not FedLock’s full scale. See [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md).

**Other non-claims.**

- No causal effect of communication on rates, markets, or later policy.
- No forecast of the next funds-target decision.
- Zero easy-pair inversion does not imply calibration on hard pairs.
- Chair openings are not full press conferences. Agreement with FedLock `press_conference` scores is not a same-document comparison.
- Cost and latency do not decide validity.
- Experiments 3–7 in [`ANALYSIS.md`](ANALYSIS.md) §11 are exploratory. They are not the registered gates.

---

## Where to go next

| If you want | Open |
|-------------|------|
| Methods, figures, limitations | [`ANALYSIS.md`](ANALYSIS.md) |
| Gate tables and artifacts | [`REPORT.md`](REPORT.md) |
| Gate 7 match and fidelity | [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md) |
| TrueSkill replica (separate) | [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md) |
| Machine-readable estimates | [`results/gates.json`](results/gates.json), [`results/interpretation.json`](results/interpretation.json) |
