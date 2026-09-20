#!/usr/bin/env python3
"""TypeSafe/Jev experiments 3–7 for fedjev-bench (run_id fedjev-2026-09-20).

Exp3: composite atomic Scores (4 dims) per statement
Exp4: multi-label Nouls (packed with Exp3 — one SystemOne call per doc)
Exp5: paraphrase calibration on Stratum A
Exp6: evidence-span Choice (Shah hawk + distractors)
Exp7: macro-relative vs text-absolute Choice on Stratum A

Cache: runs/jev/exp_cache/
Answers log: runs/jev/experiments_answers.jsonl
Outputs: results/experiments/exp{3..7}_*.json (+ csv), SUMMARY.json, FINDINGS.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.load_typesafe_env import ensure as ensure_api_key  # noqa: E402
from scripts.strip_meta import strip_meta  # noqa: E402

RUN_ID = "fedjev-2026-09-20"
MODEL = "jev-latest"
PRICE_PER_MTOK_INPUT = 0.042
BUDGET_USD = 1.0
SEED = 20260920
CRITERION = "more hawkish about inflation"
CRISIS = {"2020-03-03", "2020-03-15"}
SVB = "2023-03-22"

SCORE_DIMS = [
    "inflation_urgency",
    "tightness_preference",
    "reaction_toughness",
    "guidance_firmness",
]
COMPOSITE_WEIGHTS = {d: 0.25 for d in SCORE_DIMS}

SCORE_LEVELS = {
    "inflation_urgency": [
        "not urgent — inflation fight not a priority",
        "slightly urgent",
        "moderately urgent",
        "quite urgent",
        "extremely urgent — inflation fight dominates",
    ],
    "tightness_preference": [
        "strong preference for easier / more accommodative policy",
        "mild preference for easier policy",
        "neutral on tightness",
        "mild preference for tighter policy",
        "strong preference for tighter / restrictive policy",
    ],
    "reaction_toughness": [
        "very soft reaction — unwilling to accept growth pain",
        "somewhat soft reaction function",
        "balanced reaction function",
        "somewhat tough — willing to accept some growth pain",
        "very tough — prioritizes inflation over growth pain",
    ],
    "guidance_firmness": [
        "very soft / open to ease soon — no higher-for-longer tone",
        "somewhat soft forward guidance",
        "neutral / data-dependent without firm direction",
        "somewhat firm — higher-for-longer leaning",
        "very firm higher-for-longer / restrictive-for-longer tone",
    ],
}

SCORE_INSTRUCTIONS = {
    "inflation_urgency": (
        "Rate how urgent the fight against inflation appears in this text "
        "(0=not urgent … 4=extremely urgent)."
    ),
    "tightness_preference": (
        "Rate the preference for tighter monetary policy expressed in this text "
        "(0=strong ease preference … 4=strong tighten preference)."
    ),
    "reaction_toughness": (
        "Rate the toughness of the reaction function / willingness to accept "
        "growth or employment pain to bring inflation down "
        "(0=very soft … 4=very tough)."
    ),
    "guidance_firmness": (
        "Rate the firmness of forward guidance / higher-for-longer tone "
        "(0=very soft / ease-soon … 4=very firm higher-for-longer)."
    ),
}

NOUL_KEYS = [
    "signals_cut_soon",
    "signals_higher_for_longer",
    "acknowledges_banking_stress",
    "blames_supply_shocks",
]
NOUL_INSTRUCTIONS = {
    "signals_cut_soon": (
        "Does this text signal that policy rate cuts are coming soon "
        "or that easing is imminent?"
    ),
    "signals_higher_for_longer": (
        "Does this text signal a higher-for-longer / restrictive-for-longer "
        "policy stance?"
    ),
    "acknowledges_banking_stress": (
        "Does this text acknowledge banking-sector stress, financial-stability "
        "risks from banks, or recent bank failures / turmoil?"
    ),
    "blames_supply_shocks": (
        "Does this text primarily attribute inflation pressures to supply shocks, "
        "tariffs, commodity/supply disruptions, or similar supply-side factors "
        "(rather than excess demand)?"
    ),
}

PARA_BASELINE = "Which of Text A or Text B is more hawkish about inflation"
PARA_PHRASES = [
    {
        "id": "para_tighter_stance",
        "instructions": (
            "Which of Text A or Text B argues for a tighter stance against inflation"
        ),
    },
    {
        "id": "para_less_accommodative",
        "instructions": (
            "Which of Text A or Text B is less accommodative on inflation"
        ),
    },
]

MACRO_INSTRUCTIONS = (
    "Which of Text A or Text B is more hawkish about inflation given the macro "
    "conditions provided for each text"
)
SPAN_INSTRUCTIONS = "Which span is more hawkish about inflation"

EXP_CACHE = ROOT / "runs" / "jev" / "exp_cache"
ANSWERS_PATH = ROOT / "runs" / "jev" / "experiments_answers.jsonl"
OUT_DIR = ROOT / "results" / "experiments"

_write_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress = {
    "n": 0, "cache_hits": 0, "failures": 0,
    "input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "usd": 0.0,
    "by_exp": defaultdict(lambda: {
        "n": 0, "cache_hits": 0, "failures": 0,
        "input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "usd": 0.0,
    }),
}


def spearman(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return float("nan"), n
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan"), n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def bootstrap_spearman(x, y, n_boot=1000, seed=SEED):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    point, _ = spearman(x, y)
    if n < 3 or not np.isfinite(point):
        return {
            "rho": None if not np.isfinite(point) else float(point),
            "n": n, "ste": None, "se": None,
            "ci_low": None, "ci_high": None, "n_boot": 0,
        }
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r, _ = spearman(x[idx], y[idx])
        if np.isfinite(r):
            boots.append(r)
    boots = np.asarray(boots)
    ste = float(boots.std(ddof=1)) if len(boots) > 1 else None
    return {
        "rho": float(point), "n": n, "ste": ste, "se": ste,
        "ci_low": float(np.percentile(boots, 2.5)) if len(boots) else None,
        "ci_high": float(np.percentile(boots, 97.5)) if len(boots) else None,
        "n_boot": len(boots),
    }


def binomial_rate(n_success: int, n: int):
    if n <= 0:
        return {"rate": None, "n": 0, "n_success": 0, "ste": None}
    p = n_success / n
    ste = float(np.sqrt(p * (1.0 - p) / n))
    return {
        "rate": float(p), "n": int(n), "n_success": int(n_success),
        "ste": ste, "ci_low": float(max(0.0, p - 1.96 * ste)),
        "ci_high": float(min(1.0, p + 1.96 * ste)),
    }


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cache_path(key: str) -> Path:
    return EXP_CACHE / f"{key}.json"


def read_cache(key: str) -> dict[str, Any] | None:
    p = cache_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def write_cache(key: str, obj: dict[str, Any]) -> None:
    EXP_CACHE.mkdir(parents=True, exist_ok=True)
    p = cache_path(key)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    tmp.replace(p)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()


def bump(exp: str, *, cache_hit=False, failure=False,
         input_tokens=0, output_tokens=0, latency_ms=0):
    with _progress_lock:
        _progress["n"] += 1
        if cache_hit:
            _progress["cache_hits"] += 1
        if failure:
            _progress["failures"] += 1
        _progress["input_tokens"] += input_tokens
        _progress["output_tokens"] += output_tokens
        _progress["latency_ms"] += latency_ms
        _progress["usd"] = _progress["input_tokens"] * PRICE_PER_MTOK_INPUT / 1e6
        be = _progress["by_exp"][exp]
        be["n"] += 1
        if cache_hit:
            be["cache_hits"] += 1
        if failure:
            be["failures"] += 1
        be["input_tokens"] += input_tokens
        be["output_tokens"] += output_tokens
        be["latency_ms"] += latency_ms
        be["usd"] = be["input_tokens"] * PRICE_PER_MTOK_INPUT / 1e6
        n = _progress["n"]
        if n % 20 == 0 or failure:
            print(
                f"[progress] calls={n} cache={_progress['cache_hits']} "
                f"fail={_progress['failures']} "
                f"tok={_progress['input_tokens']} usd≈{_progress['usd']:.5f}",
                flush=True,
            )
        if _progress["usd"] > BUDGET_USD:
            print("STOP: spend > $1 — aborting further live calls", flush=True)
            raise SystemExit(99)


def make_client():
    from typesafe_sdk import TypeSafeClient, RetryPolicy
    return TypeSafeClient(
        retry=RetryPolicy(
            max_retries=5, backoff_initial=0.5, backoff_max=30.0,
            http_statuses={408, 429, 500, 502, 503, 504, 529},
            timeout=120.0,
        ),
        timeout=120.0,
    )


def load_statements() -> list[dict[str, Any]]:
    rows = []
    for line in (ROOT / "data/clean/statements.jsonl").open():
        d = json.loads(line)
        raw = d.get("raw_text") or d.get("text") or ""
        d["stripped"] = strip_meta(raw) or strip_meta(d.get("text") or "")
        rows.append(d)
    return rows


def load_pairs(source: str | None = None) -> list[dict[str, Any]]:
    pairs = [json.loads(l) for l in (ROOT / "data/pairs/gold_pairs.jsonl").open()]
    if source:
        pairs = [p for p in pairs if p.get("source") == source]
    return pairs


def load_corpus_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "data/clean/statements.jsonl").open():
        d = json.loads(line)
        raw = d.get("raw_text") or d.get("text") or ""
        out[d["doc_id"]] = strip_meta(raw) or strip_meta(d.get("text") or "")
    for line in (ROOT / "data/clean/sentences.jsonl").open():
        d = json.loads(line)
        raw = d.get("raw_text") or d.get("text") or ""
        out[d["sent_id"]] = strip_meta(raw) or strip_meta(d.get("text") or "")
    return out


def load_meetings() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data/labels/meetings.csv")


def load_fedlock_m() -> dict[str, float]:
    fl = json.loads((ROOT / "data/raw/fedlock/data.json").read_text())
    pcs = {s["d"]: s for s in fl["speeches"] if s["st"] == "press_conference"}

    def parse_d(d):
        return datetime.strptime(str(d)[:10], "%Y-%m-%d")

    meetings = load_meetings()
    out: dict[str, float] = {}
    for d in meetings["date"].unique():
        for delta in (0, 1, -1, 2):
            cand = (parse_d(d) + timedelta(days=delta)).strftime("%Y-%m-%d")
            if cand in pcs:
                out[str(d)[:10]] = float(pcs[cand]["m"])
                break
    return out


def load_macro_asof() -> dict[str, dict[str, Any]]:
    pce = pd.read_csv(ROOT / "data/raw/fred/PCEPILFE.csv")
    pce["observation_date"] = pd.to_datetime(pce["observation_date"])
    pce = pce.sort_values("observation_date").reset_index(drop=True)
    pce["pce_yoy"] = pce["PCEPILFE"].pct_change(12) * 100.0

    unrate = pd.read_csv(ROOT / "data/raw/fred/UNRATE.csv")
    unrate["observation_date"] = pd.to_datetime(unrate["observation_date"])
    unrate = unrate.sort_values("observation_date")

    dgs10 = pd.read_csv(ROOT / "data/raw/fred/DGS10.csv")
    dgs10["observation_date"] = pd.to_datetime(dgs10["observation_date"])
    dgs10["DGS10"] = pd.to_numeric(dgs10["DGS10"], errors="coerce")
    dgs10 = dgs10.dropna(subset=["DGS10"]).sort_values("observation_date")

    stmts = load_statements()
    out: dict[str, dict[str, Any]] = {}
    for s in stmts:
        dt = pd.Timestamp(s["date"])
        pce_row = pce[pce["observation_date"] <= dt].tail(1)
        un_row = unrate[unrate["observation_date"] <= dt].tail(1)
        dg_row = dgs10[dgs10["observation_date"] <= dt].tail(1)
        macro: dict[str, Any] = {"asof_date": s["date"]}
        if len(pce_row):
            yoy = pce_row["pce_yoy"].iloc[0]
            level = float(pce_row["PCEPILFE"].iloc[0])
            if pd.notna(yoy):
                macro["core_pce_yoy"] = round(float(yoy), 3)
                macro["core_pce_source"] = "PCEPILFE_yoy"
            else:
                macro["core_pce_level"] = round(level, 3)
                macro["core_pce_source"] = "PCEPILFE_level"
            macro["core_pce_obs_date"] = str(pce_row["observation_date"].iloc[0].date())
        if len(un_row):
            macro["unrate"] = float(un_row["UNRATE"].iloc[0])
            macro["unrate_obs_date"] = str(un_row["observation_date"].iloc[0].date())
        if len(dg_row):
            macro["dgs10"] = float(dg_row["DGS10"].iloc[0])
            macro["dgs10_obs_date"] = str(dg_row["observation_date"].iloc[0].date())
            macro["risk_proxy"] = "DGS10"
        out[s["date"]] = macro
    return out


def era_for_date(date_str: str) -> str:
    d = date_str[:10]
    if d.startswith("2020"):
        return "2020"
    if d >= "2022-01-01" and d <= "2022-12-31":
        return "2022_hikes"
    if d == SVB:
        return "2023_SVB"
    if d >= "2025-01-01":
        return "2025_26"
    if d.startswith("2023"):
        return "2023_other"
    if d.startswith("2024"):
        return "2024"
    return "other"


def call_scores_nouls(client, text: str) -> dict[str, Any]:
    from typesafe_sdk import Score, Noul

    questions: dict[str, Any] = {}
    for dim in SCORE_DIMS:
        questions[dim] = Score(
            instructions=SCORE_INSTRUCTIONS[dim],
            criteria=list(SCORE_LEVELS[dim]),
        )
    for nk in NOUL_KEYS:
        questions[nk] = Noul(
            instructions=NOUL_INSTRUCTIONS[nk],
            criteria={
                "true": "yes — the signal/attribute is present",
                "false": "no — the signal/attribute is absent",
            },
        )

    t0 = time.perf_counter()
    response = client.system_one(
        model=MODEL, state={"statement": text}, questions=questions,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    scores = {}
    nouls = {}
    for dim in SCORE_DIMS:
        ans = response.answers[dim]
        scores[dim] = {
            "score": float(ans.score),
            "confidence": float(ans.confidence),
            "probabilities": {str(k): float(v) for k, v in ans.probabilities.items()},
            "legend": {str(k): v for k, v in ans.legend.items()},
        }
    for nk in NOUL_KEYS:
        ans = response.answers[nk]
        nouls[nk] = float(ans.noul)
    usage = response.usage
    composite = sum(COMPOSITE_WEIGHTS[d] * scores[d]["score"] for d in SCORE_DIMS)
    return {
        "model": response.model,
        "scores": scores,
        "nouls": nouls,
        "composite": float(composite),
        "composite_weights": dict(COMPOSITE_WEIGHTS),
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
    }


def call_choice(client, *, text_a: str, text_b: str, instructions: str,
                state_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    from typesafe_sdk import Choice

    state = {"Text A": text_a, "Text B": text_b}
    if state_extra:
        state.update(state_extra)
    t0 = time.perf_counter()
    response = client.system_one(
        model=MODEL, state=state,
        questions={
            "winner": Choice(
                instructions=instructions,
                criteria={"A": "Text A", "B": "Text B"},
            ),
        },
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    ans = response.answers["winner"]
    usage = response.usage
    return {
        "model": response.model,
        "winner": ans.choice,
        "p_A": float(ans.probabilities.get("A", 0.0)),
        "p_B": float(ans.probabilities.get("B", 0.0)),
        "confidence": float(ans.confidence),
        "probabilities": {k: float(v) for k, v in ans.probabilities.items()},
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
    }


def call_span_choice(client, *, options: dict[str, str], gold_id: str) -> dict[str, Any]:
    from typesafe_sdk import Choice

    state = {oid: text for oid, text in options.items()}
    criteria = {oid: f"Span {oid}" for oid in options}
    t0 = time.perf_counter()
    response = client.system_one(
        model=MODEL, state=state,
        questions={
            "winner": Choice(instructions=SPAN_INSTRUCTIONS, criteria=criteria),
        },
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    ans = response.answers["winner"]
    usage = response.usage
    probs = {k: float(v) for k, v in ans.probabilities.items()}
    return {
        "model": response.model,
        "winner": ans.choice,
        "probabilities": probs,
        "p_gold": float(probs.get(gold_id, 0.0)),
        "confidence": float(ans.confidence),
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
    }


def run_exp3_exp4(client, stmts: list[dict], dry_run: bool = False) -> list:
    results = []

    def one(stmt: dict) -> dict:
        text = stmt["stripped"]
        h = text_hash(text)
        key = hashlib.sha256(f"{MODEL}|exp3_4|scores_nouls|{h}".encode()).hexdigest()
        cached = read_cache(key)
        if cached and cached.get("ok"):
            out = dict(cached)
            out["cache_hit"] = True
            append_jsonl(ANSWERS_PATH, {
                "exp": "exp3_4", "doc_id": stmt["doc_id"], "date": stmt["date"],
                "ok": True, "cache_hit": True, "model": out.get("model"),
                "composite": out.get("composite"),
                "scores": {d: out["scores"][d]["score"] for d in SCORE_DIMS},
                "nouls": out.get("nouls"),
                "input_tokens": 0, "output_tokens": 0,
                "latency_ms": out.get("latency_ms", 0),
            })
            bump("exp3_4", cache_hit=True)
            return out
        if dry_run:
            return {"ok": False, "dry_run": True, "doc_id": stmt["doc_id"]}
        try:
            result = call_scores_nouls(client, text)
            out = {
                "ok": True, "exp": "exp3_4",
                "doc_id": stmt["doc_id"], "date": stmt["date"],
                "hash": h, "cache_key": key, **result, "cache_hit": False,
            }
            write_cache(key, out)
            append_jsonl(ANSWERS_PATH, {
                "exp": "exp3_4", "doc_id": stmt["doc_id"], "date": stmt["date"],
                "ok": True, "cache_hit": False, "model": result["model"],
                "composite": result["composite"],
                "scores": {d: result["scores"][d]["score"] for d in SCORE_DIMS},
                "nouls": result["nouls"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"],
            })
            bump("exp3_4", input_tokens=result["input_tokens"],
                 output_tokens=result["output_tokens"], latency_ms=result["latency_ms"])
            return out
        except SystemExit:
            raise
        except Exception as e:
            err = {
                "ok": False, "exp": "exp3_4", "doc_id": stmt["doc_id"],
                "date": stmt["date"], "error": f"{type(e).__name__}: {e}",
                "cache_key": key,
            }
            append_jsonl(ANSWERS_PATH, err)
            bump("exp3_4", failure=True)
            return err

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one, s): s["doc_id"] for s in stmts}
        for fut in as_completed(futs):
            results.append(fut.result())
    return results


def analyze_exp3(packed: list[dict]) -> dict:
    ok = [r for r in packed if r.get("ok")]
    meetings = load_meetings()
    score_jev = pd.read_csv(ROOT / "results/statement_scores.csv")
    fedlock = load_fedlock_m()

    rows = []
    for r in ok:
        date = r["date"]
        mrow = meetings[meetings["date"] == date]
        d_same = float(mrow["d_same"].iloc[0]) if len(mrow) and pd.notna(mrow["d_same"].iloc[0]) else np.nan
        excl = bool(mrow["exclude_main"].iloc[0]) if len(mrow) else False
        scheduled = bool(mrow["is_scheduled"].iloc[0]) if len(mrow) else True
        sj = score_jev[score_jev["date"] == date]
        score_jev_v = float(sj["score_jev"].iloc[0]) if len(sj) and pd.notna(sj["score_jev"].iloc[0]) else np.nan
        fl_m = fedlock.get(date, np.nan)
        row = {
            "doc_id": r["doc_id"], "date": date, "composite": r["composite"],
            "d_same": d_same, "score_jev": score_jev_v, "fedlock_m": fl_m,
            "exclude_main": excl, "is_scheduled": scheduled, "flag_svb": date == SVB,
        }
        for d in SCORE_DIMS:
            row[d] = r["scores"][d]["score"]
        rows.append(row)
    df = pd.DataFrame(rows)

    main = df[
        (df["is_scheduled"] == True)
        & (df["exclude_main"] == False)
        & ~df["date"].isin(CRISIS)
    ].copy()

    corr = {
        "vs_d_same": bootstrap_spearman(main["composite"], main["d_same"]),
        "vs_score_jev": bootstrap_spearman(main["composite"], main["score_jev"]),
        "vs_fedlock_m": bootstrap_spearman(
            main.loc[main["fedlock_m"].notna(), "composite"],
            main.loc[main["fedlock_m"].notna(), "fedlock_m"],
        ),
    }
    act = main[main["d_same"].abs() > 1e-9]
    corr["vs_d_same_action_days"] = bootstrap_spearman(act["composite"], act["d_same"])

    base_rho = corr["vs_d_same"]["rho"]
    ablations = {}
    for drop in SCORE_DIMS:
        remain = [d for d in SCORE_DIMS if d != drop]
        w = 1.0 / len(remain)
        abl = main[remain].mean(axis=1)
        rho = bootstrap_spearman(abl, main["d_same"])
        ablations[f"drop_{drop}"] = {
            **rho,
            "delta_rho_vs_full": (
                None if rho["rho"] is None or base_rho is None
                else float(rho["rho"] - base_rho)
            ),
            "remaining_dims": remain,
            "weights": {d: w for d in remain},
        }

    per_dim = {}
    for d in SCORE_DIMS:
        per_dim[d] = {
            "vs_d_same": bootstrap_spearman(main[d], main["d_same"]),
            "vs_score_jev": bootstrap_spearman(main[d], main["score_jev"]),
        }

    out = {
        "run_id": RUN_ID, "model": MODEL,
        "n_docs": len(ok), "n_main": int(len(main)),
        "composite_weights": COMPOSITE_WEIGHTS,
        "score_levels": SCORE_LEVELS,
        "score_instructions": SCORE_INSTRUCTIONS,
        "correlations": corr,
        "per_dimension": per_dim,
        "ablations_drop_one": ablations,
        "rows": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exp3_composite.json").write_text(json.dumps(out, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(OUT_DIR / "exp3_composite.csv", index=False)
    return out


def analyze_exp4(packed: list[dict]) -> dict:
    ok = [r for r in packed if r.get("ok")]
    rows = []
    for r in ok:
        row = {"doc_id": r["doc_id"], "date": r["date"], "era": era_for_date(r["date"])}
        for nk in NOUL_KEYS:
            row[nk] = r["nouls"][nk]
        highs = [nk for nk in NOUL_KEYS if r["nouls"][nk] >= 0.6]
        row["n_high_ge_0.6"] = len(highs)
        row["high_nouls"] = highs
        rows.append(row)
    df = pd.DataFrame(rows)

    by_era = {}
    for era, g in df.groupby("era"):
        by_era[era] = {
            "n": int(len(g)),
            **{nk: {
                "mean": float(g[nk].mean()),
                "std": float(g[nk].std(ddof=1)) if len(g) > 1 else 0.0,
                "median": float(g[nk].median()),
            } for nk in NOUL_KEYS},
        }

    svb = df[df["date"] == SVB]
    svb_detail = None
    if len(svb):
        svb_detail = {
            "date": SVB, "doc_id": svb.iloc[0]["doc_id"],
            "nouls": {nk: float(svb.iloc[0][nk]) for nk in NOUL_KEYS},
            "note": "2023-03-22 SVB / banking-stress meeting",
        }

    multi = df[df["n_high_ge_0.6"] >= 2].sort_values("n_high_ge_0.6", ascending=False)
    multi_cases = multi.head(25).to_dict(orient="records")

    noul_corr = {}
    for i, a in enumerate(NOUL_KEYS):
        for b in NOUL_KEYS[i + 1:]:
            rho, n = spearman(df[a], df[b])
            noul_corr[f"{a}__{b}"] = {
                "rho": None if not np.isfinite(rho) else float(rho), "n": n,
            }

    out = {
        "run_id": RUN_ID, "model": MODEL, "n_docs": len(ok),
        "noul_keys": NOUL_KEYS, "noul_instructions": NOUL_INSTRUCTIONS,
        "by_era": by_era, "svb_2023_03_22": svb_detail,
        "multi_high_threshold": 0.6, "n_multi_high": int(len(multi)),
        "multi_high_cases": multi_cases, "noul_pair_spearman": noul_corr,
        "rows": rows,
    }
    (OUT_DIR / "exp4_nouls.json").write_text(json.dumps(out, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(OUT_DIR / "exp4_nouls.csv", index=False)
    return out


def load_baseline_stratum_a(corpus: dict[str, str], pairs: list[dict]) -> dict:
    answers_path = ROOT / "runs/jev/answers.jsonl"
    by_key: dict[str, dict] = {}
    extreme_ids = {p["pair_id"] for p in pairs}
    if answers_path.exists():
        for line in answers_path.open():
            d = json.loads(line)
            if d.get("kind") != "choice":
                continue
            if d.get("pair_id") not in extreme_ids:
                continue
            if d.get("error") or d.get("ok") is False:
                continue
            k = f"{d['pair_id']}:{d['order']}"
            prev = by_key.get(k)
            if prev is None or (prev.get("cache_hit") and not d.get("cache_hit")):
                by_key[k] = d

    judgments = {}
    for p in pairs:
        pid = p["pair_id"]
        ab = by_key.get(f"{pid}:ab")
        ba = by_key.get(f"{pid}:ba")
        probs_a, probs_b, winners = [], [], []
        order_detail = {}
        if ab:
            probs_a.append(float(ab["p_A"]))
            probs_b.append(float(ab["p_B"]))
            winners.append("a" if ab["winner"] == "A" else "b")
            order_detail["ab"] = {
                "p_A": float(ab["p_A"]), "p_B": float(ab["p_B"]),
                "winner": ab["winner"],
                "p_gold": float(ab["p_A"]) if p["gold"] == "a" else float(ab["p_B"]),
            }
        if ba:
            probs_a.append(float(ba["p_B"]))
            probs_b.append(float(ba["p_A"]))
            winners.append("b" if ba["winner"] == "A" else "a")
            p_gold = float(ba["p_B"]) if p["gold"] == "a" else float(ba["p_A"])
            order_detail["ba"] = {
                "p_A": float(ba["p_A"]), "p_B": float(ba["p_B"]),
                "winner": ba["winner"], "p_gold": p_gold,
            }
        if not probs_a:
            continue
        p_a = sum(probs_a) / len(probs_a)
        p_b = sum(probs_b) / len(probs_b)
        winner = "a" if p_a >= p_b else "b"
        p_gold = p_a if p["gold"] == "a" else p_b
        judgments[pid] = {
            "pair_id": pid, "gold": p["gold"],
            "p_A_avg": p_a, "p_B_avg": p_b, "p_gold": p_gold,
            "winner_avg": winner, "inverted": winner != p["gold"],
            "order_flip": len(set(winners)) > 1 if len(winners) == 2 else None,
            "orders": order_detail, "a": p["a"], "b": p["b"],
        }
    return judgments


def ece_and_reliability(rows, n_bins=10):
    if not rows:
        return {"ece": None, "bins": []}
    ps = np.array([r["p_gold"] for r in rows], dtype=float)
    correct = np.array([0.0 if r["inverted"] else 1.0 for r in rows])
    bins = []
    ece = 0.0
    edges = np.linspace(0, 1, n_bins + 1)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (ps >= lo) & (ps <= hi) if i == n_bins - 1 else ((ps >= lo) & (ps < hi))
        if mask.sum() == 0:
            bins.append({"lo": float(lo), "hi": float(hi), "n": 0,
                         "mean_p": None, "emp_freq": None})
            continue
        mean_p = float(ps[mask].mean())
        emp = float(correct[mask].mean())
        bins.append({"lo": float(lo), "hi": float(hi), "n": int(mask.sum()),
                     "mean_p": mean_p, "emp_freq": emp})
        ece += (mask.sum() / len(ps)) * abs(mean_p - emp)
    return {"ece": float(ece), "n_bins": n_bins, "bins": bins}


def run_exp5(client, corpus: dict[str, str], dry_run: bool = False) -> dict:
    pairs = load_pairs("extreme")
    assert len(pairs) == 40, len(pairs)
    baseline = load_baseline_stratum_a(corpus, pairs)

    jobs = []
    for p in pairs:
        for para in PARA_PHRASES:
            for order in ("ab", "ba"):
                jobs.append((p, para, order))

    def one(job):
        p, para, order = job
        text_a = corpus[p["a"]]
        text_b = corpus[p["b"]]
        if order == "ab":
            da, db = text_a, text_b
            id_a, id_b = p["a"], p["b"]
        else:
            da, db = text_b, text_a
            id_a, id_b = p["b"], p["a"]
        ha, hb = text_hash(da), text_hash(db)
        key = hashlib.sha256(
            f"{MODEL}|exp5|{para['id']}|{ha}|{hb}|{order}".encode()
        ).hexdigest()
        cached = read_cache(key)
        if cached and cached.get("ok"):
            out = dict(cached)
            out["cache_hit"] = True
            append_jsonl(ANSWERS_PATH, {
                "exp": "exp5", "pair_id": p["pair_id"], "para_id": para["id"],
                "order": order, "ok": True, "cache_hit": True,
                "winner": out.get("winner"), "p_A": out.get("p_A"),
                "p_B": out.get("p_B"), "gold": p["gold"],
            })
            bump("exp5", cache_hit=True)
            return out
        if dry_run:
            return {"ok": False, "dry_run": True}
        try:
            result = call_choice(
                client, text_a=da, text_b=db, instructions=para["instructions"],
            )
            if order == "ab":
                p_gold = result["p_A"] if p["gold"] == "a" else result["p_B"]
                winner_mapped = "a" if result["winner"] == "A" else "b"
            else:
                p_gold = result["p_B"] if p["gold"] == "a" else result["p_A"]
                winner_mapped = "b" if result["winner"] == "A" else "a"
            out = {
                "ok": True, "exp": "exp5", "pair_id": p["pair_id"],
                "para_id": para["id"], "order": order,
                "instructions": para["instructions"],
                "gold": p["gold"], "id_A": id_a, "id_B": id_b,
                "hash_A": ha, "hash_B": hb, "cache_key": key,
                "winner": result["winner"], "winner_mapped": winner_mapped,
                "p_A": result["p_A"], "p_B": result["p_B"], "p_gold": p_gold,
                "confidence": result["confidence"], "model": result["model"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"], "cache_hit": False,
            }
            write_cache(key, out)
            append_jsonl(ANSWERS_PATH, out)
            bump("exp5", input_tokens=result["input_tokens"],
                 output_tokens=result["output_tokens"], latency_ms=result["latency_ms"])
            return out
        except SystemExit:
            raise
        except Exception as e:
            err = {
                "ok": False, "exp": "exp5", "pair_id": p["pair_id"],
                "para_id": para["id"], "order": order,
                "error": f"{type(e).__name__}: {e}",
            }
            append_jsonl(ANSWERS_PATH, err)
            bump("exp5", failure=True)
            return err

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for fut in as_completed(futs):
            results.append(fut.result())

    by_para: dict[str, list] = defaultdict(list)
    for para in PARA_PHRASES:
        pid_results = defaultdict(dict)
        for r in results:
            if not r.get("ok") or r.get("para_id") != para["id"]:
                continue
            pid_results[r["pair_id"]][r["order"]] = r
        for p in pairs:
            pid = p["pair_id"]
            orders = pid_results.get(pid, {})
            ab, ba = orders.get("ab"), orders.get("ba")
            if not ab and not ba:
                continue
            p_golds, winners, probs_a, probs_b = [], [], [], []
            if ab:
                p_golds.append(ab["p_gold"]); winners.append(ab["winner_mapped"])
                probs_a.append(ab["p_A"]); probs_b.append(ab["p_B"])
            if ba:
                p_golds.append(ba["p_gold"]); winners.append(ba["winner_mapped"])
                probs_a.append(ba["p_B"]); probs_b.append(ba["p_A"])
            p_gold_avg = float(np.mean(p_golds))
            p_a = float(np.mean(probs_a)); p_b = float(np.mean(probs_b))
            winner = "a" if p_a >= p_b else "b"
            base = baseline.get(pid)
            base_p_gold = base["p_gold"] if base else None
            row = {
                "pair_id": pid, "gold": p["gold"], "p_gold": p_gold_avg,
                "winner_avg": winner, "inverted": winner != p["gold"],
                "order_flip": len(set(winners)) > 1 if len(winners) == 2 else None,
                "baseline_p_gold": base_p_gold,
                "abs_delta_p_gold": (
                    abs(p_gold_avg - base_p_gold) if base_p_gold is not None else None
                ),
                "baseline_inverted": base["inverted"] if base else None,
            }
            by_para[para["id"]].append(row)

    para_summaries = {}
    for para in PARA_PHRASES:
        rows = by_para[para["id"]]
        n_inv = sum(1 for r in rows if r["inverted"])
        n_flip = sum(1 for r in rows if r["order_flip"])
        deltas = [r["abs_delta_p_gold"] for r in rows if r["abs_delta_p_gold"] is not None]
        cal = ece_and_reliability(rows)
        para_summaries[para["id"]] = {
            "instructions": para["instructions"],
            "n_pairs": len(rows),
            "inversion": binomial_rate(n_inv, len(rows)),
            "order_flip_rate": binomial_rate(n_flip, len(rows)),
            "mean_abs_delta_p_gold_vs_baseline": float(np.mean(deltas)) if deltas else None,
            "mean_p_gold": float(np.mean([r["p_gold"] for r in rows])) if rows else None,
            "calibration": cal, "pairs": rows,
        }

    base_rows = list(baseline.values())
    n_inv_b = sum(1 for r in base_rows if r["inverted"])
    n_flip_b = sum(1 for r in base_rows if r["order_flip"])
    baseline_summary = {
        "instructions": PARA_BASELINE, "criterion": CRITERION,
        "n_pairs": len(base_rows),
        "inversion": binomial_rate(n_inv_b, len(base_rows)),
        "order_flip_rate": binomial_rate(n_flip_b, len(base_rows)),
        "mean_p_gold": float(np.mean([r["p_gold"] for r in base_rows])) if base_rows else None,
        "calibration": ece_and_reliability([
            {"p_gold": r["p_gold"], "inverted": r["inverted"]} for r in base_rows
        ]),
    }

    out = {
        "run_id": RUN_ID, "model": MODEL,
        "n_calls_requested": len(jobs),
        "n_calls_ok": sum(1 for r in results if r.get("ok")),
        "paraphrase_strings_exact": {
            "baseline": PARA_BASELINE,
            **{p["id"]: p["instructions"] for p in PARA_PHRASES},
        },
        "baseline": baseline_summary,
        "paraphrases": para_summaries,
    }
    (OUT_DIR / "exp5_calibration.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def build_span_items(n: int = 50, seed: int = SEED) -> list[dict]:
    sents = [json.loads(l) for l in (ROOT / "data/clean/sentences.jsonl").open()]
    hawks = [s for s in sents if s["label"] == "hawkish"]
    doves = [s for s in sents if s["label"] == "dovish"]
    neuts = [s for s in sents if s["label"] == "neutral"]
    rng = np.random.default_rng(seed)

    by_group: dict[tuple, list] = defaultdict(list)
    for s in sents:
        by_group[(s.get("year"), s.get("doc_type"))].append(s)

    if len(hawks) < n:
        chosen = list(hawks)
    else:
        idx = rng.choice(len(hawks), size=n, replace=False)
        chosen = [hawks[i] for i in idx]

    items = []
    for i, gold in enumerate(chosen):
        group = by_group[(gold.get("year"), gold.get("doc_type"))]
        nearby_dist = [
            s for s in group
            if s["sent_id"] != gold["sent_id"] and s["label"] in ("dovish", "neutral")
        ]
        n_dist = int(rng.integers(3, 6))
        distractors = []
        if len(nearby_dist) >= n_dist:
            pick = rng.choice(len(nearby_dist), size=n_dist, replace=False)
            distractors = [nearby_dist[j] for j in pick]
        else:
            distractors = list(nearby_dist)
            need = n_dist - len(distractors)
            pool = [
                s for s in (doves + neuts)
                if s["sent_id"] != gold["sent_id"]
                and s["sent_id"] not in {d["sent_id"] for d in distractors}
            ]
            if need > 0 and pool:
                pick = rng.choice(len(pool), size=min(need, len(pool)), replace=False)
                distractors.extend([pool[j] for j in pick])

        options = [gold] + distractors
        rng.shuffle(options)
        opt_map = {}
        gold_key = None
        for j, s in enumerate(options):
            key = f"S{j+1}"
            text = strip_meta(s.get("raw_text") or s.get("text") or "")
            opt_map[key] = {"sent_id": s["sent_id"], "label": s["label"], "text": text}
            if s["sent_id"] == gold["sent_id"]:
                gold_key = key
        items.append({
            "item_id": f"SPAN{i+1:03d}",
            "gold_key": gold_key,
            "gold_sent_id": gold["sent_id"],
            "n_options": len(opt_map),
            "options": opt_map,
        })
    return items[:n]


def run_exp6(client, dry_run: bool = False) -> dict:
    items = build_span_items(50, SEED)

    def one(item):
        texts = {k: v["text"] for k, v in item["options"].items()}
        blob = "|".join(f"{k}:{text_hash(texts[k])}" for k in sorted(texts))
        key = hashlib.sha256(
            f"{MODEL}|exp6|span|{item['item_id']}|{blob}".encode()
        ).hexdigest()
        cached = read_cache(key)
        if cached and cached.get("ok"):
            out = dict(cached)
            out["cache_hit"] = True
            append_jsonl(ANSWERS_PATH, {
                "exp": "exp6", "item_id": item["item_id"],
                "ok": True, "cache_hit": True,
                "winner": out.get("winner"), "p_gold": out.get("p_gold"),
                "gold_key": item["gold_key"],
            })
            bump("exp6", cache_hit=True)
            return out
        if dry_run:
            return {"ok": False, "dry_run": True, "item_id": item["item_id"]}
        try:
            result = call_span_choice(client, options=texts, gold_id=item["gold_key"])
            inverted = result["winner"] != item["gold_key"]
            out = {
                "ok": True, "exp": "exp6", "item_id": item["item_id"],
                "gold_key": item["gold_key"], "gold_sent_id": item["gold_sent_id"],
                "n_options": item["n_options"],
                "option_sent_ids": {k: v["sent_id"] for k, v in item["options"].items()},
                "option_labels": {k: v["label"] for k, v in item["options"].items()},
                "winner": result["winner"], "p_gold": result["p_gold"],
                "probabilities": result["probabilities"], "inverted": inverted,
                "confidence": result["confidence"], "model": result["model"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"],
                "cache_key": key, "cache_hit": False,
            }
            write_cache(key, out)
            append_jsonl(ANSWERS_PATH, out)
            bump("exp6", input_tokens=result["input_tokens"],
                 output_tokens=result["output_tokens"], latency_ms=result["latency_ms"])
            return out
        except SystemExit:
            raise
        except Exception as e:
            err = {
                "ok": False, "exp": "exp6", "item_id": item["item_id"],
                "error": f"{type(e).__name__}: {e}",
            }
            append_jsonl(ANSWERS_PATH, err)
            bump("exp6", failure=True)
            return err

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, it) for it in items]
        for fut in as_completed(futs):
            results.append(fut.result())

    ok = [r for r in results if r.get("ok")]
    n_inv = sum(1 for r in ok if r.get("inverted"))
    p_golds = [r["p_gold"] for r in ok]
    cost_tok = sum(int(r.get("input_tokens") or 0) for r in ok if not r.get("cache_hit"))
    all_tok = sum(int(r.get("input_tokens") or 0) for r in ok)

    out = {
        "run_id": RUN_ID, "model": MODEL, "seed": SEED,
        "instructions": SPAN_INSTRUCTIONS,
        "n_items": len(items), "n_ok": len(ok),
        "inversion": binomial_rate(n_inv, len(ok)),
        "mean_p_gold": float(np.mean(p_golds)) if p_golds else None,
        "mean_p_gold_ste": (
            float(np.std(p_golds, ddof=1) / np.sqrt(len(p_golds)))
            if len(p_golds) > 1 else None
        ),
        "cost_usd_live": round(cost_tok * PRICE_PER_MTOK_INPUT / 1e6, 8),
        "cost_usd_all_tokens_recorded": round(all_tok * PRICE_PER_MTOK_INPUT / 1e6, 8),
        "input_tokens_recorded": all_tok,
        "items": ok,
        "item_construction": {
            "n_distractors_range": [3, 5],
            "gold": "Shah hawkish sentence",
            "distractors": "nearby same (year, doc_type) neutrals/doves, else random pool",
            "cap": 50, "seed": SEED,
        },
    }
    (OUT_DIR / "exp6_span_choice.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def run_exp7(client, corpus: dict[str, str], dry_run: bool = False) -> dict:
    pairs = load_pairs("extreme")
    macro = load_macro_asof()
    baseline = load_baseline_stratum_a(corpus, pairs)

    jobs = [(p, order) for p in pairs for order in ("ab", "ba")]

    def compact(m):
        return {
            k: v for k, v in m.items()
            if k in ("core_pce_yoy", "core_pce_level", "unrate", "dgs10",
                     "asof_date", "risk_proxy", "core_pce_source")
        }

    def one(job):
        p, order = job
        text_a = corpus[p["a"]]
        text_b = corpus[p["b"]]
        date_a = p["a"].replace("stmt-", "")
        date_b = p["b"].replace("stmt-", "")
        macro_a = macro.get(date_a, {})
        macro_b = macro.get(date_b, {})
        if order == "ab":
            da, db = text_a, text_b
            ma, mb = macro_a, macro_b
            id_a, id_b = p["a"], p["b"]
        else:
            da, db = text_b, text_a
            ma, mb = macro_b, macro_a
            id_a, id_b = p["b"], p["a"]

        ha, hb = text_hash(da), text_hash(db)
        macro_blob = json.dumps({"A": compact(ma), "B": compact(mb)}, sort_keys=True)
        key = hashlib.sha256(
            f"{MODEL}|exp7|macro|{ha}|{hb}|{order}|{macro_blob}".encode()
        ).hexdigest()
        cached = read_cache(key)
        if cached and cached.get("ok"):
            out = dict(cached)
            out["cache_hit"] = True
            append_jsonl(ANSWERS_PATH, {
                "exp": "exp7", "pair_id": p["pair_id"], "order": order,
                "arm": "macro", "ok": True, "cache_hit": True,
                "winner": out.get("winner"), "p_gold": out.get("p_gold"),
            })
            bump("exp7", cache_hit=True)
            return out
        if dry_run:
            return {"ok": False, "dry_run": True}
        try:
            result = call_choice(
                client, text_a=da, text_b=db,
                instructions=MACRO_INSTRUCTIONS,
                state_extra={"macro_A": compact(ma), "macro_B": compact(mb)},
            )
            if order == "ab":
                p_gold = result["p_A"] if p["gold"] == "a" else result["p_B"]
                winner_mapped = "a" if result["winner"] == "A" else "b"
            else:
                p_gold = result["p_B"] if p["gold"] == "a" else result["p_A"]
                winner_mapped = "b" if result["winner"] == "A" else "a"
            out = {
                "ok": True, "exp": "exp7", "arm": "macro",
                "pair_id": p["pair_id"], "order": order, "gold": p["gold"],
                "id_A": id_a, "id_B": id_b,
                "macro_A": compact(ma), "macro_B": compact(mb),
                "winner": result["winner"], "winner_mapped": winner_mapped,
                "p_A": result["p_A"], "p_B": result["p_B"], "p_gold": p_gold,
                "confidence": result["confidence"], "model": result["model"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"],
                "cache_key": key, "cache_hit": False,
            }
            write_cache(key, out)
            append_jsonl(ANSWERS_PATH, out)
            bump("exp7", input_tokens=result["input_tokens"],
                 output_tokens=result["output_tokens"], latency_ms=result["latency_ms"])
            return out
        except SystemExit:
            raise
        except Exception as e:
            err = {
                "ok": False, "exp": "exp7", "pair_id": p["pair_id"],
                "order": order, "error": f"{type(e).__name__}: {e}",
            }
            append_jsonl(ANSWERS_PATH, err)
            bump("exp7", failure=True)
            return err

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for fut in as_completed(futs):
            results.append(fut.result())

    by_pair: dict[str, dict] = defaultdict(dict)
    for r in results:
        if r.get("ok"):
            by_pair[r["pair_id"]][r["order"]] = r

    macro_rows = []
    for p in pairs:
        pid = p["pair_id"]
        orders = by_pair.get(pid, {})
        ab, ba = orders.get("ab"), orders.get("ba")
        if not ab and not ba:
            continue
        probs_a, probs_b, p_golds, winners = [], [], [], []
        if ab:
            probs_a.append(ab["p_A"]); probs_b.append(ab["p_B"])
            p_golds.append(ab["p_gold"]); winners.append(ab["winner_mapped"])
        if ba:
            probs_a.append(ba["p_B"]); probs_b.append(ba["p_A"])
            p_golds.append(ba["p_gold"]); winners.append(ba["winner_mapped"])
        p_a = float(np.mean(probs_a)); p_b = float(np.mean(probs_b))
        winner = "a" if p_a >= p_b else "b"
        base = baseline.get(pid)
        macro_rows.append({
            "pair_id": pid, "gold": p["gold"],
            "p_gold_macro": float(np.mean(p_golds)),
            "winner_macro": winner,
            "inverted_macro": winner != p["gold"],
            "order_flip_macro": len(set(winners)) > 1 if len(winners) == 2 else None,
            "p_gold_absolute": base["p_gold"] if base else None,
            "winner_absolute": base["winner_avg"] if base else None,
            "inverted_absolute": base["inverted"] if base else None,
            "agree_abs_macro": (winner == base["winner_avg"]) if base else None,
        })

    n_inv_m = sum(1 for r in macro_rows if r["inverted_macro"])
    n_inv_a = sum(1 for r in macro_rows if r["inverted_absolute"])
    n_agree = sum(1 for r in macro_rows if r["agree_abs_macro"])
    n_agree_denom = sum(1 for r in macro_rows if r["agree_abs_macro"] is not None)

    macro_p = [r["p_gold_macro"] for r in macro_rows]
    abs_p = [r["p_gold_absolute"] for r in macro_rows if r["p_gold_absolute"] is not None]
    if len(macro_rows) >= 3:
        sp = bootstrap_spearman(
            [r["p_gold_macro"] for r in macro_rows],
            [r["p_gold_absolute"] for r in macro_rows],
        )
    else:
        sp = {"rho": None, "n": len(macro_rows)}

    out = {
        "run_id": RUN_ID, "model": MODEL,
        "instructions_macro": MACRO_INSTRUCTIONS,
        "instructions_absolute": PARA_BASELINE,
        "macro_series": {
            "core_pce": "PCEPILFE YoY (12m) if available else level; FRED as-of doc date",
            "unrate": "UNRATE as-of doc date",
            "risk": "DGS10 (VIXCLS not in local dump; specified fallback)",
        },
        "gold_note": (
            "Gold still from rate extremes (Stratum A). Macro arm asks hawkishness "
            "conditional on provided macro; agreement with rate-extreme gold is a "
            "limited diagnostic, not a pure test of macro-conditional judgment."
        ),
        "n_pairs": len(macro_rows),
        "n_macro_calls_ok": sum(1 for r in results if r.get("ok")),
        "inversion_macro": binomial_rate(n_inv_m, len(macro_rows)),
        "inversion_absolute": binomial_rate(n_inv_a, len(macro_rows)),
        "agreement_abs_vs_macro_winners": binomial_rate(n_agree, n_agree_denom),
        "spearman_p_gold_abs_vs_macro": sp,
        "mean_p_gold_macro": float(np.mean(macro_p)) if macro_p else None,
        "mean_p_gold_absolute": float(np.mean(abs_p)) if abs_p else None,
        "pairs": macro_rows,
    }
    (OUT_DIR / "exp7_macro_relative.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def write_summary(exp3, exp4, exp5, exp6, exp7) -> dict:
    by_exp = {k: dict(v) for k, v in _progress["by_exp"].items()}
    summary = {
        "run_id": RUN_ID,
        "model": MODEL,
        "price_per_mtok_input_usd": PRICE_PER_MTOK_INPUT,
        "total": {
            "n_calls": _progress["n"],
            "n_cache_hits": _progress["cache_hits"],
            "n_failures": _progress["failures"],
            "input_tokens": _progress["input_tokens"],
            "output_tokens": _progress["output_tokens"],
            "latency_ms_sum": _progress["latency_ms"],
            "cost_usd": round(_progress["usd"], 8),
        },
        "by_experiment": by_exp,
        "key_findings": {
            "exp3": (
                f"Composite equal-weight Scores rho(d_same)="
                f"{(exp3.get('correlations') or {}).get('vs_d_same', {}).get('rho')}; "
                f"vs score_jev="
                f"{(exp3.get('correlations') or {}).get('vs_score_jev', {}).get('rho')}; "
                f"vs FedLock m="
                f"{(exp3.get('correlations') or {}).get('vs_fedlock_m', {}).get('rho')}"
            ),
            "exp4": (
                f"SVB banking Noul="
                f"{((exp4.get('svb_2023_03_22') or {}).get('nouls') or {}).get('acknowledges_banking_stress')}; "
                f"n multi-high>=2: {exp4.get('n_multi_high')}"
            ),
            "exp5": (
                "baseline inv="
                f"{((exp5.get('baseline') or {}).get('inversion') or {}).get('rate')}; "
                + "; ".join(
                    f"{pid} inv={((exp5.get('paraphrases') or {}).get(pid) or {}).get('inversion', {}).get('rate')}, "
                    f"|Dp|={((exp5.get('paraphrases') or {}).get(pid) or {}).get('mean_abs_delta_p_gold_vs_baseline')}, "
                    f"ECE={((exp5.get('paraphrases') or {}).get(pid) or {}).get('calibration', {}).get('ece')}"
                    for pid in (exp5.get("paraphrases") or {})
                )
            ),
            "exp6": (
                f"span Choice inv={((exp6.get('inversion') or {}).get('rate'))}, "
                f"mean p(gold)={exp6.get('mean_p_gold')}, "
                f"cost~${exp6.get('cost_usd_live')}"
            ),
            "exp7": (
                f"macro inv={((exp7.get('inversion_macro') or {}).get('rate'))}, "
                f"abs inv={((exp7.get('inversion_absolute') or {}).get('rate'))}, "
                f"agree={((exp7.get('agreement_abs_vs_macro_winners') or {}).get('rate'))}"
            ),
        },
    }
    (OUT_DIR / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _fmt_rho(d):
    if not d or d.get("rho") is None:
        return "n/a"
    ste = d.get("ste")
    ste_s = f", STE={ste:.3f}" if ste is not None else ""
    return f"rho={d['rho']:.3f} (n={d['n']}{ste_s})"


def write_findings(exp3, exp4, exp5, exp6, exp7, summary) -> None:
    """Academic / arXiv-style draft section for merge into ANALYSIS."""
    c3 = exp3.get("correlations") or {}
    abl = exp3.get("ablations_drop_one") or {}
    abl_lines = []
    for k, v in abl.items():
        dr = v.get("delta_rho_vs_full")
        dim = k.replace("drop_", "")
        if dr is not None:
            abl_lines.append(f"- Drop `{dim}`: {_fmt_rho(v)}; Delta-rho vs full = {dr:.3f}")
        else:
            abl_lines.append(f"- Drop `{dim}`: {_fmt_rho(v)}")

    svb = exp4.get("svb_2023_03_22") or {}
    svb_nouls = svb.get("nouls") or {}

    era_lines = []
    for era, stats in sorted((exp4.get("by_era") or {}).items()):
        means = ", ".join(
            f"{nk}={stats[nk]['mean']:.2f}" for nk in NOUL_KEYS if nk in stats
        )
        era_lines.append(f"- **{era}** (n={stats['n']}): {means}")

    para_blocks = []
    for pid, ps in (exp5.get("paraphrases") or {}).items():
        inv = ps.get("inversion") or {}
        flip = ps.get("order_flip_rate") or {}
        cal = ps.get("calibration") or {}
        para_blocks.append(
            f"- `{pid}` — instructions: \"{ps.get('instructions')}\". "
            f"Inversion {inv.get('rate')} (n={inv.get('n')}, STE={inv.get('ste')}). "
            f"Order-flip rate {flip.get('rate')}. "
            f"Mean |p_gold - p_gold_baseline| = {ps.get('mean_abs_delta_p_gold_vs_baseline')}. "
            f"ECE = {cal.get('ece')}."
        )

    base5 = exp5.get("baseline") or {}
    inv5b = base5.get("inversion") or {}
    inv6 = exp6.get("inversion") or {}
    inv7m = exp7.get("inversion_macro") or {}
    inv7a = exp7.get("inversion_absolute") or {}
    agr7 = exp7.get("agreement_abs_vs_macro_winners") or {}

    md = f"""# Experiments 3–7 — Findings (draft for ANALYSIS)

