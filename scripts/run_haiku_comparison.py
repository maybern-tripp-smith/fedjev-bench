#!/usr/bin/env python3
"""Full Haiku 4.5 Choice comparison vs Jev on all 262 gold pairs × both orders.

Same protocol as score.py Choice: stripped meta text, criterion
"more hawkish about inflation", orders ab/ba. Asks Claude for JSON
{"winner":"A"|"B","p_A":float,"p_B":float} with p_A+p_B=1.

Cache under runs/haiku/cache/. Answers → runs/haiku/answers.jsonl.
Pricing (Haiku 4.5): $1 / MTok input, $5 / MTok output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.strip_meta import strip_meta  # noqa: E402

MODEL = "claude-haiku-4-5-20251001"
CRITERION = "more hawkish about inflation"
RUN_ID = "fedjev-2026-09-20"
PRICE_IN = 1.0   # USD / MTok
PRICE_OUT = 5.0  # USD / MTok

RUN_DIR = ROOT / "runs" / "haiku"
CACHE_DIR = RUN_DIR / "cache"
ANSWERS_PATH = RUN_DIR / "answers.jsonl"
SUMMARY_PATH = ROOT / "results" / "haiku_comparison.json"
JUDGMENTS_PATH = ROOT / "results" / "haiku_pair_judgments.jsonl"
COST_PATH = ROOT / "results" / "haiku_cost.json"
TIMING_PATH = ROOT / "results" / "haiku_timing.json"

_write_lock = threading.Lock()
_progress = {"n": 0, "cache_hits": 0, "failures": 0, "in_tok": 0, "out_tok": 0, "usd": 0.0}
_progress_lock = threading.Lock()


def ensure_anthropic_key() -> bool:
    """Public tree: env-only. Set ANTHROPIC_API_KEY in the environment."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cache_key(model: str, criterion: str, ha: str, hb: str, order: str) -> str:
    raw = f"{model}|{criterion}|{ha}|{hb}|{order}|haiku_cmp"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_corpus() -> dict[str, dict[str, Any]]:
    corpus: dict[str, dict[str, Any]] = {}
    for line in (ROOT / "data/clean/statements.jsonl").open():
        d = json.loads(line)
        corpus[d["doc_id"]] = d
    for line in (ROOT / "data/clean/sentences.jsonl").open():
        d = json.loads(line)
        corpus[d["sent_id"]] = d
    return corpus


def load_pairs() -> list[dict[str, Any]]:
    return [json.loads(l) for l in (ROOT / "data/pairs/gold_pairs.jsonl").open()]


def get_stripped(corpus: dict[str, dict[str, Any]], doc_id: str) -> str:
    d = corpus[doc_id]
    raw = d.get("raw_text") or d.get("text") or ""
    stripped = strip_meta(raw)
    if not stripped:
        stripped = strip_meta(d.get("text") or "")
    return stripped


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()


