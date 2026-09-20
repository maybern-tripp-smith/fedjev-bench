# Relationship to FedLock (fidelity)

Gate 7 is an **external consistency check**, not a FedLock replication.

## What we faithfully share
- Pairwise text hawkishness judgments
- Name anonymization / meta-stripping on *our* Jev Choice calls
- Use of FedLock `press_conference` scores as an independent text-scoring reference

## What we do **not** reproduce
- Macro-conditioned judge prompts (Core PCE, unemployment, GDP growth, VIX at speech time)
- TrueSkill aggregator (μ start 50, σ≈8.33 → converge σ<2); ~60k comparisons / ~4k speeches
- Era adjustment (`ma`) as the Gate 7 **primary** metric (we report `ma` as sensitivity alongside raw `m`)
- Full speech corpus, Llama 3.3 70B judge, Swiss / uncertainty-targeted matching

## Implication
Gate 7 ρ asks: *do two independent text-scoring systems agree on meeting-day hawkishness?*
It does **not** claim: *we replicated FedLock*.

## Matching
- Policy: prefer title-embedded meeting date; else FedLock `d` with deltas 0, +1, −1, +2
- Matched meetings (all calendar): **92**
- Main-analysis matched rows: **90**
- Same-calendar-day on FedLock `d` field: **1**
- Delta(`fedlock_d` − meeting) distribution: `{'0': 1, '1': 89}`
- Match-via distribution: `{'title_date': 90}`
- Mean FedLock `s` on matched main set: **1.7762** (TrueSkill uncertainty; lower ⇒ more converged)

## Results (with STE)
| Contrast | ρ | STE | n | 95% CI |
|----------|---|----:|--:|--------|
| BT vs `m` (raw) | +0.679 | 0.112 | 46 | [+0.436, +0.861] |
| BT vs `ma` (era-adj) | +0.594 | 0.104 | 46 | [+0.361, +0.770] |
| score_jev vs `m` | +0.944 | 0.016 | 90 | [+0.900, +0.966] |
| score_jev vs `ma` | +0.774 | 0.044 | 90 | [+0.673, +0.839] |

## Corpus mismatch
Our documents are chair **openings** (jsort-style). FedLock `press_conference` may be fuller presser text. Agreement is still informative but not same-document.

## Separate experiment: FedLock-faithful protocol replication

Gate 7 remains an external consistency check only. A **separate** experiment implements a FedLock-V3-faithful protocol (macro-conditioned relative hawkishness, anonymization, TrueSkill with Swiss/uncertainty pairing) on the 95 openings corpus, comparing Jev, Haiku, and published FedLock `m`/`ma`. See `results/fedlock_replica/FINDINGS.md` and ANALYSIS §12. That run is **not** a 4k-speech / ~60k-comparison scale replication.

