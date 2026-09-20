# fedjev-bench

Pre-registered evaluation of **TypeSafe / Jev** rankings of FOMC chair press-conference openings under the criterion `more hawkish about inflation`, relative to same-day funds-rate changes and an external FedLock text-score reference.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS (2/5/7 report) |
| **Main cost** | ≈ $0.031 · ablation +$0.011 · grand ≈ $0.042 |

Long-form: [`ANALYSIS.md`](ANALYSIS.md) (Abstract, methods, FedLock fidelity, Discussion). Short gates: [`REPORT.md`](REPORT.md). Machine-readable: [`results/gates.json`](results/gates.json) · [`results/interpretation.json`](results/interpretation.json). FedLock relationship: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

**Measurement question (informal):** Are same-day target-rate changes a complete label for textual hawkishness? The evaluation asks whether Jev recovers easy hawk/dove orderings, tracks `d_same` on action days, and still separates holds from cuts on the text axis—where `d_same` is uninformative by construction.

---

## Quick start (offline analysis)

Cached answers ship under `runs/jev/`:

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install typesafe-sdk pandas pyarrow openpyxl scipy matplotlib
python scripts/analyze_gates.py
```

Do **not** mutate `data/pairs/gold_pairs.jsonl` for this `run_id`.

## Live re-score (optional)

```bash
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
```

## GitHub Pages

Deploy `/docs` from `main`. Site: https://maybern-tripp-smith.github.io/fedjev-bench/

## Citation / license

[`CITATION`](CITATION) · MIT code · data terms in [`DATA.md`](DATA.md) (Shah CC BY-NC 4.0 not fully vendored).
