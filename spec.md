# fedjev-bench — Retrospective Comprehensive Specification

Repo/package name: `maybern-tripp-smith/fedjev-bench`

Description: Pre-registered scientific evaluation harness that ranks FOMC chair press-conference openings under the frozen criterion `more hawkish about inflation` using TypeSafe Jev pairwise Choice (Bradley–Terry primary; Score secondary), compares against Haiku 4.5, runs construct-validity gates 1–7, optional Experiments 3–7, a separate FedLock-faithful TrueSkill replica, and publishes static GitHub Pages from `docs/`.

**Spec status:** RETROSPECTIVE / AS-BUILT — freezes the shipped system for `run_id=fedjev-2026-09-20`.  
**Pages:** https://maybern-tripp-smith.github.io/fedjev-bench/  
**Skill:** Written against the local `comprehensive-specification` skill (`maybern-tripp-smith/maybern-skills/agent-workflow/comprehensive-specification/`); section titles match that skill’s `reference.md` §§1–22.

---

## 1. Executive Summary


**This artifact is already published.** The GitHub repository, cached run outputs, gate tables, analysis prose, and GitHub Pages site for `run_id=fedjev-2026-09-20` are live. This specification freezes the **as-built** system so another agent can reproduce offline analysis, optionally re-score with live API keys, or extend the harness without inventing protocol details.

**What shipped (categories):**

1. **Data pipeline** — FOMC openings (~95), Shah hawk/dove sentences, FRED labels (`DFEDTARU`/`L`, `DGS2`/`10`, `UNRATE`, `PCEPILFE`, plus replica macros), FedLock snapshot, frozen gold pairs.
2. **Scientific evaluation harness** — Choice both orders → Bradley–Terry → `statement_scores.csv`; Score secondary; gates 1–7 with STE/CIs; timing and cost first-class.
3. **AI-agent judgment protocol** — TypeSafe System One `jev-1.13.0` (main); Haiku 4.5 comparison; Experiments 3–7 on `jev-latest`; separate FedLock-faithful TrueSkill replica (Jev+Haiku vs published FedLock).
4. **Static GH Pages docs** — `docs/` from `main` (academic/economist audience).

**Headline as-built outcomes (do not invent; from `REPORT.md` / `results/gates.json`):**

| Item | Value |
|------|-------|
| Criterion (frozen) | `more hawkish about inflation` |
| Gate 1 inversion | **PASS** 0.000 (≤ 0.05) |
| Gate 3 Spearman vs `d_same` | **PASS** ~+0.623 all scheduled / ~+0.851 action days (signal line +0.30) |
| Gate 4 | **PASS** mean holds > mean cuts (construct-validity framing) |
| Gate 6 name ablation | **PASS** Δ inversion = 0 |
| Main cost | ≈ **$0.031**; grand with ablation ≈ **$0.042** |
| Jev pricing | **$0.042/MTok** in; out free |
| Hard non-goals | No customer Maybern data; no Grok-as-judge for main tables; no mutating frozen `gold_pairs`; no silent post-hoc exclusions |

---

## 2. Project Classification

**Category:** Data pipeline + scientific evaluation harness + AI-agent judgment protocol + static documentation site (GitHub Pages).

**Primary users:** Academic/economist readers; reproducing researchers/agents; extending agents; author.

**Jobs-to-be-done:** Reproduce offline gate analysis; optionally re-score live; extend gates/experiments without protocol drift; publish academic artifact.

**Failure modes:** Criterion/prompt drift; post-hoc pair mutation; circular labels from Jev/FedLock; secret leakage; mistaking Gate 7 for TrueSkill replication; Grok substituted as main judge.

**Definition of complete (as-built):** Frozen gold pairs + cached Jev/Haiku answers + gates 1–7 with STE + ANALYSIS/REPORT/Pages + scrubbed public repo.


Same-day federal funds target changes (`d_same`) are a convenient but **incomplete** label for the hawkishness of FOMC communication. Behavioral actions and textual stance often co-move on scheduled action days; they need not coincide on holds (`d_same = 0`) or across regimes (e.g., 2020 easing language vs 2022–23 holds with hawkish inflation language).

The measurement problem is: under a **fixed** pairwise criterion string, does a modern AI judgment stack (TypeSafe/Jev) recover (a) obvious hawk/dove document orderings, (b) rank agreement with `d_same` on action days, and (c) separation of holds from cuts on the **text** axis—where same-day funds-rate changes cannot encode hawkish- vs dovish-hold language?

Prior references (jsort published Spearman ≈ +0.46; Shah sentence labels; FedLock independent text scores) provide label algebra and external consistency checks, not a single ground-truth hawkishness index.

---

## 3. Goals

### Goals (as-built)

- Pre-register Gates 1–7 **before** any Jev output; publish pass/fail and report-only results with STE/CIs.
- Freeze gold pairs and criterion; score with strip_meta anonymization; cache by `(model, criterion, hash, order)`.
- Fit Bradley–Terry on document-level Choice (strata A+C); publish `statement_scores.csv`.
- Compare Haiku 4.5 Choice on the same gold pairs (not a substitute for main tables).
- Run Experiments 3–7 holding gold labels fixed; vary question interface.
- Run a **separate** FedLock-faithful TrueSkill replica; do **not** treat it as Gate 7.
- Publish academic prose (`ANALYSIS.md`, `REPORT.md`) and GitHub Pages.
- Scrub secrets; MIT code; document data licenses in `DATA.md`.