**run_id:** `{RUN_ID}`  
**model:** `{MODEL}` (TypeSafe SystemOne; resolved model ids logged per call)  
**criterion family:** inflation / hawkishness  
**cost (this experiment suite):** ${summary['total']['cost_usd']:.5f} over {summary['total']['n_calls']} logical calls ({summary['total']['n_cache_hits']} cache hits; {summary['total']['input_tokens']} input tokens at ${PRICE_PER_MTOK_INPUT}/MTok input).

This section reports five follow-up probes that hold the corpus, gold pairs, and primary criterion family fixed while varying the question interface (multi-Score composite, multi-label Noul, paraphrase Choice, span Choice, and macro-conditioned Choice). Gold labels are unchanged: Stratum A extremes remain rate-path constructed; document-level `d_same` remains the FRED same-day funds-target move. All live calls use `jev-latest` via `typesafe-sdk`; answers are cached under `runs/jev/exp_cache/`.

---

## Experiment 3 — Composite atomic Scores

### Methods

For each of {exp3.get('n_docs')} presser-opening statements (meta-stripped), a single SystemOne request elicited four ordered Scores (levels 0–4) jointly with the Exp4 Nouls (cost sharing). Dimensions and equal weights:

| Dimension | Weight | Construct |
|-----------|-------:|-----------|
| `inflation_urgency` | 0.25 | Urgency of the inflation fight |
| `tightness_preference` | 0.25 | Preference for tighter policy |
| `reaction_toughness` | 0.25 | Toughness of reaction function / willingness to accept growth pain |
| `guidance_firmness` | 0.25 | Firmness of forward guidance / higher-for-longer tone |

