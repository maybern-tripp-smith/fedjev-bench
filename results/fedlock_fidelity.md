# Relationship to FedLock (Gate 7 fidelity)

Gate 7 is an **external consistency check**: do two independently constructed *text* scores agree on meeting-day hawkishness? It is **not** a FedLock replication, and it is **not** the TrueSkill replica documented in [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md).

This note is self-contained. A reader who has not read the main analysis should still be able to rebuild the Gate 7 match and the rank correlations from the frozen artifacts. Numbers are taken from `results/gates.json` (`7_fedlock_consistency`). None were invented for this write-up.

---

## 1. Terms, taught once

**Federal Open Market Committee (FOMC).** The Federal Reserve committee that sets the federal funds target. The documents on *this* side of Gate 7 are Chair press-conference *openings* (jsort-style), not necessarily the full press-conference transcript.

**Behavioral label versus textual hawkishness.** The main bench’s behavioral label is `d_same`, the same-day change in the federal funds target (hike, hold, or cut). On a hold, `d_same` is identically zero, so it cannot encode hawkish-hold versus dovish-hold wording. Gate 7 does not correlate against `d_same`. It correlates two *text* scores with each other.

**FedLock.** An independent published scoring project ([methodology](https://jnathan9.github.io/fedlock/); snapshot `data/raw/fedlock/data.json`). FedLock V3 asks Llama 3.3 70B which of two anonymized speeches is more hawkish *given* contemporaneous macro conditions, then aggregates ~60,000 comparisons on ~4,000 speeches with TrueSkill (defined below). Published `press_conference` fields used here:

| Field | Meaning |
|-------|---------|
| `m` | Raw TrueSkill mean (μ) — absolute text hawkishness |
| `ma` | Era-adjusted mean — `m` minus a quarterly average |
| `s` | TrueSkill uncertainty (σ). Lower means the published rating has settled. Mean `s` on the matched main-analysis set is **1.7762** |
| `d` | Date on the FedLock record |
| `st` | Speech type; Gate 7 uses `press_conference` |

The primary Gate 7 contrast is raw `m`. Era-adjusted `ma` is a sensitivity, not the headline.

**TrueSkill versus Bradley–Terry.** Gate 7’s *left-hand* scores come from this repository’s main protocol: dual-order Choice under `more hawkish about inflation`, aggregated by **Bradley–Terry** (a pairwise strength model on a fixed gold-pair graph), plus a secondary direct Score pass (`score_jev`). **TrueSkill** is Microsoft’s Bayesian skill-rating system (prior mean 50, prior uncertainty about 8.33, target uncertainty σ < 2). Published FedLock uses TrueSkill. Gate 7 does **not** re-run TrueSkill. It only *reads* FedLock’s published means and asks how they rank against Bradley–Terry / Score.

**Macro conditioning and anonymization (what Gate 7 does and does not share).**

- *Shared with FedLock, in a limited sense:* the object of measurement is pairwise textual hawkishness; this repository strips names and dates on its own Jev Choice calls (`scripts/strip_meta.py`); FedLock scores are used as an external reference.
- *Not used on the Gate 7 left-hand side:* macro-conditioned judge prompts (core personal consumption expenditures inflation, unemployment, real gross domestic product growth, and the CBOE Volatility Index at speech time); TrueSkill aggregation; Swiss or uncertainty-targeted pairing; Llama 3.3 70B; FedLock’s full speech corpus.

**Gate 7 versus the FedLock-faithful replica.**

| | Gate 7 (this note) | Replica ([FINDINGS](results/fedlock_replica/FINDINGS.md), ANALYSIS §12) |
|--|--------------------|--------------------------------------------------------------|
| Claim | Rank agreement between two *already computed* text systems | Protocol-fidelity experiment: re-run a FedLock-style TrueSkill tournament on the 95 openings (Jev arm and Haiku arm) and compare those ratings to published `m` / `ma` |
| Left-hand series | Bradley–Terry and `score_jev` from the main bench | New TrueSkill μ series from Jev and from Haiku |
| Does it re-run TrueSkill? | No | Yes, on 95 openings only — not at FedLock’s ~4,000-speech scale |

**Jev versus Haiku in the *main* bench (not this table’s third column).** The Gate 7 numbers below are Jev (Bradley–Terry and Score) versus published FedLock. A same-protocol Haiku Choice arm exists for the main gates (cost / inversion); it is not the Gate 7 left-hand series. The replica’s Haiku arm is a different run (`claude-haiku-4-5-20251001` under the TrueSkill protocol).

**Spearman’s rank correlation (ρ).** Do the two series produce a similar *ordering* of meetings? Reported with a bootstrap **standard error (s.e.)** — the standard deviation of 1,000 meeting resamples — and a percentile 95 percent confidence interval. This note writes “standard error” or “s.e.” It does not use the label STE.

---

## 2. Procedure a reader can re-run (from cached outputs)

1. Load meeting-level scores from `results/statement_scores.csv` (Bradley–Terry `score`, `score_jev`) and the meeting calendar / exclusions from `data/labels/meetings.parquet`.
2. Load FedLock `press_conference` rows from `data/raw/fedlock/data.json`.
3. Match on **title-embedded meeting date** when a `20YY-MM-DD` string appears in the FedLock title; otherwise use the FedLock `d` field with calendar offsets 0, +1, −1, +2 days.
4. Restrict to the main-analysis sample (scheduled meetings; drop the pre-registered crisis dates 2020-03-03 and 2020-03-15; flag 2023-03-22 without dropping).
5. Compute Spearman’s rank correlation of Bradley–Terry versus `m` and versus `ma` (n = 46 meetings with a Bradley–Terry score) and of `score_jev` versus `m` and versus `ma` (n = 90). Bootstrap 1,000 meeting resamples for the standard error and the percentile interval.
6. Do **not** treat the result as a TrueSkill replication. If the question is protocol fidelity, stop and open the replica note instead.

---

## 3. Matching (observed)

- Policy: prefer title-embedded meeting date; else FedLock `d` with offsets 0, +1, −1, +2
- Matched meetings (all calendar): **92**
- Main-analysis matched rows: **90**
- Same-calendar-day on the FedLock `d` field: **1**
- Offset (`fedlock_d` − meeting) on the main-analysis match: `{'0': 1, '1': 89}`
- Match route on the main-analysis match: `{'title_date': 90}`
- Mean FedLock `s` on the matched main set: **1.7762** (TrueSkill uncertainty; lower means more settled)

When the match falls back to the `d` field, the offset is almost always +1 day. That is a dating convention, not a second sample.

---


## 4. Results

| Contrast | Spearman ρ | Standard error | n | 95% confidence interval |
|----------|-----------:|---------------:|--:|-------------------------|
| Bradley–Terry vs `m` (raw) | +0.679 | 0.112 | 46 | [+0.436, +0.861] |
| Bradley–Terry vs `ma` (era-adjusted) | +0.594 | 0.104 | 46 | [+0.361, +0.770] |
| `score_jev` vs `m` | +0.944 | 0.016 | 90 | [+0.900, +0.966] |
| `score_jev` vs `ma` | +0.774 | 0.044 | 90 | [+0.673, +0.839] |

Agreement with raw `m` is stronger than with era-adjusted `ma`, especially for the Score pass. The Score-versus-`m` contrast is near a rank ceiling (ρ = +0.944, s.e. = 0.016, n = 90). Bradley–Terry versus `m` is lower (ρ = +0.679, s.e. = 0.112, n = 46) on a smaller, sparser graph.

---

## 5. What this does and does not imply

Gate 7 ρ asks: *do two independent text-scoring systems agree on meeting-day hawkishness?*

It does **not** claim: *we replicated FedLock’s tournament, judge, corpus, or aggregator.*

**Corpus mismatch.** Our documents are chair openings. FedLock `press_conference` may be fuller presser text. Agreement is still informative; it is not a same-document comparison.

**Length design choice (jsort `--max-chars` 8000).** jsort / jgrep default `--max-chars 8000` truncates what Jev sees in jsort tournaments. On *our* opening corpus (`data/clean/statements.jsonl`, n=95): mean ≈ 7,917 characters; p50 ≈ 7,547; p95 ≈ 11,706; max = 13,794; **39 / 95 (41.1%)** exceed 8,000 characters. The frozen main `run_id=fedjev-2026-09-20` Score/Choice pass did **not** apply that 8k client cap. Audit: `results/khaled_sensitivity/char_length_audit.json`. Passage-filter Score pilot: ANALYSIS §13 · `results/khaled_sensitivity/filter_pilot.json`.

**Separate experiment.** A FedLock-V3-faithful protocol (macro-conditioned relative hawkishness, anonymization, TrueSkill with Swiss / uncertainty pairing) was run on the 95 openings, comparing Jev, Haiku, and published `m` / `ma`. That run has its own `run_id` (`fedjev-fedlock-replica-2026-09-20`). See [`results/fedlock_replica/FINDINGS.md`](results/fedlock_replica/FINDINGS.md) and ANALYSIS §12. It is not a 4,000-speech / ~60,000-comparison scale replication, and it does not replace Gate 7.
