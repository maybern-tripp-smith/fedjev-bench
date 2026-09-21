#!/usr/bin/env python3
"""Khaled / jsort sensitivity pilot: jgrep --para filter then Score (~25 meetings).

Sequence (approved):
  1) Sample ~25 scheduled openings (prefer action days; seed 20260920)
  2) Recover blank-line paragraphs from presser PDFs
  3) Filter with jgrep --para criterion (or pure-Python fallback)
  4) Cap filtered concat at 8000 chars; empty filter → original + filter_empty
  5) Re-Score filtered text (same levels as main bench); cache under
     runs/jev/khaled_filter_cache/
  6) Compare filtered vs baseline score_jev vs d_same and FedLock m

Abort if preflight estimated spend > $0.08. Target ~$0.02–0.05.
Does NOT raise char limits on full pressers, re-run TrueSkill, or re-run Haiku.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from load_typesafe_env import ensure as ensure_api_key  # noqa: E402
from strip_meta import strip_meta  # noqa: E402

SEED = 20260920
FILTER_CRITERION = "states a view on inflation or the stance of monetary policy"
SCORE_CRITERION = "more hawkish about inflation"
SCORE_LEVELS = [
    "much more dovish",
    "somewhat dovish",
    "neutral",
    "somewhat hawkish",
    "much more hawkish",
]
SCORE_INSTRUCTIONS = (
    f"Rate how {SCORE_CRITERION} this statement is, "
    "from much more dovish to much more hawkish"
)
MODEL = "jev-latest"
PRICE_PER_MTOK = 0.042
MAX_CHARS = 8000
N_TARGET = 25
COST_ABORT_USD = 0.08
CACHE_DIR = ROOT / "runs" / "jev" / "khaled_filter_cache"
OUT_DIR = ROOT / "results" / "khaled_sensitivity"
PDF_DIR = ROOT / "data" / "raw" / "jsort" / "pdfs"
# Fallback if symlink missing
PDF_DIR_ALT = Path("/workspace/fedjev-bench/data/raw/jsort/pdfs")

FURNITURE = re.compile(
    r"^(Page \d+ of \d+|PRELIMINARY|FINAL|[A-Z][a-z]+ \d{1,2}, \d{4}|"
    r"(Transcript of )?Chair\w* \w+[’']s Press Conference|\d+\s+of\s+\d+)$"
)
SPEAKER = re.compile(r"^((?:[A-Z][A-Z’'\-]+\.? ){1,3}[A-Z][A-Z’'\-]+)[.:] ")

# Lightweight lexical fallback if jgrep CLI unavailable
INFLATION_POLICY_RE = re.compile(
    r"\b(inflation|price\s+stabilit\w*|PCE|CPI|core\s+prices?|"
    r"monetary\s+policy|federal\s+funds|policy\s+rate|interest\s+rates?|"
    r"accommodation|tightening|restrictive|hawkish|dovish|"
    r"balance\s+sheet|securities\s+holdings|forward\s+guidance|"
    r"dual\s+mandate|maximum\s+employment|price\s+pressures?)\b",
    re.I,
)


def pdf_path_for_date(date: str) -> Path:
    day = date.replace("-", "")
    for base in (PDF_DIR, PDF_DIR_ALT):
        p = base / f"{day}.pdf"
        if p.exists():
            return p
    raise FileNotFoundError(f"No PDF for {date}")


def opening_paragraphs(date: str) -> list[str]:
    """Blank-line paragraphs of the chair opening, recovered from the presser PDF."""
    pdf = pdf_path_for_date(date)
    raw = subprocess.check_output(["pdftotext", str(pdf), "-"], text=True, errors="replace")
    raw_lines = raw.splitlines()
    lines = [l.strip() for l in raw_lines]
    start = next(
        i
        for i, l in enumerate(lines)
        if (m := SPEAKER.match(l)) and m.group(1).startswith("CHAIR")
    )
    end = next((i for i in range(start + 1, len(lines)) if SPEAKER.match(lines[i])), len(lines))
    chair = SPEAKER.match(lines[start]).group(1)
    paras: list[str] = []
    buf: list[str] = []
    for i in range(start, end):
        s = raw_lines[i].strip()
        if not s or FURNITURE.match(s):
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if i == start:
            s = (
                s[len(chair) + 2 :].strip()
                if s.startswith(chair)
                else re.sub(r"^" + re.escape(chair) + r"[.:]\s*", "", s)
            )
            if not s:
                continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf))
    # Drop tiny furniture fragments
    return [p for p in paras if len(p) >= 40]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def score_cache_key(model: str, criterion: str, hash_t: str, arm: str) -> str:
    raw = f"{model}|score|{criterion}|{hash_t}|arm={arm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_cache(key: str) -> dict[str, Any] | None:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def write_cache(key: str, obj: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(obj, indent=2) + "\n")


def jgrep_available() -> bool:
    from shutil import which

    return which("jgrep") is not None


def filter_paras_jgrep(paras: list[str], *, budget: float = 0.05) -> tuple[list[str], dict[str, Any]]:
    """Run jgrep --para on blank-line-joined paragraphs; return kept paras + meta."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n\n".join(paras) + "\n")
        tmp = f.name
    try:
        cmd = [
            "jgrep",
            "--para",
            "-p",
            "0.5",
            "--budget",
            str(budget),
            "--max-chars",
            str(MAX_CHARS),
            FILTER_CRITERION,
            tmp,
        ]
        env = os.environ.copy()
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
        out = proc.stdout
        # Reconstruct kept paragraphs: jgrep prints matching paragraphs separated by blank lines
        kept = [p.strip() for p in re.split(r"\n\s*\n", out) if p.strip()]
        meta = {
            "method": "jgrep --para",
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-500:],
            "n_in": len(paras),
            "n_kept": len(kept),
        }
        return kept, meta
    finally:
        Path(tmp).unlink(missing_ok=True)