Composite = equal-weight mean of the four scores ($w_d = 1/4$). Correlations use Spearman rho with bootstrap STE (1,000 resamples, seed {SEED}) on scheduled, non-excluded, non-crisis meetings (n={exp3.get('n_main')}). Ablation drops one dimension and re-averages the remaining three with equal weight.

### Results

- Composite vs `d_same`: {_fmt_rho(c3.get('vs_d_same'))}
- Composite vs `d_same` (action days only): {_fmt_rho(c3.get('vs_d_same_action_days'))}
- Composite vs existing `score_jev`: {_fmt_rho(c3.get('vs_score_jev'))}
- Composite vs FedLock press-conference `m` (meeting±1d match): {_fmt_rho(c3.get('vs_fedlock_m'))}

Leave-one-dimension-out (Delta-rho vs full composite on `d_same`):

{chr(10).join(abl_lines) if abl_lines else '- (none)'}

Artifacts: `results/experiments/exp3_composite.json`, `exp3_composite.csv`.

### Interpretation

The four-way composite is a structured absolute score of communicated stance, not a pairwise Choice aggregate. Concordance with `score_jev` tests whether the richer rubric collapses to the single hawkishness Score used in the main run; concordance with `d_same` and FedLock `m` situates the composite in the same external comparisons as Gates 3 and 7. Ablation Delta-rho identifies which atomic construct carries most of the association with the rate move.