## 4. Non-Goals

### Hard non-goals

| Non-goal | Rationale |
|----------|-----------|
| Customer Maybern data | Public research repo; scrub checklist |
| Grok-as-judge for main tables | Main judge is Jev; Grok not in scoring path |
| Mutating `gold_pairs.jsonl` after freeze | Prevents post-hoc cherry-picking |
| Silent post-hoc exclusions | Crisis dates pre-registered; SVB flagged not dropped |
| Claiming Gate 7 = TrueSkill replication | Gate 7 is Spearman consistency only |
| Investment advice / Fed endorsement | Ethics section |

---

## 5. Users and Use Cases


| Persona | Need |
|---------|------|
| Academic / economist reader (arXiv-style) | Construct-validity framing, STE/CIs, Gate 4 interpretation |
| Reproducing agent / researcher | Offline `analyze_gates.py` from cached `runs/`; optional live re-score |
| Extending agent | This spec + frozen pairs + script inventory |
| Author (Tripp Smith) | Public MIT publish; Pages; scrub |

No end-user product UI beyond static Pages. No Maybern customer tenants.

---

## 6. Domain Research Summary


Same-day federal funds target changes (`d_same`) are a convenient but **incomplete** label for the hawkishness of FOMC communication. Behavioral actions and textual stance often co-move on scheduled action days; they need not coincide on holds (`d_same = 0`) or across regimes (e.g., 2020 easing language vs 2022–23 holds with hawkish inflation language).

The measurement problem is: under a **fixed** pairwise criterion string, does a modern AI judgment stack (TypeSafe/Jev) recover (a) obvious hawk/dove document orderings, (b) rank agreement with `d_same` on action days, and (c) separation of holds from cuts on the **text** axis—where same-day funds-rate changes cannot encode hawkish- vs dovish-hold language?

Prior references (jsort published Spearman ≈ +0.46; Shah sentence labels; FedLock independent text scores) provide label algebra and external consistency checks, not a single ground-truth hawkishness index.

---


### Success metrics (as-built)


| Metric | As-built target / observed |
|--------|----------------------------|
| Gate 1 inversion (Stratum A) | ≤ 0.05 → **PASS 0.000** |
| Gate 3 Spearman(BT, `d_same`) | ≥ +0.30 → **PASS ~+0.62 / ~+0.85 action** |
| Gate 4 mean(holds) > mean(cuts) | **PASS** |
| Gate 6 Δ inversion (names-in) | ≤ 0.05 → **PASS 0** |
| Main cost | ≈ $0.031 (observed `$0.03120352`) |
| Grand with name ablation | ≈ $0.042 |
| Timing logged | `results/timing.json` first-class |
| Secrets | Env-only; scrub checklist green for keys |
| Pages live | `/docs` from `main` |

---


### Formal definitions (summary)


### Behavioral labels (jsort-aligned; never from Jev/FedLock)

- **`d_same`** = DFEDTARU[t+1] − DFEDTARU[t−1] (same-day target change proxy).
- **`y_action`** = sign(`d_same`).
- **`d_90`** = DFEDTARU[t+90] − DFEDTARU[t].
- **`d_2y`** = DGS2[t] − DGS2[t−1].
- **Dissent counts** — scraped/refreshed into meetings labels (partial scrape acknowledged as limitation).

### Textual judgment primitives

- **Choice (primary):** Prompt maps to “Which of Text A or Text B is more hawkish about inflation”. Soft probabilities → gold-side `p_gold`. Both orders `ab`/`ba`; average. **Inversion** = averaged winner ≠ gold.
- **Score (secondary):** Five-level ordinal → continuous `score_jev` per opening.
- **Noul(s):** Multi-label primitive used in Experiment 4 (non-exclusive).
- **strip_meta:** Remove chair surnames, titles, ISO dates, and other identifying meta before judge calls.

### Ranking

- **Bradley–Terry (BT):** Fit on document-level Choice comparisons from strata **extreme + adjacent** (Shah excluded from BT graph). Outputs `score` / SE / `n_pairs` in `statement_scores.csv`. As-built: `n_statements=48`, `n_comparisons=124`, `converged=true`, `γ≈-0.1378`.

### Gates (pre-registered)

| # | Definition | Pass line |
|---|------------|-----------|
| 1 | Stratum A inversion rate (both orders averaged) | ≤ 0.05 |
| 2 | Stratum B inversion + Brier | report only |
| 3 | Spearman(BT score, `d_same`) scheduled excl crisis | ≥ +0.30 (signal); jsort pub. ref +0.46 |
| 4 | mean score holds (`d_same=0`) > mean cuts (`d_same<0`) | inequality on point means |
| 5 | Spearman vs `d_90` | secondary |
| 6 | Names-in ablation Δ inversion on A | Δ ≤ 0.05 |
| 7 | Spearman vs FedLock `m` / `ma` | report only (NOT TrueSkill replication) |

### Exclusions