def filter_paras_python(paras: list[str]) -> tuple[list[str], dict[str, Any]]:
    kept = [p for p in paras if INFLATION_POLICY_RE.search(p)]
    return kept, {"method": "python_regex_fallback", "n_in": len(paras), "n_kept": len(kept)}


def estimate_jgrep_usd(paras: list[str]) -> float:
    """Offline estimate via jgrep --estimate when available; else bytes heuristic."""
    if not paras:
        return 0.0
    if not jgrep_available():
        # ~270 overhead tokens + chars/4 per para at $0.042/MTok
        toks = sum(270 + max(len(p), 1) / 4 for p in paras)
        return toks * PRICE_PER_MTOK / 1e6
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n\n".join(paras) + "\n")
        tmp = f.name
    try:
        proc = subprocess.run(
            ["jgrep", "--estimate", "--para", FILTER_CRITERION, tmp],
            capture_output=True,
            text=True,
            timeout=60,
        )
        m = re.search(r"~\$([0-9.]+)", proc.stdout)
        if m:
            return float(m.group(1))
        return 0.001 * len(paras)
    finally:
        Path(tmp).unlink(missing_ok=True)


def estimate_score_usd(n_docs: int, mean_chars: float) -> float:
    # Match cost.json score_docs ≈ 177093 tok / 95 docs ≈ 1864 tok/doc for ~8k chars
    toks_per = 270 + mean_chars / 4
    return n_docs * toks_per * PRICE_PER_MTOK / 1e6


def bootstrap_spearman(x: np.ndarray, y: np.ndarray, n_boot: int = 1000, seed: int = SEED) -> dict[str, Any]:
    from scipy.stats import spearmanr

    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return {"rho": None, "se": None, "n": n, "ci95": [None, None]}
    rho = float(spearmanr(x, y).correlation)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r = spearmanr(x[idx], y[idx]).correlation
        if np.isfinite(r):
            boots.append(float(r))
    boots_a = np.asarray(boots)
    se = float(boots_a.std(ddof=1)) if len(boots_a) > 1 else None
    lo, hi = (float(np.quantile(boots_a, 0.025)), float(np.quantile(boots_a, 0.975))) if len(boots_a) else (None, None)
    return {"rho": rho, "se": se, "n": n, "ci95": [lo, hi], "n_boot": n_boot}