### Limitations

Equal weights are a pre-specified convenience, not estimated from data. Score levels are verbal rubrics whose interval scaling is assumed when averaging. `d_same` labels policy outcomes, not text; holds can be text-hawkish, so modest rho is expected and is not by itself a failure of the composite.

---

## Experiment 4 — Multi-label Nouls

### Methods

The same packed SystemOne call returned four Nouls (yes-probability in [0,1]): `signals_cut_soon`, `signals_higher_for_longer`, `acknowledges_banking_stress`, `blames_supply_shocks`. Eras are calendar partitions (2020; 2022 hike year; 2023-03-22 SVB meeting; other 2023; 2024; 2025–26; residual). Multi-label cases are documents with at least two Nouls >= 0.6. Pairwise Spearman among Nouls documents mutual non-exclusivity.

### Results

Mean Noul by era:

{chr(10).join(era_lines) if era_lines else '- (none)'}

**2023-03-22 (SVB) banking Noul:** `acknowledges_banking_stress` = {svb_nouls.get('acknowledges_banking_stress')}  
(other Nouls that meeting: cut_soon={svb_nouls.get('signals_cut_soon')}, H4L={svb_nouls.get('signals_higher_for_longer')}, supply={svb_nouls.get('blames_supply_shocks')}; doc `{svb.get('doc_id')}`).

