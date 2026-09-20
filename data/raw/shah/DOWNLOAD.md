# Shah FOMC hawkish-dovish — download (not vendored)

Upstream: https://github.com/gtfintechlab/fomc-hawkish-dovish  
License: **CC BY-NC 4.0** (see `LICENSE.md`).

We do **not** redistribute the full `data/` dump in this public repo.

To rebuild `data/clean/sentences.jsonl` from upstream:

```bash
git clone https://github.com/gtfintechlab/fomc-hawkish-dovish data/raw/shah-full
# then run: python scripts/prepare_sentences.py  (pointing at the clone)
```

This run_id already ships the derived `data/clean/sentences.jsonl` and frozen
`data/pairs/gold_pairs.jsonl` needed to reproduce analysis without re-download.
Derived sentence extracts inherit upstream NonCommercial terms — research/non-commercial use only.
