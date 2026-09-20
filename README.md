# fedjev-bench

**TypeSafe / Jev** experiment: does a text model rank FOMC communications by *hawkishness about inflation*, and how does that ranking relate to the rate series?

**Thesis:** Rate changes label *policy*. Jev labels *text*. Gate 4 (holds scored above cuts) is the interesting disagreement — not a bug.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS (2/5/7 report) |
| **Main cost** | ≈ $0.031 · ablation +$0.011 · grand ≈ $0.042 |

Long-form write-up: [`ANALYSIS.md`](ANALYSIS.md) · Short gates: [`REPORT.md`](REPORT.md) · Machine: [`results/gates.json`](results/gates.json)

---

## Quick start (reproduce analysis offline)

Cached Jev answers ship under `runs/jev/`. You can rebuild gate tables without spending:

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
export TYPESAFE_API_KEY=ts_...   # from https://typesafe.ai — never commit
# or: cp .env.example .env  and fill it (gitignored)

python score.py --live --full              # Choice both orders + Score
python scripts/run_name_ablation.py --live # Gate 6 names-in (cache key \|names=1)
python scripts/analyze_gates.py
```

Pricing used in the report (**jev-1.13.0**): **$0.042 / Mtok input**; output free. Confirm current numbers at [typesafe.ai](https://typesafe.ai).

`scripts/load_typesafe_env.py` reads **`TYPESAFE_API_KEY` from the environment only**.

## Layout

```
fedjev-bench/
  ANALYSIS.md REPORT.md DATA.md CITATION LICENSE
  score.py
  scripts/           # prepare_*, analyze_gates, run_name_ablation, strip_meta
  data/clean/        # statements, sentences
  data/labels/       # meetings parquet/csv (FRED-aligned)
  data/pairs/        # frozen gold_pairs.jsonl
  data/raw/          # fred, fedlock snapshot, slim jsort, Shah attribution
  runs/jev/          # answers + cache (main + names ablation)
  results/           # gates, cost, timing, figures, judgments
  docs/              # GitHub Pages site
```

## GitHub Pages

Site source is the `/docs` folder (zero-build HTML).

1. Push this repo to `main`.
2. **Settings → Pages → Build and deployment**
3. Source: **Deploy from a branch**
4. Branch: **`main`** / folder: **`/docs`**
5. Save. Site: **https://maybern-tripp-smith.github.io/fedjev-bench/**

`docs/.nojekyll` is present so GitHub skips Jekyll.

## Gates (pre-registered)

| # | Gate | Pass line | Result |
|---|------|-----------|--------|
| 1 | Easy-pair inversion (A) | ≤ 0.05 | **PASS** (0.000) |
| 2 | Shah sentence discrimination | report | inv=0.190 |
| 3 | BT score vs `d_same` | ≥ +0.30 | **PASS** (+0.623 / action +0.851) |
| 4 | mean(holds) > mean(cuts) | holds > cuts | **PASS** (gap +0.519 BT) |
| 5 | vs `d_90` | secondary | +0.357 BT |
| 6 | Names-in Δ inversion | Δ ≤ 0.05 | **PASS** (Δ=0.000) |
| 7 | FedLock Spearman | report | +0.685 BT / +0.946 score |

## Citation

See [`CITATION`](CITATION). Data terms: [`DATA.md`](DATA.md).

## License

MIT for code. Third-party data: see `DATA.md` (esp. Shah **CC BY-NC 4.0** — full dump not vendored).

## Haiku 4.5 comparison *(optional)*

```bash
export ANTHROPIC_API_KEY=...
python scripts/run_haiku_comparison.py --live --concurrency 8
```

Full 262×2 Choice re-run vs Jev. See ANALYSIS §11 and `results/haiku_comparison.json`.
