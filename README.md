# fedjev-bench

Pre-registered evaluation of TypeSafe/Jev pairwise rankings of Federal Open Market Committee (FOMC) chair press-conference openings under the criterion `more hawkish about inflation`. The behavioral comparison is the same-day federal funds target change (`d_same` — hike, hold, or cut; zero on holds by construction). The external *text* comparison is FedLock, an independent published scoring project ([methodology](https://jnathan9.github.io/fedlock/)): Gate 7 is rank agreement with those published press-conference scores, not a TrueSkill replication.

| | |
|--|--|
| **run_id** | `fedjev-2026-09-20` |
| **model** | jev-1.13.0 |
| **criterion** | `more hawkish about inflation` |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS (2 / 5 / 7 report) |
| **Main cost** | ≈ $0.031 · ablation +$0.011 · grand ≈ $0.042 |

**Abstract.** Same-day funds-rate changes are an incomplete label for textual hawkishness when the target is unchanged. The evaluation asks whether Jev recovers easy hawk/dove orderings, agrees in rank with `d_same` on scheduled action days, and still separates holds from cuts on the text axis. Gate 7 reports Spearman’s rank correlation with FedLock’s published press-conference scores (raw TrueSkill mean `m`; era-adjusted `ma` as a sensitivity). It reads those scores; it does not re-run FedLock’s tournament. A separate FedLock-faithful TrueSkill replica on the 95 openings is documented in [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md).

How to read the scoreboard: [`HOW_TO_READ.md`](HOW_TO_READ.md) ([Pages](https://maybern-tripp-smith.github.io/fedjev-bench/how-to-read.html)). Long-form: [`ANALYSIS.md`](ANALYSIS.md). Gate tables: [`REPORT.md`](REPORT.md). Figures: [`results/figures/`](results/figures/). Machine-readable: [`results/gates.json`](results/gates.json) · [`results/interpretation.json`](results/interpretation.json). Gate 7 fidelity: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md). Multi-axis extension (seven criteria, `run_id` `fedjev-multiaxis-2026-09-20`): [`results/multiaxis/FINDINGS.md`](results/multiaxis/FINDINGS.md) ([Pages](https://maybern-tripp-smith.github.io/fedjev-bench/multiaxis.html)).

---

## Specification

The retrospective as-built comprehensive specification for `run_id=fedjev-2026-09-20` is recorded in [`spec.md`](spec.md).

## Offline analysis

Cached answers ship under `runs/jev/`:

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install -e .
# or: uv sync
python scripts/analyze_gates.py
python scripts/plot_figures.py
```

Do not mutate `data/pairs/gold_pairs.jsonl` for this `run_id`.

## Live re-score (optional)

Core install is enough for `score.py` and the name ablation. Optional extras: `pip install -e ".[haiku]"` for `scripts/run_haiku_comparison.py`; `pip install -e ".[fedlock]"` for `scripts/run_fedlock_replica.py`. Combine with `pip install -e ".[haiku,fedlock]"` or `uv sync --extra haiku --extra fedlock`.

```bash
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
```

## GitHub Pages

Deploy `/docs` from `main`. Site: https://maybern-tripp-smith.github.io/fedjev-bench/. Scoreboard guide: https://maybern-tripp-smith.github.io/fedjev-bench/how-to-read.html.

## Citation and license

[`CITATION`](CITATION) · MIT code · data terms in [`DATA.md`](DATA.md) (Shah CC BY-NC 4.0 not fully vendored).


## Sensitivity: length and passage filtering (Khaled / jsort)

Zero-$ length audit and a small paid `jgrep --para` → Score pilot live under [`results/khaled_sensitivity/`](results/khaled_sensitivity/). ANALYSIS §13. **Does not** mutate frozen `run_id=fedjev-2026-09-20`, raise char limits on full pressers, or re-run TrueSkill / Haiku.

If you run jsort tournaments yourself, set `--budget` high enough for completion (Khaled tip); see [`scripts/README.md`](scripts/README.md).

## FedLock-faithful protocol replica (separate)

A second experiment (`run_id` `fedjev-fedlock-replica-2026-09-20`) re-runs a FedLock-style tournament on the 95 chair openings: anonymized pairwise Choice, macro conditions attached to each text, Microsoft TrueSkill aggregation (stop when every document’s uncertainty σ < 2). Live arms are Jev (`jev-latest`) and Claude Haiku (`claude-haiku-4-5-20251001`); the third arm is published FedLock `m` / `ma` (Llama is not re-invoked). This is protocol fidelity on a 95-document corpus, not a 4,000-speech / ~60,000-comparison scale copy, and it does not replace Gate 7.

See [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md) and ANALYSIS §12. Gate 7 fidelity: [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md). Needs the `fedlock` extra (`trueskill`); the Haiku arm also needs `haiku`.

## Multi-axis TrueSkill extension (separate)

A third experiment (`run_id` `fedjev-multiaxis-2026-09-20`) ranks the same 95 openings on seven frozen criterion strings, text-only and with contemporaneous macro conditions attached. Jev only; tracked spend $1.5329. The first principal component is inflation hawkishness (50.6 percent text-only; 55.5 percent conditional). A smaller second component (19.7 / 17.0 percent) loads on forward-path and financial-conditions language. Worked example on the Pages note: 2 November 2022. Does not mutate gold for `fedjev-2026-09-20`.

See [`results/multiaxis/FINDINGS.md`](results/multiaxis/FINDINGS.md) and ANALYSIS §15. Redraw overview figures with `python scripts/plot_multiaxis_overview.py` (reads frozen CSV/JSON only).
