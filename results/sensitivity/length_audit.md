# Length audit vs jsort default 8,000 characters

**Corpus.** Chair openings in `data/clean/statements.jsonl` (`text` field), n=95.

| Statistic | Value |
|-----------|------:|
| Mean | 7917 |
| p50 | 7547 |
| p90 | 10823 |
| p95 | 11706 |
| Max | 13794 |
| n > 8,000 | **39** (41.1%) |

**Did the published main run truncate?** **No.** `run_id=fedjev-2026-09-20` Score/Choice used full stripped openings (no 8k client cap). The 8k default is a **jsort/jgrep design choice**; binding for 39/95 openings if you re-rank with those tools’ defaults.

**Machine-readable.** [`char_length_audit.json`](../khaled_sensitivity/char_length_audit.json) (canonical) · this file is a short pointer.

Credit: Khaled (@eltokh7 / jsort) tip on `--max-chars` / `jgrep --para` / `--budget`.