def paired_bootstrap_delta_rho(
    base: np.ndarray,
    filt: np.ndarray,
    y: np.ndarray,
    n_boot: int = 1000,
    seed: int = SEED,
) -> dict[str, Any]:
    """Bootstrap s.e. for Δρ = ρ(filt,y) − ρ(base,y) with paired resampling."""
    from scipy.stats import spearmanr

    mask = np.isfinite(base) & np.isfinite(filt) & np.isfinite(y)
    base, filt, y = base[mask], filt[mask], y[mask]
    n = len(base)
    if n < 3:
        return {"delta_rho": None, "se": None, "n": n, "ci95": [None, None]}
    rho_b = float(spearmanr(base, y).correlation)
    rho_f = float(spearmanr(filt, y).correlation)
    delta = rho_f - rho_b
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        rb = spearmanr(base[idx], y[idx]).correlation
        rf = spearmanr(filt[idx], y[idx]).correlation
        if np.isfinite(rb) and np.isfinite(rf):
            boots.append(float(rf - rb))
    boots_a = np.asarray(boots)
    se = float(boots_a.std(ddof=1)) if len(boots_a) > 1 else None
    lo, hi = (float(np.quantile(boots_a, 0.025)), float(np.quantile(boots_a, 0.975))) if len(boots_a) else (None, None)
    return {
        "rho_baseline": rho_b,
        "rho_filtered": rho_f,
        "delta_rho": delta,
        "se": se,
        "n": n,
        "ci95": [lo, hi],
        "n_boot": n_boot,
    }


def select_sample(meetings: pd.DataFrame, n: int = N_TARGET) -> pd.DataFrame:
    """Prefer scheduled action-day openings overlapping Gate 3; else fill stratified."""
    m = meetings.copy()
    m = m[m["has_opening_statement"] & m["is_scheduled"] & ~m["exclude_main"]].copy()
    action = m[m["y_action"] != 0].sort_values("date")
    holds = m[m["y_action"] == 0].sort_values("date")
    rng = random.Random(SEED)
    action_dates = action["date"].tolist()
    rng.shuffle(action_dates)
    chosen = action_dates[:n]
    if len(chosen) < n:
        hold_dates = holds["date"].tolist()
        rng.shuffle(hold_dates)
        chosen.extend(hold_dates[: n - len(chosen)])
    chosen = sorted(chosen)
    out = m[m["date"].isin(chosen)].copy()
    out["sample_stratum"] = np.where(out["y_action"] != 0, "action_day", "hold_day")
    return out.sort_values("date")


def load_fedlock_m() -> dict[str, float]:
    path = ROOT / "results" / "fedlock_replica" / "fedlock_matches.json"
    if not path.exists():
        # try gates analysis path via fedlock raw
        return {}
    raw = json.loads(path.read_text())
    out = {}
    for doc_id, info in raw.items():
        # doc_id like stmt-2011-04-27
        date = doc_id.replace("stmt-", "")
        if info.get("m") is not None:
            out[date] = float(info["m"])
    return out


