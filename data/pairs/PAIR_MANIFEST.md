# PAIR_MANIFEST — frozen gold pairs

**run_id:** `fedjev-2026-09-20`  
**frozen:** before any TypeSafe/Jev call  
**seed (Stratum B):** `20260920`  
**freeze note:** Pairs locked for fedjev-2026-09-20. Do not regenerate after Jev scoring begins.

## Counts

| Stratum | source | n | file |
|---------|--------|--:|------|
| A — extreme document pairs | extreme | 40 | gold_pairs.jsonl |
| B — Shah hawkish vs dovish sentences | shah | 200 | gold_pairs.jsonl |
| C — adjacent scheduled statements (labeled) | adjacent | 22 | gold_pairs.jsonl |
| Unlabeled adjacents (holds vs holds / zero Δ) | — | 70 | adjacent_unlabeled.jsonl |
| **Total gold pairs** | | **262** | |

## Construction rules

### A (certain, must-not-invert)
- 50–75 bp hike statements (2022-06, 07, 09, 11) vs Mar 2020–Jan 2021 easing/hold-at-zero
- Explicit: 2022-11-02 vs 2020-03-15; 2022-09-21 vs 2020-04-29; latest hike vs 2020-03-15
- Cap 40; gold = hike/hawk side (`a`)

### B
- Hawkish vs dovish only (Shah labels 1 vs 0); no neutrals
- Random pairs, seed 20260920, cap 200; gold = hawkish id as `a`

### C
- Consecutive *scheduled* meetings with opening statements in corpus
- Gold only when sign(d_same[t] − d_same[t−1]) ≠ 0; higher d_same → more hawkish
- Zero-diff pairs → adjacent_unlabeled.jsonl

## Latest hike in corpus
- requested: 2026-09-16 (raise toward 3.75–4.00)
- resolved latest_hike doc: `2026-09-16`
- present in statements.jsonl: `True`

## Hike / ease pools used for A
- hike_dates (4): 2022-06-15, 2022-07-27, 2022-09-21, 2022-11-02
- ease_dates n=9 (Mar 2020–Jan 2021)