Documents with >=2 high Nouls: n={exp4.get('n_multi_high')} (threshold 0.6). Pairwise Noul Spearman is reported in `exp4_nouls.json` (`noul_pair_spearman`).

### Interpretation

Nouls are not mutually exclusive by construction: a text may both acknowledge banking stress and retain a higher-for-longer signal. Era means are descriptive; the SVB meeting is a targeted face-validity check for `acknowledges_banking_stress`.

### Limitations

Era bins are coarse and unbalanced. Noul probabilities are calibrated only insofar as SystemOne's Noul primitive is; we do not claim frequentist coverage. Supply-shock attribution (`blames_supply_shocks`) can co-occur with hawkish urgency when the Committee describes shocks yet still tightens.

---

## Experiment 5 — Calibration / paraphrase consistency

### Methods

Stratum A (40 extreme pairs) times both presentation orders. Baseline instructions (main run, cached): "{PARA_BASELINE}". Two meaning-preserving paraphrases (exact strings logged):

1. "{PARA_PHRASES[0]['instructions']}"
2. "{PARA_PHRASES[1]['instructions']}"

Metrics: inversion rate vs gold; mean |p_gold,para - p_gold,baseline|; order-flip rate per paraphrase; reliability diagram (10 equal-width bins of p_gold vs empirical non-inversion frequency) and ECE.

