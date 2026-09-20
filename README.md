# fedjev-bench

Pre-registered evaluation of TypeSafe/Jev pairwise rankings of FOMC chair press-conference openings under the criterion `more hawkish about inflation`. The behavioral comparison is the same-day federal funds target change (`d_same`). The external text comparison is FedLock press-conference scores.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 (gates); `jev-latest` (Experiments 3–7) |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Pass/fail** | Gates 1, 3, 4, 6 pass; Gates 2, 5, 7 report-only or secondary |
| **Main cost** | ≈ $0.031; name ablation ≈ $0.011; combined ≈ $0.042 |
| **Experiments 3–7** | $0.04453; 385 calls; `results/experiments/` |

## Abstract

Same-day funds-rate changes are an incomplete label for textual hawkishness when the target is unchanged. The evaluation asks whether the ranking recovers rate-extreme hawk-versus-dove orderings, agrees in rank with `d_same` on scheduled action days, and still separates holds from cuts on the text axis. Gate 7 reports agreement with an independent FedLock text score. It is not a TrueSkill or macro-conditioned replication. Experiments 3–7 vary the question interface on the same gold labels. Long-form sections: Abstract, Contributions, Methods, Results, Discussion, Limitations.

Long-form: [`ANALYSIS.md`](ANALYSIS.md). Gate tables: [`REPORT.md`](REPORT.md). Figures: [`results/figures/`](results/figures/). Machine-readable: [`results/gates.json`](results/gates.json) · [`results/interpretation.json`](results/interpretation.json) · [`results/experiments/`](results/experiments/). FedLock fidelity: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

---

## Offline analysis

Cached answers ship under `runs/jev/`:

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install typesafe-sdk pandas pyarrow openpyxl scipy matplotlib
python scripts/analyze_gates.py
python scripts/plot_figures.py
```

Do not mutate `data/pairs/gold_pairs.jsonl` for this `run_id`.

## Live re-score (optional)

```bash
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
python scripts/run_experiments_3_7.py   # optional
```

## GitHub Pages

Deploy `/docs` from `main`. Site: https://maybern-tripp-smith.github.io/fedjev-bench/

## Citation and license

[`CITATION`](CITATION) · MIT code · data terms in [`DATA.md`](DATA.md) (Shah CC BY-NC 4.0 not fully vendored).

A separate TrueSkill protocol replica (`fedjev-fedlock-replica-2026-09-20`) is in [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md) and ANALYSIS (Results, Figures 19–24). Jev↔FedLock `m` Spearman=+0.965 (STE=0.011, n=92). Listed cost: Jev $0.1418 (1,034 comparisons); Haiku $3.5897 (1,033 comparisons). It does not replace Gate 7.
