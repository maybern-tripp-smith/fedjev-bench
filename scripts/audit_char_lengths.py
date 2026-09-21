#!/usr/bin/env python3
"""Zero-$ length audit: opening texts vs jsort default --max-chars 8000.

Records character counts for the main-run opening corpus (meta-stripped text as
scored). Does not call Jev. Writes results/khaled_sensitivity/char_length_audit.json
and char_length_vs_8k.png.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results" / "khaled_sensitivity"
JSORT_MAX_CHARS = 8000
SEED_NOTE = "audit is deterministic; no sampling"


def percentile(xs: list[int], p: float) -> float:
    if not xs:
        return float("nan")
    return float(np.percentile(np.asarray(xs, dtype=float), p))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docs = []
    for line in (ROOT / "data" / "clean" / "statements.jsonl").open():
        d = json.loads(line)
        # Prefer cleaned `text` (strip_meta already applied in prepare_statements);
        # fall back to raw_text. Main Score pass uses strip_meta(raw) again.
        text = d.get("text") or d.get("raw_text") or ""
        docs.append(
            {
                "doc_id": d["doc_id"],
                "date": d["date"],
                "n_chars": len(text),
                "n_chars_raw": len(d.get("raw_text") or text),
                "exceeds_8000": len(text) > JSORT_MAX_CHARS,
            }
        )

    lengths = [r["n_chars"] for r in docs]
    over = [r for r in docs if r["exceeds_8000"]]
    over_dates = sorted(r["date"] for r in over)

    summary = {
        "corpus": "chair openings (data/clean/statements.jsonl text field)",
        "jsort_default_max_chars": JSORT_MAX_CHARS,
        "design_note": (
            "jsort/jgrep default --max-chars 8000 truncates what Jev sees. "
            "This audit measures bindingness on our opening corpus only; "
            "we do not raise char limits on full pressers for the frozen run_id."
        ),
        "n_docs": len(docs),
        "mean_chars": float(statistics.fmean(lengths)) if lengths else None,
        "p50_chars": percentile(lengths, 50),
        "p90_chars": percentile(lengths, 90),
        "p95_chars": percentile(lengths, 95),
        "max_chars": max(lengths) if lengths else None,
        "min_chars": min(lengths) if lengths else None,
        "n_exceeding_8000": len(over),
        "share_exceeding_8000": (len(over) / len(docs)) if docs else None,
        "main_run_truncated": False,
        "main_run_note": (
            "Frozen run_id=fedjev-2026-09-20 Score/Choice sent full stripped openings "
            "without a jsort-style 8000-char client cap."
        ),
        "dates_exceeding_8000": over_dates,
        "per_doc": docs,
        "seed_note": SEED_NOTE,
    }

    out_json = OUT_DIR / "char_length_audit.json"
    out_json.write_text(json.dumps(summary, indent=2) + "\n")

    # Figure: histogram + 8k reference line
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.hist(lengths, bins=20, color="#2c5282", edgecolor="white", alpha=0.9)
    ax.axvline(JSORT_MAX_CHARS, color="#c53030", linestyle="--", linewidth=1.5, label="jsort default 8,000")
    ax.axvline(summary["mean_chars"], color="#2f855a", linestyle=":", linewidth=1.3, label=f"mean {summary['mean_chars']:.0f}")
    ax.set_xlabel("Characters (opening text)")
    ax.set_ylabel("Meetings")
    ax.set_title("Opening length vs jsort default --max-chars 8000")
    ax.legend(frameon=False, fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig_path = OUT_DIR / "char_length_vs_8k.png"
    fig.savefig(fig_path, dpi=150)
    # also copy to results/figures and docs/figures
    for dest_dir in (ROOT / "results" / "figures", ROOT / "docs" / "figures"):
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / fig_path.name).write_bytes(fig_path.read_bytes())
    plt.close(fig)

    print(
        f"n={summary['n_docs']} mean={summary['mean_chars']:.1f} "
        f"p50={summary['p50_chars']:.1f} p95={summary['p95_chars']:.1f} "
        f"max={summary['max_chars']} over8k={summary['n_exceeding_8000']} "
        f"({100 * summary['share_exceeding_8000']:.1f}%)"
    )
    print(f"wrote {out_json}")
    print(f"wrote {fig_path}")


if __name__ == "__main__":
    main()