### Results

- Baseline: inversion={inv5b.get('rate')} (n={inv5b.get('n')}, STE={inv5b.get('ste')}); order-flip={((base5.get('order_flip_rate') or {}).get('rate'))}; ECE={((base5.get('calibration') or {}).get('ece'))}; mean p_gold={base5.get('mean_p_gold')}.

Paraphrases:

{chr(10).join(para_blocks) if para_blocks else '- (none)'}

Artifact: `results/experiments/exp5_calibration.json`.

### Interpretation

Low inversion under paraphrase indicates criterion-string robustness within the inflation-hawkishness family. ECE and reliability bins summarize whether reported p_gold tracks empirical accuracy; large mean |Delta p| with stable winners would indicate confidence instability without rank changes.

### Limitations

Stratum A is deliberately easy (rate extremes); calibration on hard / adjacent pairs may differ. Paraphrases were author-chosen, not sampled from a paraphrase model. Baseline and paraphrase calls are not contemporaneous (baseline from the main run cache).

---

## Experiment 6 — Evidence-span Choice

### Methods

{exp6.get('n_items')} items (cap 50, seed {SEED}): one Shah hawkish sentence as gold plus 3–5 distractors drawn preferentially from the same (year, doc_type) pool of neutrals/doves, else from the global dove/neutral pool. Choice options are span ids (`S1`…); instructions: "{SPAN_INSTRUCTIONS}". No free-form generation.

