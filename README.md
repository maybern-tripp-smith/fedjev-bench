# fedjev-bench

Pre-registered evaluation of **TypeSafe / Jev** rankings of FOMC chair press-conference openings under the criterion `more hawkish about inflation`, relative to same-day funds-rate changes and an external FedLock text-score reference.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 (gates); `jev-latest` (exps 3–7) |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS (2/5/7 report) |
| **Main cost** | ≈ $0.031 · ablation +$0.011 · grand ≈ $0.042 |
| **Exps 3–7** | $0.04452752 · 385 calls · `results/experiments/` |

Long-form: [`ANALYSIS.md`](ANALYSIS.md). Short gates: [`REPORT.md`](REPORT.md). Machine-readable: [`results/gates.json`](results/gates.json) · [`results/interpretation.json`](results/interpretation.json) · [`results/experiments/`](results/experiments/). FedLock relationship: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md).

**Measurement question.** Same-day target-rate changes (`d_same`) are an incomplete label for textual hawkishness under holds. The evaluation asks whether Jev recovers easy hawk/dove orderings, tracks `d_same` on action days, and separates holds from cuts on the text axis. Agreement with FedLock scores (Gate 7) is an external consistency check, not methodological replication.

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
python scripts/run_experiments_3_7.py   # optional
```

## GitHub Pages

Deploy `/docs` from `main`. Site: https://maybern-tripp-smith.github.io/fedjev-bench/

## Citation / license

[`CITATION`](CITATION) · MIT code · data terms in [`DATA.md`](DATA.md) (Shah CC BY-NC 4.0 not fully vendored).


## FedLock-faithful protocol replica (separate)

See [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md) and ANALYSIS §12. Does not replace Gate 7.
