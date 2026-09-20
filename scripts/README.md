# Scripts

## Main frozen run (`run_id=fedjev-2026-09-20`)

- `analyze_gates.py` — offline gates from cached answers
- `plot_figures.py` / `make_publication_figures.py` / `render_docs.py` — figures and Pages HTML
- `score.py` (repo root) — live Choice + Score for the main protocol

Do not mutate `data/pairs/gold_pairs.jsonl` for this `run_id`.

## Khaled / jsort sensitivity (does not change frozen protocol)

- `audit_char_lengths.py` — zero-$ audit of opening lengths vs jsort default `--max-chars 8000`
- `run_khaled_filter_pilot.py` — ~25-meeting `jgrep --para` filter → Score pilot

### Budget tip (Khaled / jsort)

When running **jev-sort / jsort** tournaments (or long `jgrep` jobs), set an explicit `--budget` high enough that the run completes rather than stopping mid-tournament. Khaled’s tip: jsort’s default budget can halt ranking early; prefer `--budget 0` (no dollar cap) or a deliberately large dollar cap for full completion, and prefer filtering with `jgrep --para "…"` before sorting when the corpus is long. This bench’s main TrueSkill replica already used explicit completion criteria; do not silently re-run it when only auditing length or passage filters.

Example:

```bash
# Prefer para-filter then sort (Khaled)
jgrep --para "states a view on inflation or the stance of monetary policy" openings.txt > filtered.txt
jsort --para "more hawkish about inflation" --budget 0 filtered.txt

# Length audit (free)
python scripts/audit_char_lengths.py

# Filter pilot (~$0.005 on 25 action-day openings; seed 20260920)
python scripts/run_khaled_filter_pilot.py --live
```
