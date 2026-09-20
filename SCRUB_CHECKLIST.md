# Public scrub checklist (fedjev-bench)

- [x] `scripts/load_typesafe_env.py` — env-only `TYPESAFE_API_KEY` (no `/home/box` / box-secrets)
- [x] `scripts/run_haiku_comparison.py` — env-only `ANTHROPIC_API_KEY`
- [x] No `.venv/`, `__pycache__/`, `.env`
- [x] No live API keys / Bearer tokens / `sk-` / `sk-ant-` values
- [x] Shah full dump not vendored (CC-BY-NC) — attribution + `DOWNLOAD.md`
- [x] jsort slimmed to `bench/` + license (`SLIM_COPY.md`); no pdfs
- [x] Maybern customer / work-email material excluded
- [x] `.gitignore` covers `.env`, venv, secrets patterns
- [x] `LICENSE` (MIT code) + `DATA.md` + `CITATION`
- [x] README public-facing (reproduce + Pages + Haiku)
- [x] Gate 6 PASS in `results/gates.json` + `REPORT.md`
- [x] Haiku artifacts: `haiku_comparison.json`, `haiku_pair_judgments.jsonl`, cost/timing, `runs/haiku/`
- [x] `docs/` GH Pages (`.nojekyll`, index/analysis/report HTML, figures)
- [ ] **Not pushed** — parent runs `gh repo create maybern-tripp-smith/fedjev-bench --public`