- **Exclude from main analysis:** `2020-03-03`, `2020-03-15` (unscheduled / intermeeting); other `exclude_main` / `is_scheduled=false`.
- **Flag, do not drop:** `2023-03-22` (SVB) via `flag_svb`.

### Gold pair strata

| Stratum | n (as-built) | Role |
|---------|-------------:|------|
| A extreme | 40 | Certain hawk vs dove docs — Gate 1 |
| B Shah | 200 | Sentence discrimination — Gate 2 report |
| C adjacent labeled | 22 | Adjacent scheduled with nonzero Δ `d_same` |
| adjacent_unlabeled | 70 | Holds / zero Δ — not gold inversions |

---

## 7. Assumptions and Decisions


| ID | Area | Assumption / Decision | Rationale | Risk | How to Validate |
|----|------|----------------------|-----------|------|-----------------|
| A1 | Criterion | Exact string `more hawkish about inflation` is frozen for the run | Prevents prompt drift | Semantic mismatch vs other hawkishness defs | Grep `CRITERION` in `score.py`; match `gates.json` |
| A2 | Labels | `d_same`, `y_action`, `d_90`, dissent, `d_2y` never come from Jev/FedLock | Avoid circularity | Label scrape errors | Rebuild from FRED via `prepare_meetings_labels.py` |
| A3 | Pairs | Strata A(~40)/B(~200)/C(adjacent labeled) frozen before scoring | Pre-registration integrity | Wrong gold | `PAIR_MANIFEST.md`; do not regenerate |
| A4 | Choice | Both orders; average; strip_meta | Order bias / name leakage | Residual leakage | Gate 6 name ablation; order-flip rates |
| A5 | Ranking | Bradley–Terry primary from A+C Choice; Score secondary | Document-level ranking claim | Sparse graph | `bt_fit` in `gates.json` |
| A6 | Exclusions | Drop 2020-03-03/15 unscheduled; flag SVB 2023-03-22 | Crisis confounding | Over/under exclusion | `CRISIS`/`SVB` in `analyze_gates.py` |
| A7 | Gate 7 | Report-only Spearman vs FedLock `m`/`ma`; NOT TrueSkill replica | Different construct check | Misread as replication | `fedlock_fidelity.md` |
| A8 | Replica | Separate TrueSkill run does not replace Gate 7 | Protocol fidelity vs main claim | Confusion in prose | ANALYSIS §12 vs §6 |
| A9 | Secrets | `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY` env only | Public scrub | Accidental commit | `SCRUB_CHECKLIST.md`; `.gitignore` |
| A10 | Judge | Main tables = Jev; Haiku comparison adjunct; no Grok judge | Stated protocol | Drift | README / REPORT |
| A11 | Pricing | Jev $0.042/MTok in, out free | Cost accounting | Price change | Confirm typesafe.ai; `cost.json` |
| A12 | Audience | Academic/economist prose; STE/CIs | Publication tone | Overclaim | ANALYSIS Abstract |

---

## 8. Functional Requirements


| ID | Requirement | Priority | Details | Acceptance Criteria | Verification |
|----|-------------|----------|---------|---------------------|--------------|
| FR1 | Data preparation | P0 | `prepare_statements`, `prepare_sentences`, `prepare_meetings_labels`, `refresh_dissents` | Clean JSONL/parquet exist; ~95 statements; labels present | `wc -l data/clean/statements.jsonl`; `ls data/labels/` |
| FR2 | Gold pairs | P0 | `build_gold_pairs`; strata A/B/C + adjacent_unlabeled | 262 gold pairs; manifest freeze note | `wc -l data/pairs/gold_pairs.jsonl`; read `PAIR_MANIFEST.md` |
| FR3 | Meta strip | P0 | `strip_meta` removes names/dates/titles before judge | API calls use stripped text | Unit: run `strip_meta` on sample; Gate 6 |
| FR4 | Jev Choice+Score | P0 | `score.py`; cache; both orders; Score pass | `runs/jev/answers.jsonl`; judgments; cost | `python score.py` offline path; `results/cost.json` |
| FR5 | BT + gates | P0 | `analyze_gates.py` → scores + gates 1–7 | `statement_scores.csv`, `gates.json` | `python scripts/analyze_gates.py` |
| FR6 | Haiku comparison | P1 | `run_haiku_comparison.py` | `haiku_comparison.json` complete | Compare inversion tables to REPORT |
| FR7 | Name ablation | P0 | `run_name_ablation.py` Gate 6 | Δ ≤ 0.05 recorded | `results/name_ablation.json` |
| FR8 | Experiments 3–7 | P1 | `run_experiments_3_7.py` | Artifacts under `results/experiments/` | Read `SUMMARY.json` / FINDINGS |
| FR9 | FedLock replica | P1 | `run_fedlock_replica.py` TrueSkill | `results/fedlock_replica/` | FINDINGS + agreement.json |
| FR10 | Figures | P1 | `plot_figures.py`, `make_publication_figures.py` | PNGs in `results/figures` + `docs/figures` | `ls docs/figures` |
| FR11 | Pages | P0 | `render_docs.py`; deploy `/docs` | Live site | Open Pages URL |
| FR12 | Scrub/publish | P0 | Env keys; checklist; MIT + DATA.md | No secrets in tree | `SCRUB_CHECKLIST.md`; secret scan |