### Results

- Inversion rate: {inv6.get('rate')} (n={inv6.get('n')}, STE={inv6.get('ste')}, n_inverted={inv6.get('n_success')})
- Mean p(gold): {exp6.get('mean_p_gold')} (STE={exp6.get('mean_p_gold_ste')})
- Approx. live cost: ${exp6.get('cost_usd_live')}

Artifact: `results/experiments/exp6_span_choice.json`.

### Interpretation

Span Choice tests whether Jev can select a hawkish inflation span among local distractors, complementary to pairwise document Choice. Chance baseline depends on option count (3–5 distractors implies 4–6 options; chance p approximately 1/K).

### Limitations

Shah labels are sentence-level and domain-specific; "nearby" is operationalized as same year and document type, not true transcript adjacency (positional offsets are unavailable in `sentences.jsonl`). Distractor difficulty is uncontrolled beyond label class.

---

## Experiment 7 — Macro-relative vs text-absolute

### Methods

Stratum A times both orders. **Absolute arm:** text-only Choice with the main-run criterion (cached). **Macro arm:** state includes `Text A`, `Text B`, and `macro_A` / `macro_B` with FRED as-of each document date — core PCE (PCEPILFE 12-month YoY when available, else level), UNRATE, and DGS10 as the risk/rate proxy (VIXCLS absent from the local FRED dump). Instructions: "{MACRO_INSTRUCTIONS}". Gold remains the rate-extreme label.

