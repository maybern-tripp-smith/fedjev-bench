"""Freeze gold pairs for run_id fedjev-2026-09-20 BEFORE any Jev call."""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
LABELS = ROOT / "data" / "labels"
PAIRS = ROOT / "data" / "pairs"
RUN_ID = "fedjev-2026-09-20"
SEED = 20260920

# Explicit must-include extreme pairs (hike doc vs ease/zero doc)
EXPLICIT = [
    ("2022-11-02", "2020-03-15"),
    ("2022-09-21", "2020-04-29"),
]


def load_statements() -> dict[str, dict]:
    out = {}
    with (CLEAN / "statements.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            out[r["date"]] = r
    return out


def load_sentences() -> list[dict]:
    rows = []
    with (CLEAN / "sentences.jsonl").open() as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    PAIRS.mkdir(parents=True, exist_ok=True)
    stmts = load_statements()
    labels = pd.read_csv(LABELS / "meetings.csv")
    labels["date"] = labels["date"].astype(str)
    by_date = labels.set_index("date")

    # --- Stratum A: extreme document pairs ---
    hike_dates = []
    for d in ["2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02"]:
        if d in stmts and d in by_date.index:
            ds = by_date.loc[d, "d_same"]
            # 50-75 bp = 0.50 to 0.75
            if pd.notna(ds) and 0.50 - 1e-9 <= float(ds) <= 0.75 + 1e-9:
                hike_dates.append(d)
            elif d in stmts:
                hike_dates.append(d)  # still known 75bp meetings even if label gap

    ease_dates = []
    for d, row in stmts.items():
        if d < "2020-03-01" or d > "2021-01-31":
            continue
        if d not in by_date.index:
            ease_dates.append(d)
            continue
        ds = by_date.loc[d, "d_same"]
        # easing or hold-at-zero
        if pd.isna(ds) or float(ds) <= 0:
            ease_dates.append(d)

    # Ensure Mar 2020 – Jan 2021 corpus dates present
    for d in list(stmts):
        if "2020-03-01" <= d <= "2021-01-31" and d not in ease_dates:
            ease_dates.append(d)
    ease_dates = sorted(set(ease_dates))
    hike_dates = sorted(set(hike_dates) & set(stmts))

    # Latest hike: prefer 2026-09-16 if present, else latest positive d_same
    latest_hike = None
    if "2026-09-16" in stmts:
        latest_hike = "2026-09-16"
    else:
        cand = []
        for d, row in by_date.iterrows():
            if d in stmts and pd.notna(row["d_same"]) and float(row["d_same"]) > 0:
                cand.append((d, float(row["d_same"])))
        if cand:
            latest_hike = sorted(cand)[-1][0]

    gold_a = []
    seen = set()

    def add_a(hawk_date: str, dove_date: str, note: str = ""):
        if hawk_date not in stmts or dove_date not in stmts:
            return False
        key = (hawk_date, dove_date)
        if key in seen:
            return False
        seen.add(key)
        pid = f"A{len(gold_a)+1:03d}"
        gold_a.append(
            {
                "pair_id": pid,
                "a": stmts[hawk_date]["doc_id"],
                "b": stmts[dove_date]["doc_id"],
                "gold": "a",
                "source": "extreme",
                "confidence": "certain",
                "hawk_date": hawk_date,
                "dove_date": dove_date,
                "note": note,
            }
        )
        return True

    for h, e in EXPLICIT:
        add_a(h, e, "explicit")
    if latest_hike:
        add_a(latest_hike, "2020-03-15", "latest_hike_vs_2020-03-15")

    # Fill to ~40 by cartesian of hike vs ease (deterministic order)
    for h in hike_dates:
        for e in ease_dates:
            if len(gold_a) >= 40:
                break
            add_a(h, e, "50_75bp_vs_ease_or_zero")
        if len(gold_a) >= 40:
            break

    # If still short, use any positive d_same vs any negative
    if len(gold_a) < 40:
        pos = sorted(
            d
            for d in stmts
            if d in by_date.index and pd.notna(by_date.loc[d, "d_same"]) and float(by_date.loc[d, "d_same"]) > 0
        )
        neg = sorted(
            d
            for d in stmts
            if d in by_date.index and pd.notna(by_date.loc[d, "d_same"]) and float(by_date.loc[d, "d_same"]) < 0
        )
        for h in reversed(pos):  # prefer larger/recent
            for e in neg:
                if len(gold_a) >= 40:
                    break
                add_a(h, e, "pos_vs_neg_d_same")
            if len(gold_a) >= 40:
                break

    # --- Stratum B: Shah sentence pairs ---
    sents = load_sentences()
    hawks = [s for s in sents if s["label"] == "hawkish"]
    doves = [s for s in sents if s["label"] == "dovish"]
    rng = random.Random(SEED)
    # sample up to 200 unique pairs
    gold_b = []
    # To get diversity, shuffle and zip-style sample with replacement of combinations
    max_pairs = 200
    # Build list of all possible index pairs if small, else sample
    n_h, n_d = len(hawks), len(doves)
    needed = max_pairs
    used = set()
    attempts = 0
    while len(gold_b) < needed and attempts < needed * 50:
        attempts += 1
        hi = rng.randrange(n_h)
        di = rng.randrange(n_d)
        key = (hawks[hi]["sent_id"], doves[di]["sent_id"])
        if key in used:
            continue
        used.add(key)
        pid = f"B{len(gold_b)+1:03d}"
        gold_b.append(
            {
                "pair_id": pid,
                "a": hawks[hi]["sent_id"],
                "b": doves[di]["sent_id"],
                "gold": "a",
                "source": "shah",
                "confidence": "certain",
            }
        )

    # --- Stratum C: adjacent scheduled statements ---
    sched = labels[labels["is_scheduled"] == True].sort_values("date")  # noqa: E712
    sched_dates = [d for d in sched["date"].tolist() if d in stmts]
    gold_c = []
    unlabeled = []
    for i in range(1, len(sched_dates)):
        t = sched_dates[i]
        t1 = sched_dates[i - 1]
        if t not in by_date.index or t1 not in by_date.index:
            continue
        ds_t = by_date.loc[t, "d_same"]
        ds_t1 = by_date.loc[t1, "d_same"]
        if pd.isna(ds_t) or pd.isna(ds_t1):
            unlabeled.append(
                {
                    "pair_id": f"U{len(unlabeled)+1:03d}",
                    "a": stmts[t]["doc_id"],
                    "b": stmts[t1]["doc_id"],
                    "date_a": t,
                    "date_b": t1,
                    "reason": "missing_d_same",
                }
            )
            continue
        diff = float(ds_t) - float(ds_t1)
        if diff == 0:
            unlabeled.append(
                {
                    "pair_id": f"U{len(unlabeled)+1:03d}",
                    "a": stmts[t]["doc_id"],
                    "b": stmts[t1]["doc_id"],
                    "date_a": t,
                    "date_b": t1,
                    "d_same_a": float(ds_t),
                    "d_same_b": float(ds_t1),
                    "reason": "hold_vs_hold_or_same_action",
                }
            )
            continue
        # higher d_same = more hawkish action
        if diff > 0:
            hawk_d, dove_d = t, t1
        else:
            hawk_d, dove_d = t1, t
        pid = f"C{len(gold_c)+1:03d}"
        gold_c.append(
            {
                "pair_id": pid,
                "a": stmts[hawk_d]["doc_id"],
                "b": stmts[dove_d]["doc_id"],
                "gold": "a",
                "source": "adjacent",
                "confidence": "certain",
                "hawk_date": hawk_d,
                "dove_date": dove_d,
                "d_same_hawk": float(by_date.loc[hawk_d, "d_same"]),
                "d_same_dove": float(by_date.loc[dove_d, "d_same"]),
            }
        )

    all_gold = gold_a + gold_b + gold_c
    out_path = PAIRS / "gold_pairs.jsonl"
    with out_path.open("w") as f:
        for r in all_gold:
            # write core schema fields first-compatible
            core = {
                "pair_id": r["pair_id"],
                "a": r["a"],
                "b": r["b"],
                "gold": r["gold"],
                "source": r["source"],
                "confidence": r["confidence"],
            }
            # keep extras for audit
            extras = {k: v for k, v in r.items() if k not in core}
            line = {**core, **extras}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    unlab_path = PAIRS / "adjacent_unlabeled.jsonl"
    with unlab_path.open("w") as f:
        for r in unlabeled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = f"""# PAIR_MANIFEST — frozen gold pairs

**run_id:** `{RUN_ID}`  
**frozen:** before any TypeSafe/Jev call  
**seed (Stratum B):** `{SEED}`  
**freeze note:** Pairs locked for fedjev-2026-09-20. Do not regenerate after Jev scoring begins.

## Counts

| Stratum | source | n | file |
|---------|--------|--:|------|
| A — extreme document pairs | extreme | {len(gold_a)} | gold_pairs.jsonl |
| B — Shah hawkish vs dovish sentences | shah | {len(gold_b)} | gold_pairs.jsonl |
| C — adjacent scheduled statements (labeled) | adjacent | {len(gold_c)} | gold_pairs.jsonl |
| Unlabeled adjacents (holds vs holds / zero Δ) | — | {len(unlabeled)} | adjacent_unlabeled.jsonl |
| **Total gold pairs** | | **{len(all_gold)}** | |

## Construction rules

### A (certain, must-not-invert)
- 50–75 bp hike statements (2022-06, 07, 09, 11) vs Mar 2020–Jan 2021 easing/hold-at-zero
- Explicit: 2022-11-02 vs 2020-03-15; 2022-09-21 vs 2020-04-29; latest hike vs 2020-03-15
- Cap 40; gold = hike/hawk side (`a`)

### B
- Hawkish vs dovish only (Shah labels 1 vs 0); no neutrals
- Random pairs, seed {SEED}, cap 200; gold = hawkish id as `a`

### C
- Consecutive *scheduled* meetings with opening statements in corpus
- Gold only when sign(d_same[t] − d_same[t−1]) ≠ 0; higher d_same → more hawkish
- Zero-diff pairs → adjacent_unlabeled.jsonl

## Latest hike in corpus
- requested: 2026-09-16 (raise toward 3.75–4.00)
- resolved latest_hike doc: `{latest_hike}`
- present in statements.jsonl: `{latest_hike in stmts if latest_hike else False}`

## Hike / ease pools used for A
- hike_dates ({len(hike_dates)}): {", ".join(hike_dates)}
- ease_dates n={len(ease_dates)} (Mar 2020–Jan 2021)
"""
    (PAIRS / "PAIR_MANIFEST.md").write_text(manifest)
    print(manifest)
    print(f"Wrote {out_path} ({len(all_gold)} pairs)")


if __name__ == "__main__":
    main()