---

## 9. Non-Functional Requirements


| ID | Requirement | Default / as-built |
|----|-------------|--------------------|
| NFR1 | Cost transparency | Every answer logs tokens; `cost.json` / experiment SUMMARY |
| NFR2 | Latency transparency | Per-call `latency_ms`; `timing.json` (concurrency 6) |
| NFR3 | Reproducibility | Cached answers ship; offline analyze without keys |
| NFR4 | Determinism of pairs | Seed `20260920` for Stratum B; freeze note |
| NFR5 | Academic tone | STE/CIs; construct-validity Gate 4; no overclaim on Gate 7 |
| NFR6 | License hygiene | MIT code; Shah CC BY-NC attribution; no full Shah dump |
| NFR7 | Concurrency | Default `--concurrency 6` in `score.py` |
| NFR8 | Idempotent scoring | Cache by `(model, criterion, hash, order)` |

---

## 10. System Architecture


**In scope:** public corpora listed in `DATA.md`; scripts under `scripts/` + root `score.py`; results under `results/`; runs under `runs/`; docs under `docs/`.

**Out of scope:** Maybern product code; customer fund data; full Shah dump vendoring; Llama re-invocation for FedLock; causal identification of communication effects.

**Categories (architecture lanes):**

```
[raw corpora] → prepare_* → clean + labels → build_gold_pairs (FROZEN)
                                                    ↓
                              score.py / run_* (Jev, Haiku, exps, replica)
                                                    ↓
                              analyze_gates + figures + render_docs → Pages
```

---



```
data/raw/{fred,shah,jsort,fedlock,...}
        │
        ▼
scripts/prepare_*.py  ──► data/clean/* , data/labels/meetings.parquet
        │
        ▼
scripts/build_gold_pairs.py ──► data/pairs/gold_pairs.jsonl (FROZEN)
        │
        ├─► score.py (Jev Choice+Score) ──► runs/jev/ + results/pair_judgments.jsonl
        ├─► run_name_ablation.py ──► Gate 6
        ├─► run_haiku_comparison.py ──► runs/haiku/ + haiku_*
        ├─► run_experiments_3_7.py ──► results/experiments/
        └─► run_fedlock_replica.py ──► results/fedlock_replica/
        │
        ▼
scripts/analyze_gates.py ──► statement_scores.csv, gates.json, interpretation.json
        │
        ▼
plot_figures / make_publication_figures / render_docs ──► docs/ → GH Pages
```

**Models:**

- Main gates: `jev-1.13.0` (TypeSafe System One).
- Experiments 3–7 + replica Jev arm: `jev-latest`.
- Comparison / replica: `claude-haiku-4-5-20251001`.

---

## 11. Repository Structure

```
fedjev-bench/
  README.md, REPORT.md, ANALYSIS.md, DATA.md, CITATION, LICENSE, SCRUB_CHECKLIST.md, spec.md
  score.py
  scripts/
    prepare_statements.py, prepare_sentences.py, prepare_meetings_labels.py, refresh_dissents.py
    build_gold_pairs.py, strip_meta.py, load_typesafe_env.py
    analyze_gates.py, run_name_ablation.py, run_haiku_comparison.py
    run_experiments_3_7.py, run_fedlock_replica.py
    plot_figures.py, make_publication_figures.py, render_docs.py
  data/raw/{jsort,shah,fred,fedlock}/
  data/clean/  data/labels/  data/pairs/
  runs/jev/  runs/haiku/  runs/fedlock_replica/
  results/  results/experiments/  results/fedlock_replica/  results/figures/
  docs/  docs/figures/
```

As-built tree matches this layout; do not mutate `data/pairs/gold_pairs.jsonl` for `run_id=fedjev-2026-09-20`.

## 12. Data Model


| Path | Role | Mutability |
|------|------|------------|
| `data/clean/statements.jsonl` | ~95 chair openings | Stable for run |
| `data/clean/sentences.jsonl` | Shah-derived | Stable; CC BY-NC terms |
| `data/labels/meetings.parquet` | Behavioral labels | Rebuildable from FRED |
| `data/pairs/gold_pairs.jsonl` | 262 gold pairs | **FROZEN** for run_id |
| `data/pairs/adjacent_unlabeled.jsonl` | 70 holds/zero-Δ | Frozen adjunct |
| `data/pairs/PAIR_MANIFEST.md` | Construction rules | Frozen note |
| `data/raw/fedlock/data.json` | Gate 7 + replica published scores | Snapshot |
| `data/raw/fred/` | DFEDTARU, DGS2, UNRATE, PCEPILFE, VIXCLS, GDPC1, … | Regenerable |
| `runs/jev/answers.jsonl` | Cached main answers | Append-only cache |
| `results/statement_scores.csv` | BT + score_jev | Derived |
| `results/gates.json` | Machine-readable gates | Derived |

**Default:** Do not mutate gold pairs after freeze. New runs need a new `run_id`.

---

## 13. Interfaces


### Choice cache key

`cache_key(model, criterion, hash_a, hash_b, order)` where hashes are of **stripped** texts.

### Aggregation