### Results

- Macro-arm inversion vs gold: {inv7m.get('rate')} (n={inv7m.get('n')}, STE={inv7m.get('ste')})
- Absolute-arm inversion vs gold: {inv7a.get('rate')} (n={inv7a.get('n')}, STE={inv7a.get('ste')})
- Agreement rate (absolute vs macro winners): {agr7.get('rate')} (n={agr7.get('n')})
- Spearman(p_gold,abs, p_gold,macro): {_fmt_rho(exp7.get('spearman_p_gold_abs_vs_macro'))}
- Mean p_gold absolute / macro: {exp7.get('mean_p_gold_absolute')} / {exp7.get('mean_p_gold_macro')}

Artifact: `results/experiments/exp7_macro_relative.json`.

### Interpretation

Disagreement between arms isolates cases where macro context shifts the preferred text relative to a text-only reading. Agreement with rate-extreme gold under the macro arm is only a partial diagnostic: gold ignores the provided macro by construction.

### Limitations

Gold is not macro-conditional. Macro features are sparse (three series) and contemporaneous as-of dates may not match real-time information sets (publication lags). DGS10 substitutes for VIX. Extreme pairs may leave little room for macro to overturn an already lopsided text comparison.

---

## Cross-experiment notes

- **Cost / latency:** see `results/experiments/SUMMARY.json` (`total`, `by_experiment`).
- **Caching:** `runs/jev/exp_cache/`; append-only answer log `runs/jev/experiments_answers.jsonl`.
- **Non-interference:** `data/pairs/gold_pairs.jsonl` was not modified; no Haiku judge was used in these experiments.
"""
    (OUT_DIR / "FINDINGS.md").write_text(md)
    print(f"Wrote {OUT_DIR / 'FINDINGS.md'}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Subset: exp3 exp4 exp5 exp6 exp7 (exp3/4 always paired)")
    args = parser.parse_args()

    if not ensure_api_key():
        print("TYPESAFE_API_KEY missing", file=sys.stderr)
        sys.exit(2)

    EXP_CACHE.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    only = set(args.only) if args.only else {"exp3", "exp4", "exp5", "exp6", "exp7"}
    need_34 = bool(only & {"exp3", "exp4"})

    client = make_client()
    stmts = load_statements()
    corpus = load_corpus_texts()
    print(f"statements={len(stmts)} corpus_ids={len(corpus)}", flush=True)

    exp3 = exp4 = exp5 = exp6 = exp7 = {}

    if need_34:
        print("=== Exp3+4 packed Scores+Nouls ===", flush=True)
        packed = run_exp3_exp4(client, stmts, dry_run=args.dry_run)
        exp3 = analyze_exp3(packed)
        print("exp3 correlations:", json.dumps(exp3.get("correlations"), indent=2)[:800], flush=True)
        exp4 = analyze_exp4(packed)
        print("exp4 SVB:", exp4.get("svb_2023_03_22"), flush=True)

    if "exp5" in only:
        print("=== Exp5 paraphrase calibration ===", flush=True)
        exp5 = run_exp5(client, corpus, dry_run=args.dry_run)
        print("exp5 baseline inv:", (exp5.get("baseline") or {}).get("inversion"), flush=True)

    if "exp6" in only:
        print("=== Exp6 span Choice ===", flush=True)
        exp6 = run_exp6(client, dry_run=args.dry_run)
        print("exp6 inversion:", exp6.get("inversion"), flush=True)

    if "exp7" in only:
        print("=== Exp7 macro-relative ===", flush=True)
        exp7 = run_exp7(client, corpus, dry_run=args.dry_run)
        print("exp7 macro inv:", exp7.get("inversion_macro"), flush=True)

    def load_if(name, current):
        p = OUT_DIR / name
        if current:
            return current
        if p.exists():
            return json.loads(p.read_text())
        return {}

    exp3 = load_if("exp3_composite.json", exp3)
    exp4 = load_if("exp4_nouls.json", exp4)
    exp5 = load_if("exp5_calibration.json", exp5)
    exp6 = load_if("exp6_span_choice.json", exp6)
    exp7 = load_if("exp7_macro_relative.json", exp7)

    summary = write_summary(exp3, exp4, exp5, exp6, exp7)
    write_findings(exp3, exp4, exp5, exp6, exp7, summary)
    print("DONE", json.dumps(summary["total"], indent=2), flush=True)


if __name__ == "__main__":
    main()
