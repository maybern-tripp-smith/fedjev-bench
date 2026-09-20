# fedjev-bench

Pre-registered evaluation of TypeSafe/Jev pairwise rankings of FOMC chair press-conference openings under the criterion `more hawkish about inflation`. The behavioral comparison is the same-day federal funds target change (`d_same`). The external text comparison is FedLock press-conference scores.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS (2 / 5 / 7 report) |
| **Main cost** | ≈ $0.031 · ablation +$0.011 · grand ≈ $0.042 |

**Abstract.** Same-day funds-rate changes are an incomplete label for textual hawkishness when the target is unchanged. The evaluation asks whether Jev recovers easy hawk/dove orderings, agrees in rank with `d_same` on scheduled action days, and still separates holds from cuts on the text axis. Gate 7 reports agreement with an independent FedLock text score. It is not a TrueSkill or macro-conditioned replication.

Long-form: [`ANALYSIS.md`](ANALYSIS.md). Gate tables: [`REPORT.md`](REPORT.md). Machine-readable: [`results/gates.json`](results/gates.json) · [`results/interpretation.json`](results/interpretation.json). FedLock fidelity: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

---

## Offline analysis

Cached answers ship under `runs/jev/`:

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install typesafe-sdk pandas pyarrow openpyxl scipy matplotlib
python scripts/analyze_gates.py
```

Do not mutate `data/pairs/gold_pairs.jsonl` for this `run_id`.

## Live re-score (optional)

```bash
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
```

## GitHub Pages

Deploy `/docs` from `main`. Site: https://maybern-tripp-smith.github.io/fedjev-bench/

## Citation and license

[`CITATION`](CITATION) · MIT code · data terms in [`DATA.md`](DATA.md) (Shah CC BY-NC 4.0 not fully vendored).