def call_score(client, text: str) -> dict[str, Any]:
    from typesafe_sdk import Score

    t0 = time.perf_counter()
    response = client.system_one(
        model=MODEL,
        state={"statement": text},
        questions={
            "hawkishness": Score(
                instructions=SCORE_INSTRUCTIONS,
                criteria=list(SCORE_LEVELS),
            ),
        },
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    ans = response.answers["hawkishness"]
    usage = response.usage
    return {
        "ok": True,
        "score": float(ans.score),
        "confidence": float(ans.confidence),
        "probabilities": {str(k): float(v) for k, v in ans.probabilities.items()},
        "legend": {str(k): v for k, v in ans.legend.items()},
        "model": response.model,
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Execute jgrep + Score calls")
    parser.add_argument("--n", type=int, default=N_TARGET)
    parser.add_argument("--force-python-filter", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    meetings = pd.read_csv(ROOT / "data" / "labels" / "meetings.csv")
    sample = select_sample(meetings, n=args.n)
    scores = pd.read_csv(ROOT / "results" / "statement_scores.csv")
    score_by_date = dict(zip(scores["date"].astype(str), scores["score_jev"]))
    fedlock_m = load_fedlock_m()

    # Load baseline opening text lengths for cost estimate
    docs_by_date = {}
    for line in (ROOT / "data" / "clean" / "statements.jsonl").open():
        d = json.loads(line)
        docs_by_date[d["date"]] = d

    rows = []
    filter_est = 0.0
    para_counts = []
    for _, row in sample.iterrows():
        date = str(row["date"])
        try:
            paras = opening_paragraphs(date)
        except Exception as e:
            paras = []
            print(f"WARN para extract {date}: {e}", flush=True)
        para_counts.append(len(paras))
        filter_est += estimate_jgrep_usd(paras)
        base_text = docs_by_date.get(date, {}).get("text") or ""
        rows.append(
            {
                "date": date,
                "sample_stratum": row["sample_stratum"],
                "d_same": float(row["d_same"]) if pd.notna(row["d_same"]) else None,
                "y_action": int(row["y_action"]),
                "score_jev_baseline": float(score_by_date[date]) if date in score_by_date and pd.notna(score_by_date[date]) else None,
                "fedlock_m": fedlock_m.get(date),
                "n_paras": len(paras),
                "baseline_n_chars": len(base_text),
                "paras": paras,
                "baseline_text": base_text,
            }
        )

    mean_chars = float(np.mean([r["baseline_n_chars"] for r in rows])) if rows else 0.0
    score_est = estimate_score_usd(len(rows), min(mean_chars, MAX_CHARS))
    preflight = {
        "n_meetings": len(rows),
        "n_action": sum(1 for r in rows if r["sample_stratum"] == "action_day"),
        "n_hold": sum(1 for r in rows if r["sample_stratum"] == "hold_day"),
        "mean_paras": float(np.mean(para_counts)) if para_counts else 0,
        "est_jgrep_usd": filter_est,
        "est_score_usd": score_est,
        "est_total_usd": filter_est + score_est,
        "abort_threshold_usd": COST_ABORT_USD,
        "jgrep_available": jgrep_available() and not args.force_python_filter,
        "seed": SEED,
        "filter_criterion": FILTER_CRITERION,
    }
    print(json.dumps({"preflight": preflight}, indent=2), flush=True)
    (OUT_DIR / "filter_pilot_preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")

    if preflight["est_total_usd"] > COST_ABORT_USD:
        print(f"ABORT: estimated ${preflight['est_total_usd']:.4f} > ${COST_ABORT_USD}", flush=True)
        sys.exit(2)

    if not args.live:
        print("Dry run only (pass --live to execute). Sample dates:", [r["date"] for r in rows])
        return

    if not ensure_api_key():
        print("TYPESAFE_API_KEY missing", flush=True)
        sys.exit(1)

    use_jgrep = jgrep_available() and not args.force_python_filter
    # Ensure PATH for subprocess
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = local_bin + ":" + os.environ.get("PATH", "")

    spent_filter = 0.0
    spent_score = 0.0
    results = []

    from typesafe_sdk import TypeSafeClient

    client = TypeSafeClient()

    for r in rows:
        date = r["date"]
        paras = r["paras"]
        if use_jgrep and paras:
            kept, fmeta = filter_paras_jgrep(paras, budget=0.05)
            # crude spend: estimate was per-doc; track via estimate
            spent_filter += estimate_jgrep_usd(paras)  # upper bound if uncached; actual may be less
        else:
            kept, fmeta = filter_paras_python(paras) if paras else ([], {"method": "empty_paras"})

        filter_empty = len(kept) == 0
        if filter_empty:
            # Fall back to original baseline text (already cleaned)
            filtered_text = r["baseline_text"]
        else:
            concat = "\n\n".join(kept)
            filtered_text = strip_meta(concat)
            if len(filtered_text) > MAX_CHARS:
                filtered_text = filtered_text[:MAX_CHARS]

        ht = text_hash(filtered_text)
        key = score_cache_key(MODEL, SCORE_CRITERION, ht, "khaled_filter")
        cached = read_cache(key)
        if cached and cached.get("ok"):
            sc = cached
            cache_hit = True
        else:
            sc = call_score(client, filtered_text)
            sc["cache_key"] = key
            sc["hash"] = ht
            sc["date"] = date
            sc["arm"] = "filtered"
            write_cache(key, sc)
            spent_score += sc["input_tokens"] * PRICE_PER_MTOK / 1e6
            cache_hit = False

        results.append(
            {
                "date": date,
                "sample_stratum": r["sample_stratum"],
                "d_same": r["d_same"],
                "y_action": r["y_action"],
                "score_jev_baseline": r["score_jev_baseline"],
                "score_jev_filtered": sc.get("score"),
                "fedlock_m": r["fedlock_m"],
                "filter_empty": filter_empty,
                "n_paras_in": r["n_paras"],
                "n_paras_kept": 0 if filter_empty and fmeta.get("n_kept", 0) == 0 else fmeta.get("n_kept", len(kept)),
                "filtered_n_chars": len(filtered_text),
                "baseline_n_chars": r["baseline_n_chars"],
                "filter_meta": fmeta,
                "score_cache_hit": cache_hit,
                "score_input_tokens": sc.get("input_tokens", 0),
                "score_model": sc.get("model"),
                "confidence": sc.get("confidence"),
            }
        )
        print(
            f"{date} filt_empty={filter_empty} kept={results[-1]['n_paras_kept']}/{r['n_paras']} "
            f"chars={len(filtered_text)} score_f={sc.get('score')} base={r['score_jev_baseline']}",
            flush=True,
        )

    df = pd.DataFrame(results)
    base = df["score_jev_baseline"].to_numpy(dtype=float)
    filt = df["score_jev_filtered"].to_numpy(dtype=float)
    d_same = df["d_same"].to_numpy(dtype=float)
    fl_m = df["fedlock_m"].to_numpy(dtype=float)

    correlations = {
        "baseline_vs_d_same": bootstrap_spearman(base, d_same),
        "filtered_vs_d_same": bootstrap_spearman(filt, d_same),
        "delta_rho_vs_d_same": paired_bootstrap_delta_rho(base, filt, d_same),
        "baseline_vs_fedlock_m": bootstrap_spearman(base, fl_m),
        "filtered_vs_fedlock_m": bootstrap_spearman(filt, fl_m),
        "delta_rho_vs_fedlock_m": paired_bootstrap_delta_rho(base, filt, fl_m),
        "filtered_vs_baseline_scores": bootstrap_spearman(filt, base),
    }

    # Actual score spend from tokens
    actual_score_usd = float(df.loc[~df["score_cache_hit"], "score_input_tokens"].sum() * PRICE_PER_MTOK / 1e6)

    out = {
        "run_id_note": "sensitivity pilot only; does not mutate frozen run_id fedjev-2026-09-20",
        "seed": SEED,
        "n": len(df),
        "filter_criterion": FILTER_CRITERION,
        "score_criterion": SCORE_CRITERION,
        "score_levels": SCORE_LEVELS,
        "max_chars_cap": MAX_CHARS,
        "preflight": preflight,
        "cost_usd": {
            "jgrep_est_or_tracked": spent_filter if use_jgrep else 0.0,
            "score_actual": actual_score_usd,
            "total_reported": (spent_filter if use_jgrep else 0.0) + actual_score_usd,
            "note": (
                "jgrep spend is estimate-tracked (cache may reduce actual); "
                "Score spend from input tokens at $0.042/MTok"
            ),
        },
        "n_filter_empty": int(df["filter_empty"].sum()),
        "correlations": correlations,
        "rows": results,
    }
    out_path = OUT_DIR / "filter_pilot.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path}", flush=True)
    print(
        f"ρ filtered vs d_same={correlations['filtered_vs_d_same']}; "
        f"baseline={correlations['baseline_vs_d_same']}; "
        f"Δ={correlations['delta_rho_vs_d_same']}",
        flush=True,
    )
    print(f"cost Score=${actual_score_usd:.5f} jgrep_est=${spent_filter if use_jgrep else 0:.5f}", flush=True)


if __name__ == "__main__":
    main()
