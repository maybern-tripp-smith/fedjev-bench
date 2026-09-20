# Data licenses & attribution

Code in this repository is MIT (`LICENSE`). Corpora are separate:

## FOMC statements / press conference openings

Source: [federalreserve.gov](https://www.federalreserve.gov/). U.S. federal government works are generally not subject to copyright in the United States. No Fed endorsement is implied. We redistribute extracted opening-statement text in `data/clean/statements.jsonl` for research reproducibility.

## FRED

Board of Governors / St. Louis Fed series via  
`https://fred.stlouisfed.org/graph/fredgraph.csv?id=…`  
(DFEDTARU, DGS2). Follow [FRED terms of use](https://fred.stlouisfed.org/legal/). CSVs under `data/raw/fred/`. No FRED API key required for these graph CSVs.

## Shah et al. — FOMC hawkish/dovish sentences

- Repo: https://github.com/gtfintechlab/fomc-hawkish-dovish  
- License: **CC BY-NC 4.0** (`data/raw/shah/LICENSE.md`)  
- Full upstream `data/` dump is **not** vendored here (see `data/raw/shah/DOWNLOAD.md`).  
- Derived `data/clean/sentences.jsonl` for this bench is for **non-commercial / research** use with attribution.

## jsort

- Repo: https://github.com/keltokhy/jsort (MIT)  
- Slim copy: `data/raw/jsort/bench/` + license (see `SLIM_COPY.md`). Label formulas for `d_same` / related fields follow `bench/fed.py`.

## FedLock

- https://jnathan9.github.io/fedlock/  
- Snapshot `data/raw/fedlock/data.json` used only for Gate 7 consistency. Respect upstream terms.

## TypeSafe / Jev

API outputs in `runs/jev/` were produced under the author’s TypeSafe account for run_id `fedjev-2026-09-20`. Re-running live calls requires your own `TYPESAFE_API_KEY`. Pricing (jev-1.13.0 era): **$0.042 per Mtok input**; output free — confirm current pricing at https://typesafe.ai.