def read_cache(key: str) -> dict[str, Any] | None:
    p = CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def write_cache(key: str, obj: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{key}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    tmp.replace(p)


def bump(*, cache_hit=False, failure=False, in_tok=0, out_tok=0):
    with _progress_lock:
        _progress["n"] += 1
        if cache_hit:
            _progress["cache_hits"] += 1
        if failure:
            _progress["failures"] += 1
        _progress["in_tok"] += in_tok
        _progress["out_tok"] += out_tok
        _progress["usd"] = (
            _progress["in_tok"] * PRICE_IN / 1e6
            + _progress["out_tok"] * PRICE_OUT / 1e6
        )
        n = _progress["n"]
        if n % 25 == 0 or failure:
            print(
                f"[haiku] calls={n} hits={_progress['cache_hits']} "
                f"fail={_progress['failures']} "
                f"in={_progress['in_tok']} out={_progress['out_tok']} "
                f"usd≈{_progress['usd']:.4f}",
                flush=True,
            )


SYSTEM = (
    "You are a careful rater of central-bank communication. "
    "Compare two texts on a fixed criterion. "
    "Respond with ONLY a single JSON object, no markdown fences, no commentary."
)


def build_user(text_a: str, text_b: str) -> str:
    return (
        f"Criterion: which text is {CRITERION}?\n\n"
        f"Text A:\n{text_a}\n\n"
        f"Text B:\n{text_b}\n\n"
        "Return JSON with keys:\n"
        '  "winner": "A" or "B",\n'
        '  "p_A": probability Text A is more hawkish about inflation (0-1),\n'
        '  "p_B": probability Text B is more hawkish about inflation (0-1),\n'
        '  "confidence": your confidence in the winner (0-1).\n'
        "Require p_A + p_B = 1. Prefer calibrated probabilities, not 0/1 unless certain."
    )


def parse_answer(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re_strip_fence(text)
    # find first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON in response: {text[:200]!r}")
    obj = json.loads(text[start : end + 1])
    winner = str(obj.get("winner", "")).strip().upper()
    if winner not in ("A", "B"):
        raise ValueError(f"bad winner: {winner!r}")
    p_a = float(obj.get("p_A", 0.5 if winner == "A" else 0.5))
    p_b = float(obj.get("p_B", 1.0 - p_a))
    s = p_a + p_b
    if s <= 0:
        p_a, p_b = (1.0, 0.0) if winner == "A" else (0.0, 1.0)
    else:
        p_a, p_b = p_a / s, p_b / s
    # consistency: winner should match argmax
    if (p_a >= p_b and winner != "A") or (p_b > p_a and winner != "B"):
        winner = "A" if p_a >= p_b else "B"
    conf = float(obj.get("confidence", max(p_a, p_b)))
    return {"winner": winner, "p_A": p_a, "p_B": p_b, "confidence": conf}


def re_strip_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def call_haiku(client, text_a: str, text_b: str) -> dict[str, Any]:
    import random
    try:
        from anthropic import APIStatusError, RateLimitError
    except Exception:
        APIStatusError = Exception  # type: ignore
        RateLimitError = Exception  # type: ignore

    t0 = time.perf_counter()
    last_err = None
    msg = None
    for attempt in range(8):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=256,
                system=SYSTEM,
                messages=[{"role": "user", "content": build_user(text_a, text_b)}],
            )
            break
        except Exception as e:
            last_err = e
            name = type(e).__name__
            status = getattr(e, "status_code", None)
            retryable = (
                name in ("RateLimitError", "APIStatusError", "APIConnectionError", "APITimeoutError")
                or status in (429, 500, 502, 503, 529)
                or "rate" in str(e).lower()
                or "429" in str(e)
            )
            if not retryable or attempt == 7:
                raise
            sleep_s = min(60.0, (2 ** attempt) + random.random())
            print(f"[haiku] backoff {sleep_s:.1f}s after {name} status={status}", flush=True)
            time.sleep(sleep_s)
    if msg is None:
        raise last_err or RuntimeError("haiku call failed")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    parts = []
    for block in msg.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    raw_text = "".join(parts)
    parsed = parse_answer(raw_text)
    usage = msg.usage
    return {
        "model": msg.model,
        "winner": parsed["winner"],
        "p_A": parsed["p_A"],
        "p_B": parsed["p_B"],
        "confidence": parsed["confidence"],
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
        "raw_text": raw_text[:2000],
        "probs_calibrated": True,  # model asked for calibrated p_A/p_B
    }


def process_job(client, *, pair, order, corpus) -> dict[str, Any]:
    id_a_raw, id_b_raw = pair["a"], pair["b"]
    strip_a = get_stripped(corpus, id_a_raw)
    strip_b = get_stripped(corpus, id_b_raw)
    if order == "ab":
        display_a, display_b = strip_a, strip_b
        id_a, id_b = id_a_raw, id_b_raw
    else:
        display_a, display_b = strip_b, strip_a
        id_a, id_b = id_b_raw, id_a_raw

    ha, hb = text_hash(display_a), text_hash(display_b)
    key = cache_key(MODEL, CRITERION, ha, hb, order)

    cached = read_cache(key)
    if cached and cached.get("ok"):
        out = dict(cached)
        out["cache_hit"] = True
        out["pair_id"] = pair["pair_id"]
        out["order"] = order
        append_jsonl(ANSWERS_PATH, {
            **{k: out.get(k) for k in (
                "ok", "kind", "pair_id", "order", "source", "gold",
                "id_A", "id_B", "hash_A", "hash_B", "winner", "p_A", "p_B",
                "confidence", "model", "input_tokens", "output_tokens",
                "latency_ms", "cache_hit", "cache_key", "criterion",
            )},
            "cache_hit": True,
            "pair_id": pair["pair_id"],
            "order": order,
            "source": pair.get("source"),
            "gold": pair.get("gold"),
            "id_A": id_a,
            "id_B": id_b,
            "hash_A": ha,
            "hash_B": hb,
            "cache_key": key,
            "criterion": CRITERION,
            "kind": "choice",
            "ok": True,
        })
        bump(cache_hit=True)
        return out

    try:
        result = call_haiku(client, display_a, display_b)
        answer = {
            "ok": True,
            "kind": "choice",
            "pair_id": pair["pair_id"],
            "order": order,
            "source": pair.get("source"),
            "gold": pair.get("gold"),
            "id_A": id_a,
            "id_B": id_b,
            "hash_A": ha,
            "hash_B": hb,
            "winner": result["winner"],
            "p_A": result["p_A"],
            "p_B": result["p_B"],
            "confidence": result["confidence"],
            "model": result["model"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "latency_ms": result["latency_ms"],
            "cache_hit": False,
            "cache_key": key,
            "criterion": CRITERION,
            "raw_text": result.get("raw_text"),
        }
        write_cache(key, {k: v for k, v in answer.items() if k != "raw_text"})
        append_jsonl(ANSWERS_PATH, answer)
        bump(in_tok=result["input_tokens"], out_tok=result["output_tokens"])
        return answer
    except Exception as e:
        err = {
            "ok": False,
            "kind": "choice",
            "pair_id": pair["pair_id"],
            "order": order,
            "error": f"{type(e).__name__}: {e}",
            "cache_key": key,
            "hash_A": ha,
            "hash_B": hb,
        }
        append_jsonl(ANSWERS_PATH, err)
        bump(failure=True)
        return err


def aggregate(pairs: list[dict], answers: list[dict]) -> tuple[list[dict], dict]:
    by: dict[str, dict] = {}
    for d in answers:
        if d.get("kind") != "choice" or not d.get("ok"):
            continue
        k = f"{d['pair_id']}:{d['order']}"
        prev = by.get(k)
        if prev is None or (prev.get("cache_hit") and not d.get("cache_hit")):
            by[k] = d

    judgments = []
    for p in pairs:
        pid = p["pair_id"]
        ab, ba = by.get(f"{pid}:ab"), by.get(f"{pid}:ba")
        if not ab and not ba:
            continue
        probs_a, probs_b, winners = [], [], []
        if ab:
            probs_a.append(float(ab["p_A"]))
            probs_b.append(float(ab["p_B"]))
            winners.append("a" if ab["winner"] == "A" else "b")
        if ba:
            probs_a.append(float(ba["p_B"]))
            probs_b.append(float(ba["p_A"]))
            winners.append("b" if ba["winner"] == "A" else "a")
        p_a = sum(probs_a) / len(probs_a)
        p_b = sum(probs_b) / len(probs_b)
        winner = "a" if p_a >= p_b else "b"
        gold = p.get("gold")
        inverted = (winner != gold) if gold in ("a", "b") else None
        p_gold = p_a if gold == "a" else p_b
        judgments.append({
            "pair_id": pid,
            "source": p.get("source"),
            "gold": gold,
            "p_A_avg": p_a,
            "p_B_avg": p_b,
            "p_gold": p_gold,
            "brier": (p_gold - 1.0) ** 2,
            "winner_avg": winner,
            "inverted": inverted,
            "order_flip": len(set(winners)) > 1 if len(winners) == 2 else None,
            "n_orders": len(probs_a),
            "winners_per_order": winners,
            "model": MODEL,
        })

    from collections import defaultdict
    by_src = defaultdict(list)
    for j in judgments:
        by_src[j["source"]].append(j)

    inv_tables = {}
    for src, subset in by_src.items():
        n = len(subset)
        n_inv = sum(1 for j in subset if j["inverted"])
        flips = [j for j in subset if j.get("order_flip")]
        inv_tables[src] = {
            "n": n,
            "n_inverted": n_inv,
            "inversion_rate": n_inv / n if n else None,
            "mean_p_gold": sum(j["p_gold"] for j in subset) / n if n else None,
            "mean_brier": sum(j["brier"] for j in subset) / n if n else None,
            "order_flip_rate": len(flips) / n if n else None,
        }
    return judgments, inv_tables


def load_jev_baseline() -> dict:
    gates = json.loads((ROOT / "results/gates.json").read_text())
    # rebuild inv from pair_judgments
    from collections import defaultdict
    by = defaultdict(list)
    for line in (ROOT / "results/pair_judgments.jsonl").open():
        j = json.loads(line)
        by[j["source"]].append(j)
    out = {}
    for src, subset in by.items():
        n = len(subset)
        n_inv = sum(1 for j in subset if j["inverted"])
        out[src] = {
            "n": n,
            "n_inverted": n_inv,
            "inversion_rate": n_inv / n if n else None,
            "mean_p_gold": sum(j["p_gold"] for j in subset) / n if n else None,
            "mean_brier": sum(j["brier"] for j in subset) / n if n else None,
            "order_flip_rate": sum(1 for j in subset if j.get("order_flip")) / n if n else None,
        }
    cost = json.loads((ROOT / "results/cost.json").read_text())
    timing = json.loads((ROOT / "results/timing.json").read_text())
    return {"inversion": out, "cost": cost, "timing": timing, "gates": gates}


def write_summaries(pairs, answers, wall_ms: int | None = None) -> dict:
    judgments, inv = aggregate(pairs, answers)
    with JUDGMENTS_PATH.open("w") as f:
        for j in judgments:
            f.write(json.dumps(j) + "\n")

    # live token totals from cache
    in_tok = out_tok = 0
    latencies = []
    n_live = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if not d.get("ok"):
            continue
        in_tok += int(d.get("input_tokens") or 0)
        out_tok += int(d.get("output_tokens") or 0)
        latencies.append(int(d.get("latency_ms") or 0))
        n_live += 1

    usd_in = in_tok * PRICE_IN / 1e6
    usd_out = out_tok * PRICE_OUT / 1e6
    cost = {
        "run_id": RUN_ID,
        "model": MODEL,
        "price_per_mtok_input_usd": PRICE_IN,
        "price_per_mtok_output_usd": PRICE_OUT,
        "n_calls": n_live,
        "n_choice_answers": len({f"{a['pair_id']}:{a['order']}" for a in answers if a.get("ok")}),
        "usage": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency_ms_total": sum(latencies),
            "latency_ms_mean": (sum(latencies) / len(latencies)) if latencies else None,
        },
        "cost_usd": {
            "input": round(usd_in, 8),
            "output": round(usd_out, 8),
            "total": round(usd_in + usd_out, 8),
        },
    }
    COST_PATH.write_text(json.dumps(cost, indent=2) + "\n")

    def pct(xs, q):
        if not xs:
            return None
        s = sorted(xs)
        i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
        return s[i]

    timing = {
        "run_id": RUN_ID,
        "model": MODEL,
        "n_calls": n_live,
        "wall_ms": wall_ms,
        "overall": {
            "n": len(latencies),
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "p50": pct(latencies, 0.50),
            "p95": pct(latencies, 0.95),
            "max": max(latencies) if latencies else None,
            "total_ms": sum(latencies),
        },
    }
    TIMING_PATH.write_text(json.dumps(timing, indent=2) + "\n")

    jev = load_jev_baseline()

    # per-stratum latency from answers/cache joined to pair source
    pair_src = {p["pair_id"]: p.get("source") for p in pairs}
    from collections import defaultdict
    lat_by_src: dict[str, list[int]] = defaultdict(list)
    for pth in CACHE_DIR.glob("*.json"):
        try:
            d = json.loads(pth.read_text())
        except Exception:
            continue
        if not d.get("ok"):
            continue
        src = pair_src.get(d.get("pair_id")) or d.get("source")
        if src and d.get("latency_ms") is not None:
            lat_by_src[src].append(int(d["latency_ms"]))

    by_stratum_cmp = {}
    for src in ("extreme", "shah", "adjacent"):
        h = inv.get(src) or {}
        j = jev["inversion"].get(src) or {}
        xs = lat_by_src.get(src) or []
        j_lat = (jev["timing"].get("by_stratum") or {}).get(src) or {}
        by_stratum_cmp[src] = {
            "haiku": {
                "n": h.get("n"),
                "inversion_rate": h.get("inversion_rate"),
                "mean_brier": h.get("mean_brier"),
                "mean_p_gold": h.get("mean_p_gold"),
                "order_flip_rate": h.get("order_flip_rate"),
                "latency_ms_mean": (sum(xs) / len(xs)) if xs else None,
                "latency_ms_p50": pct(xs, 0.50) if xs else None,
                "latency_ms_p95": pct(xs, 0.95) if xs else None,
            },
            "jev": {
                "n": j.get("n"),
                "inversion_rate": j.get("inversion_rate"),
                "mean_brier": j.get("mean_brier"),
                "mean_p_gold": j.get("mean_p_gold"),
                "order_flip_rate": j.get("order_flip_rate"),
                "latency_ms_mean": j_lat.get("mean"),
                "latency_ms_p50": j_lat.get("p50"),
                "latency_ms_p95": j_lat.get("p95"),
            },
        }

    comparison = {
        "run_id": RUN_ID,
        "status": "complete" if len(judgments) == len(pairs) else "partial",
        "haiku_model": MODEL,
        "jev_model": "jev-1.13.0",
        "criterion": CRITERION,
        "n_pairs_expected": len(pairs),
        "n_pairs_scored": len(judgments),
        "n_calls_expected": len(pairs) * 2,
        "haiku_inversion": inv,
        "jev_inversion": jev["inversion"],
        "haiku_cost": cost,
        "jev_cost_choice_approx": {
            "note": "Jev main run includes Score; Choice-only token share from by_stratum",
            "choice_usd": round(
                sum(
                    (jev["cost"].get("by_stratum") or {}).get(s, {}).get("usd") or 0
                    for s in ("extreme", "shah", "adjacent")
                ),
                8,
            ),
            "total_run_usd": jev["cost"]["cost_usd"]["total"],
            "n_choice": jev["cost"].get("n_choice_answers"),
        },
        "haiku_timing": timing,
        "jev_timing_choice": jev["timing"].get("by_kind", {}).get("choice"),
        "delta_inversion": {
            src: {
                "haiku": (inv.get(src) or {}).get("inversion_rate"),
                "jev": (jev["inversion"].get(src) or {}).get("inversion_rate"),
                "delta_haiku_minus_jev": (
                    None
                    if (inv.get(src) or {}).get("inversion_rate") is None
                    or (jev["inversion"].get(src) or {}).get("inversion_rate") is None
                    else (inv[src]["inversion_rate"] - jev["inversion"][src]["inversion_rate"])
                ),
            }
            for src in sorted(set(list(inv) + list(jev["inversion"])))
        },
        "by_stratum": by_stratum_cmp,
        "totals": {
            "haiku": {
                "usd": cost["cost_usd"]["total"],
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "n_calls": n_live,
                "wall_ms": wall_ms,
                "latency_ms_mean": timing["overall"]["mean"],
                "latency_ms_p50": timing["overall"]["p50"],
                "latency_ms_p95": timing["overall"]["p95"],
            },
            "jev_choice": {
                "usd": round(
                    sum(
                        (jev["cost"].get("by_stratum") or {}).get(s, {}).get("usd") or 0
                        for s in ("extreme", "shah", "adjacent")
                    ),
                    8,
                ),
                "usd_full_run": jev["cost"]["cost_usd"]["total"],
                "n_calls": jev["cost"].get("n_choice_answers"),
                "latency_ms_mean": (jev["timing"].get("by_kind") or {}).get("choice", {}).get("mean"),
                "latency_ms_p50": (jev["timing"].get("by_kind") or {}).get("choice", {}).get("p50"),
                "latency_ms_p95": (jev["timing"].get("by_kind") or {}).get("choice", {}).get("p95"),
            },
        },
        "ratios": {
            "haiku_usd_over_jev_choice_usd": None,
            "haiku_latency_p50_over_jev_choice_p50": None,
            "haiku_latency_mean_over_jev_choice_mean": None,
        },
        "notes": {
            "probs": "Asked Haiku for calibrated p_A/p_B summing to 1; Brier uses those probs (not one-hot) when returned.",
            "gates": "Comparison arm only; primary gate pass/fail remains Jev.",
        },
    }
    # fill ratios
    h_usd = comparison["totals"]["haiku"]["usd"]
    j_usd = comparison["totals"]["jev_choice"]["usd"]
    h_p50 = comparison["totals"]["haiku"]["latency_ms_p50"]
    j_p50 = comparison["totals"]["jev_choice"]["latency_ms_p50"]
    h_mean = comparison["totals"]["haiku"]["latency_ms_mean"]
    j_mean = comparison["totals"]["jev_choice"]["latency_ms_mean"]
    if j_usd and h_usd is not None:
        comparison["ratios"]["haiku_usd_over_jev_choice_usd"] = round(h_usd / j_usd, 4) if j_usd else None
    if j_p50 and h_p50 is not None:
        comparison["ratios"]["haiku_latency_p50_over_jev_choice_p50"] = round(h_p50 / j_p50, 4) if j_p50 else None
    if j_mean and h_mean is not None:
        comparison["ratios"]["haiku_latency_mean_over_jev_choice_mean"] = round(h_mean / j_mean, 4) if j_mean else None
    SUMMARY_PATH.write_text(json.dumps(comparison, indent=2) + "\n")
    return comparison


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="3 pairs × 2 orders")
    ap.add_argument("--limit-pairs", type=int, default=0)
    args = ap.parse_args()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pairs = load_pairs()
    corpus = load_corpus()
    print(f"haiku comparison: {len(pairs)} pairs × 2 = {len(pairs)*2} calls; model={MODEL}")

    if args.aggregate_only:
        answers = [json.loads(l) for l in ANSWERS_PATH.open()] if ANSWERS_PATH.exists() else []
        comp = write_summaries(pairs, answers)
        print(json.dumps({k: comp[k] for k in ("status", "n_pairs_scored", "haiku_inversion", "delta_inversion", "haiku_cost")}, indent=2))
        return

    if not args.live and not args.smoke:
        print("Pass --live or --smoke")
        return

    if not ensure_anthropic_key():
        print("ANTHROPIC_API_KEY missing — waiting for parent to provision", file=sys.stderr)
        # write stub summary
        stub = {
            "run_id": RUN_ID,
            "status": "pending_api_key",
            "haiku_model": MODEL,
            "jev_model": "jev-1.13.0",
            "n_pairs_expected": len(pairs),
            "n_calls_expected": len(pairs) * 2,
            "note": "ANTHROPIC_API_KEY not available yet; Comparison section stubbed",
        }
        SUMMARY_PATH.write_text(json.dumps(stub, indent=2) + "\n")
        sys.exit(2)

    from anthropic import Anthropic
    client = Anthropic()

    if args.smoke:
        pairs = pairs[:3]
    elif args.limit_pairs:
        pairs = pairs[: args.limit_pairs]

    # skip already-ok pair:order
    done = set()
    if ANSWERS_PATH.exists():
        for line in ANSWERS_PATH.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("ok"):
                done.add(f"{d.get('pair_id')}:{d.get('order')}")

    jobs = []
    for p in pairs:
        for order in ("ab", "ba"):
            if f"{p['pair_id']}:{order}" in done:
                continue
            jobs.append((p, order))

    print(f"jobs={len(jobs)} already_ok_markers={len(done)} concurrency={args.concurrency}")
    t0 = time.perf_counter()
    results = []
    if jobs:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = [
                ex.submit(process_job, client, pair=p, order=o, corpus=corpus)
                for p, o in jobs
            ]
            for fut in as_completed(futs):
                results.append(fut.result())
    wall_ms = int((time.perf_counter() - t0) * 1000)

    answers = [json.loads(l) for l in ANSWERS_PATH.open()] if ANSWERS_PATH.exists() else []
    # Use full pair list for aggregate when not smoke
    all_pairs = load_pairs() if not args.smoke else pairs
    comp = write_summaries(all_pairs if not args.smoke else pairs, answers, wall_ms=wall_ms)
    ok = sum(1 for r in results if r.get("ok"))
    print(f"done ok={ok}/{len(results)} wall_ms={wall_ms}")
    print(json.dumps({
        "status": comp["status"],
        "n_pairs_scored": comp["n_pairs_scored"],
        "haiku_inversion": comp.get("haiku_inversion"),
        "delta_inversion": comp.get("delta_inversion"),
        "cost": comp.get("haiku_cost", {}).get("cost_usd"),
    }, indent=2))
    if ok < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