1. For each gold pair, collect Choice for `ab` and `ba`.
2. Map soft probs to gold side; average → winner / `p_gold` / Brier.
3. BT fit on extreme+adjacent document comparisons → per-statement `score`.
4. Score pass → `score_jev` for openings (n≈93–95 in tables).

### Gate formulas (implementation in `analyze_gates.py`)

- Inversion rate = (# inverted pairs) / n; binomial STE.
- Spearman with bootstrap STE and percentile 95% CI (`n_boot=1000`, seed `20260920`).
- Gate 4: compare mean BT (and score_jev) for holds vs cuts; report STE of means and gap.

### FedLock replica (separate)

- Macro-conditioned hawkishness Choice; TrueSkill μ₀=50, σ₀=8.33; stop all σ<2 or ~30 comps/doc (cap 2850).
- Swiss uncertainty pairing; soft outcome interpolation.
- Does **not** replace Gate 7.

---



### Offline analysis (default)

```bash
git clone https://github.com/maybern-tripp-smith/fedjev-bench
cd fedjev-bench
python -m venv .venv && source .venv/bin/activate
pip install typesafe-sdk pandas pyarrow openpyxl scipy matplotlib
python scripts/analyze_gates.py
```

### Live re-score (optional)

```bash
export TYPESAFE_API_KEY=...          # never commit
export ANTHROPIC_API_KEY=...         # only for Haiku paths
python score.py --live --full
python scripts/run_name_ablation.py --live
python scripts/analyze_gates.py
python scripts/run_haiku_comparison.py   # optional
python scripts/run_experiments_3_7.py    # optional
python scripts/run_fedlock_replica.py    # optional; separate
python scripts/make_publication_figures.py
python scripts/render_docs.py
```

### Env template

See `.env.example` — `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY` only.

---

## 14. Feature Specifications


### F-DATA — Data prep

- **Inputs:** Fed site openings; Shah upstream (download instructions, not full dump); FRED graph CSVs; jsort slim `bench/`; FedLock snapshot.
- **Outputs:** clean JSONL, meetings parquet/csv.
- **Scripts:** `prepare_statements.py`, `prepare_sentences.py`, `prepare_meetings_labels.py`, `refresh_dissents.py`.
- **Acceptance:** statements count 95; labels joinable by meeting date.

### F-PAIRS — Gold pairs

- **Script:** `build_gold_pairs.py`.
- **Rules:** See `PAIR_MANIFEST.md` (A certain extremes; B seed 20260920; C labeled adjacent).
- **Acceptance:** 40+200+22=262; freeze note present.
- **Forbidden:** regenerate after Jev scoring for this run_id.

### F-JEV — Jev scoring

- **Script:** `score.py` (+ `load_typesafe_env.py`).
- **Modes:** smoke / full; live requires `TYPESAFE_API_KEY`.
- **Acceptance:** 524 Choice + 95 Score class calls in main accounting; `cost.json` total ≈ $0.03120352.

### F-GATES — BT + gates

- **Script:** `analyze_gates.py`.
- **Acceptance:** Gates 1/3/4/6 pass flags true; 2/5/7 report; STE fields present.

### F-HAIKU — Haiku compare

- **Script:** `run_haiku_comparison.py`; env `ANTHROPIC_API_KEY`.
- **Acceptance:** 262 pairs / 524 calls; A inversion 0; cost ≈ $0.636; mean latency ≈ 676 ms vs Jev Choice ≈ $0.024 / ≈ 207 ms.

### F-EXP — Experiments 3–7

| Exp | Probe | As-built headline |
|-----|-------|-------------------|
| 3 | Composite Scores | vs `d_same` ρ≈0.562; tight with `score_jev` / FedLock `m` |
| 4 | Multi-Nouls | SVB banking stress ≈0.99; multi-Noul mass noted |
| 5 | Calibration/paraphrase | Stratum A inv=0 across paraphrases |
| 6 | Span Choice | Near chance (inv≈0.48) under distractor design |
| 7 | Macro-relative | Macro vs absolute winner agreement 1.0 on A |

Suite cost ≈ **$0.04452752** (385 calls).

### F-REPLICA — FedLock-faithful TrueSkill

- **Script:** `run_fedlock_replica.py`.
- **Acceptance:** FINDINGS + agreement (Jev↔FedLock m Spearman ≈ +0.965 on n=92); separate run_id `fedjev-fedlock-replica-2026-09-20`.

### F-FIG — Publication figures

- **Scripts:** `plot_figures.py`, `make_publication_figures.py`.
- **Acceptance:** Gate and experiment figures under `docs/figures/` with captions.

### F-PAGES — GitHub Pages

- **Script:** `render_docs.py`; site from `/docs` on `main`.
- **Acceptance:** index/analysis/report HTML + `.nojekyll`.

### F-SCRUB — Scrub / publish

- **Doc:** `SCRUB_CHECKLIST.md`.
- **Acceptance:** no keys; Shah not fully vendored; MIT + DATA.md + CITATION.

---

## 15. Testing and Verification Plan


| Check | Command / evidence | Expected |
|-------|--------------------|----------|
| Gates regenerate | `python scripts/analyze_gates.py` | Matches `REPORT.md` within float noise |
| Gate JSON keys | Inspect `results/gates.json` | `1_easy_pair_inversion` … `7_fedlock_consistency` |
| Pair freeze | `wc -l data/pairs/gold_pairs.jsonl` | 262 |
| Statements | `wc -l data/clean/statements.jsonl` | 95 |
| Criterion grep | `rg "more hawkish about inflation" score.py results/gates.json` | Exact match |
| Crisis exclusions | Code `CRISIS` set | 2020-03-03/15 |
| SVB flag | `SVB=2023-03-22` | Flagged not dropped |
| Pages | Browse Pages URL | HTML renders |
| Secrets | Scrub checklist + ignore | Clean |

---

## 16. Build, Packaging, and Deployment

### Packaging
- Public GitHub repo `maybern-tripp-smith/fedjev-bench` (MIT).
- Cached answers under `runs/` ship for offline analysis.

### Deployment
- GitHub Pages: source `main` `/docs`.
- Regenerate HTML: `python scripts/render_docs.py` then push.
- Site: https://maybern-tripp-smith.github.io/fedjev-bench/

### Live re-score (optional)
```bash
export TYPESAFE_API_KEY=...   # never commit
python score.py --live --full
python scripts/analyze_gates.py
```


| Surface | Path / URL |
|---------|------------|
| Long-form analysis | `ANALYSIS.md` |
| Gate report | `REPORT.md` |
| Data licenses | `DATA.md` |
| Citation | `CITATION` |
| Scrub | `SCRUB_CHECKLIST.md` |
| This spec | `spec.md` |
| Pages | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| FedLock fidelity | `results/fedlock_fidelity.md` |
| Experiments findings | `results/experiments/FINDINGS.md` |
| Replica findings | `results/fedlock_replica/FINDINGS.md` |

**Prose defaults:** academic/economist; STE/CIs; Gate 4 = construct validity of incomplete behavioral labels under holds; Gate 7 ≠ methodological replication.

---

## 17. Security and Privacy


| Rule | Implementation |
|------|----------------|
| Keys via env only | `load_typesafe_env.py`; Haiku script env read |
| Never commit keys | `.gitignore` `.env`, secrets globs |
| No box-secrets coupling | Scrub checklist item |
| No customer data | Explicit non-goal |
| Shah license | Attribution; non-commercial; DOWNLOAD.md |

**Verification:** walk `SCRUB_CHECKLIST.md`; `rg` for `sk-` / `sk-ant-` / Bearer tokens must find none in tracked files.

---

## 18. Observability and Operations


| Artifact | Contents |
|----------|----------|
| `results/cost.json` | Tokens, USD, by stratum; main total `$0.03120352` |
| `results/timing.json` | n=619; mean≈214 ms; p50≈202; concurrency 6 |
| `results/name_ablation.json` | Add-on ≈ `$0.011` → grand ≈ `$0.042` |
| `results/haiku_cost.json` / comparison | ≈ `$0.636` |
| `results/experiments/SUMMARY.json` | ≈ `$0.04452752` |
| `results/fedlock_replica/cost_performance.json` | Jev ≈ `$0.14` / Haiku ≈ `$3.59` for replica arms |
| Per-answer logs | tokens + `latency_ms` in answers JSONL |

**Default:** Treat cost/latency as accounting facts, not accuracy claims.

---

## 19. Documentation Plan


| Surface | Path / URL |
|---------|------------|
| Long-form analysis | `ANALYSIS.md` |
| Gate report | `REPORT.md` |
| Data licenses | `DATA.md` |
| Citation | `CITATION` |
| Scrub | `SCRUB_CHECKLIST.md` |
| This spec | `spec.md` |
| Pages | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| FedLock fidelity | `results/fedlock_fidelity.md` |
| Experiments findings | `results/experiments/FINDINGS.md` |
| Replica findings | `results/fedlock_replica/FINDINGS.md` |

**Prose defaults:** academic/economist; STE/CIs; Gate 4 = construct validity of incomplete behavioral labels under holds; Gate 7 ≠ methodological replication.

---

## 20. Implementation Task Checklist


> Retrospective: shipped tasks marked **[x] DONE**. Remaining honest **[ ]** items are P2 polish / hygiene only.

### T-01 — Data pipeline (statements, sentences, labels)
- **Type:** Data
- **Priority:** P0
- **Dependencies:** none
- **Description:** Build clean openings, Shah sentences, FRED/jsort labels, dissent refresh.
- **Files:** `scripts/prepare_*.py`, `scripts/refresh_dissents.py`, `data/clean/`, `data/labels/`, `data/raw/`
- **Acceptance:** 95 statements; meetings labels joinable; DATA.md attribution present.
- **Verification:** `wc -l data/clean/statements.jsonl`; `ls data/labels/meetings.parquet`
- **Completion evidence:** [x] DONE — corpora shipped in repo for `fedjev-2026-09-20`.

### T-02 — Freeze gold pairs
- **Type:** Data
- **Priority:** P0
- **Dependencies:** T-01
- **Description:** Build strata A/B/C + adjacent_unlabeled; write PAIR_MANIFEST freeze note.
- **Files:** `scripts/build_gold_pairs.py`, `data/pairs/*`
- **Acceptance:** 262 gold pairs; seed 20260920 for B; freeze before Jev.
- **Verification:** `wc -l data/pairs/gold_pairs.jsonl`; read manifest.
- **Completion evidence:** [x] DONE — frozen pairs committed.

### T-03 — strip_meta + Jev Choice/Score scoring
- **Type:** Feature
- **Priority:** P0
- **Dependencies:** T-02
- **Description:** Implement strip_meta, score.py cache, both-order Choice, Score pass, cost/timing logs.
- **Files:** `scripts/strip_meta.py`, `score.py`, `scripts/load_typesafe_env.py`, `runs/jev/`
- **Acceptance:** Cached answers; cost ≈ $0.031; criterion exact.
- **Verification:** `results/cost.json`; `results/timing.json`
- **Completion evidence:** [x] DONE — main run complete.

### T-04 — Bradley–Terry + gates 1–7
- **Type:** Feature
- **Priority:** P0
- **Dependencies:** T-03
- **Description:** Fit BT; compute gates with STE/CIs; write REPORT fields.
- **Files:** `scripts/analyze_gates.py`, `results/gates.json`, `results/statement_scores.csv`, `REPORT.md`
- **Acceptance:** Gates 1/3/4/6 PASS; 2/5/7 report-only semantics.
- **Verification:** `python scripts/analyze_gates.py`; diff key metrics to REPORT.
- **Completion evidence:** [x] DONE — `gates.json` run_id `fedjev-2026-09-20`.

### T-05 — Name ablation (Gate 6)
- **Type:** Feature
- **Priority:** P0
- **Dependencies:** T-03
- **Description:** Re-score Stratum A with names-in; Δ inversion ≤ 0.05.
- **Files:** `scripts/run_name_ablation.py`, `results/name_ablation.json`
- **Acceptance:** PASS Δ=0; cost add-on ≈ $0.011.
- **Verification:** Inspect `name_ablation.json` `pass` / `inversion_delta`.
- **Completion evidence:** [x] DONE.

### T-06 — Haiku 4.5 comparison
- **Type:** Feature
- **Priority:** P1
- **Dependencies:** T-02
- **Description:** Same gold pairs Choice comparison; cost/timing/inversion tables.
- **Files:** `scripts/run_haiku_comparison.py`, `results/haiku_*`, `runs/haiku/`
- **Acceptance:** Complete status; A inv=0; artifacts present.
- **Verification:** `results/haiku_comparison.json` `status=complete`
- **Completion evidence:** [x] DONE.

### T-07 — Experiments 3–7
- **Type:** Feature
- **Priority:** P1
- **Dependencies:** T-02
- **Description:** Composite Scores, multi-Nouls, paraphrase/calibration, span Choice, macro-relative.
- **Files:** `scripts/run_experiments_3_7.py`, `results/experiments/`, ANALYSIS §11
- **Acceptance:** SUMMARY + FINDINGS; gold labels fixed.
- **Verification:** `results/experiments/SUMMARY.json`
- **Completion evidence:** [x] DONE.

### T-08 — FedLock-faithful TrueSkill replica
- **Type:** Feature
- **Priority:** P1
- **Dependencies:** T-01, strip_meta
- **Description:** Macro-conditioned TrueSkill tournament Jev+Haiku vs published FedLock; separate from Gate 7.
- **Files:** `scripts/run_fedlock_replica.py`, `results/fedlock_replica/`, ANALYSIS §12
- **Acceptance:** FINDINGS published; agreement metrics; fidelity notes.
- **Verification:** Read `results/fedlock_replica/FINDINGS.md`
- **Completion evidence:** [x] DONE (as-built artifacts present; ensure Mac/main tip includes replica commits if any lag).

### T-09 — Publication figures + Pages
- **Type:** Docs
- **Priority:** P0
- **Dependencies:** T-04, T-07, T-08
- **Description:** Generate figures; render docs HTML; deploy `/docs` from main.
- **Files:** `scripts/plot_figures.py`, `make_publication_figures.py`, `render_docs.py`, `docs/`
- **Acceptance:** Pages URL serves analysis/report/figures.
- **Verification:** Open https://maybern-tripp-smith.github.io/fedjev-bench/
- **Completion evidence:** [x] DONE.

### T-10 — Public scrub + license pack
- **Type:** Release
- **Priority:** P0
- **Dependencies:** all scoring
- **Description:** Env-only keys; MIT; DATA.md; CITATION; gitignore; no customer data.
- **Files:** `SCRUB_CHECKLIST.md`, `LICENSE`, `DATA.md`, `CITATION`, `.gitignore`, `.env.example`
- **Acceptance:** Checklist items for secrets green.
- **Verification:** Manual scrub + `rg` secret patterns.
- **Completion evidence:** [x] DONE for secrets/licenses. 

### T-11 — Retrospective comprehensive specification
- **Type:** Docs
- **Priority:** P0
- **Dependencies:** T-01…T-10
- **Description:** Write this `spec.md`; link from README.
- **Files:** `spec.md`, `README.md`
- **Acceptance:** Sections 1–22 present; pushed to main.
- **Verification:** `rg -n '^## [0-9]+\.' spec.md`
- **Completion evidence:** [x] DONE when this file lands on `main`.

### T-12 — Scrub checklist stale “Not pushed” row
- **Type:** Docs
- **Priority:** P2
- **Dependencies:** T-10
- **Description:** Update `SCRUB_CHECKLIST.md` final unchecked “Not pushed” item now that the public repo exists.
- **Files:** `SCRUB_CHECKLIST.md`
- **Acceptance:** Checklist reflects published state.
- **Verification:** Read checklist footer.
- **Completion evidence:** [ ] P2 remaining — honest gap; repo is public but checklist line may still say not pushed.

### T-13 — Partial dissent scrape hardening
- **Type:** Data
- **Priority:** P2
- **Dependencies:** T-01
- **Description:** Improve dissent coverage called out as limitation in ANALYSIS.
- **Files:** `scripts/refresh_dissents.py`, labels
- **Acceptance:** Documented coverage metrics.
- **Verification:** ANALYSIS limitations vs label null rates.
- **Completion evidence:** [ ] P2 remaining — acknowledged limitation, not blocking published gates.

---

## 21. Final Definition of Done

The project is complete for `run_id=fedjev-2026-09-20` when all of the following hold (as-built: true unless noted):

- All P0/P1 functional requirements implemented and verified.
- Gates 1–7 computed into `results/gates.json` with STE/CIs where applicable.
- Cached runs enable offline `python scripts/analyze_gates.py`.
- ANALYSIS/REPORT/Pages use academic/economist register; Gate 4 framed as construct validity; Gate 7 not claimed as TrueSkill replication.
- Secrets scrubbed; MIT + DATA.md licenses documented.
- Cost and timing published (`results/cost.json`, `results/timing.json`).

### Anti-partial-implementation rules (binding on extending agents)


1. **No silent protocol changes.** Criterion string, gold pairs, and gate pass lines are frozen for `fedjev-2026-09-20`. A new experiment gets a new `run_id`.
2. **No partial gate reporting.** If regenerating analysis, emit all gates 1–7 with STE fields; do not drop failures.
3. **No unlabeled exclusions.** Crisis dates and SVB flagging must remain explicit in code and prose.
4. **No judge substitution in main tables.** Do not replace Jev with Grok/Haiku for Gates 1/3/4/6 headlines without a new registered protocol.
5. **Gate 7 ≠ replica.** Publishing TrueSkill replica metrics must not rewrite Gate 7 semantics.
6. **Cache honesty.** Live re-scores must preserve cache key identity; do not mix models under one cache namespace.
7. **Secrets.** Never commit API keys; never read keys from box-secrets into public tree.
8. **Verification mandatory.** A task is not done without the listed verification command/evidence.
9. **Bias to explicit defaults.** Prefer documented defaults (concurrency 6, seed 20260920, both orders, strip_meta on) over implicit behavior.
10. **Completeness over demo path.** Stratum B report-only and span-Choice near-chance results stay published; do not hide negative/null results.

---

## 22. Final Handoff Report Template


### 22.A As-built handoff (retrospective completed)

| Field | Content |
|-------|---------|
| **Project** | fedjev-bench |
| **run_id** | `fedjev-2026-09-20` |
| **Status** | SHIPPED / PUBLIC |
| **Repo** | https://github.com/maybern-tripp-smith/fedjev-bench |
| **Pages** | https://maybern-tripp-smith.github.io/fedjev-bench/ |
| **Mac path** | `/Users/tripp/Desktop/dev/maybern-tripp-smith/fedjev-bench` |
| **Criterion** | `more hawkish about inflation` |
| **Model (gates)** | jev-1.13.0 |
| **Gates** | 1 PASS · 3 PASS · 4 PASS · 6 PASS; 2/5/7 report |
| **Main cost** | ≈ $0.03120352; grand w/ ablation ≈ $0.042 |
| **Key artifacts** | `results/gates.json`, `statement_scores.csv`, `ANALYSIS.md`, `REPORT.md`, `results/experiments/`, `results/fedlock_replica/` |
| **Do not** | Mutate gold_pairs; use Grok for main tables; treat Gate 7 as TrueSkill replication; commit secrets |
| **Next agent entry** | Offline: `python scripts/analyze_gates.py`. Extend: new run_id + this spec §8/§14 |
| **Honest gaps** | T-12 checklist stale line; T-13 dissent coverage P2; sparse BT graph / openings≠full pressers (documented limitations) |

### 22.B Blank template (for future runs)

Copy for a new `run_id`:

```markdown
# Handoff — fedjev-bench / run_id=<NEW>

## Outcome
- [ ] PASS / FAIL / BLOCKED — one sentence.

## What changed
- Criterion:
- Pairs freeze commit:
- Models:
- Gates regenerated: yes/no

## Evidence
- gates.json path + SHA:
- cost.json total:
- timing.json summary:
- Pages URL refreshed: yes/no

## Decisions locked
- |

## Open risks
- |

## Verification commands run
```bash
python scripts/analyze_gates.py
rg -n '^## [0-9]+\.' spec.md
```

## Next actions (ordered)
1.
2.

## Secrets check
- [ ] No keys committed
```

---

*End of retrospective comprehensive specification for fedjev-bench (`fedjev-2026-09-20`).*

