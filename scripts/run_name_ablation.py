#!/usr/bin/env python3
"""Gate 6 name ablation: Stratum A Choice with names/dates LEFT IN (raw_text).

Cache key includes names=1 so it never collides with stripped baseline cache.
Writes runs/jev/answers_names.jsonl and updates results for gate 6.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.load_typesafe_env import ensure as ensure_api_key  # noqa: E402
import score as S  # noqa: E402

ANSWERS_NAMES = S.RUN_DIR / "answers_names.jsonl"
JUDGMENTS_NAMES = ROOT / "results" / "pair_judgments_names.jsonl"
ABLATION_SUMMARY = ROOT / "results" / "name_ablation.json"


def cache_key_names(model: str, criterion: str, hash_a: str, hash_b: str, order: str) -> str:
    """Same as score.cache_key but appends |names=1 to prevent collision."""
    raw = f"{model}|{criterion}|{hash_a}|{hash_b}|{order}|names=1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_raw(corpus: dict[str, dict[str, Any]], doc_id: str) -> str:
    d = corpus.get(doc_id)
    if not d:
        raise KeyError(f"missing corpus id: {doc_id}")
    raw = d.get("raw_text") or d.get("text") or ""
    if not raw:
        raise ValueError(f"empty raw_text for {doc_id}")
    return raw


def process_names_choice(
    client,
    *,
    pair: dict[str, Any],
    order: str,
    corpus: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    text_a_raw_id = pair["a"]
    text_b_raw_id = pair["b"]
    raw_a = get_raw(corpus, text_a_raw_id)
    raw_b = get_raw(corpus, text_b_raw_id)

    if order == "ab":
        display_a, display_b = raw_a, raw_b
        id_a, id_b = text_a_raw_id, text_b_raw_id
    elif order == "ba":
        display_a, display_b = raw_b, raw_a
        id_a, id_b = text_b_raw_id, text_a_raw_id
    else:
        raise ValueError(order)

    ha, hb = S.text_hash(display_a), S.text_hash(display_b)
    key = cache_key_names(S.MODEL, S.CRITERION, ha, hb, order)

    cached = S.read_cache(key)
    if cached and cached.get("ok"):
        out = dict(cached)
        out["cache_hit"] = True
        out["names"] = 1
        out["pair_id"] = pair["pair_id"]
        out["order"] = order
        out["source"] = pair.get("source")
        out["gold"] = pair.get("gold")
        out["id_A"] = id_a
        out["id_B"] = id_b
        out["hash_A"] = ha
        out["hash_B"] = hb
        out["cache_key"] = key
        S.append_jsonl(ANSWERS_NAMES, {k: out[k] for k in (
            "ok", "kind", "pair_id", "order", "source", "gold", "id_A", "id_B",
            "hash_A", "hash_B", "winner", "p_A", "p_B", "confidence",
            "model", "input_tokens", "output_tokens", "latency_ms",
            "cache_hit", "cache_key", "criterion", "names",
        ) if k in out})
        S.bump_progress(cache_hit=True, input_tokens=0)
        return out

    try:
        result = S.call_choice(client, text_a=display_a, text_b=display_b)
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
            "probabilities": result["probabilities"],
            "model": result["model"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "latency_ms": result["latency_ms"],
            "cache_hit": False,
            "cache_key": key,
            "criterion": S.CRITERION,
            "names": 1,
        }
        S.write_cache(key, answer)
        S.append_jsonl(ANSWERS_NAMES, answer)
        S.append_jsonl(S.RESPONSES_PATH, {
            "pair_id": pair["pair_id"],
            "order": order,
            "kind": "choice_names",
            "names": 1,
            "model": result["model"],
            "answer": result["raw_answer"],
            "usage": {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            },
            "latency_ms": result["latency_ms"],
        })
        # Also append a marker line to main answers.jsonl for audit trail
        S.append_jsonl(S.ANSWERS_PATH, {**answer, "ablation": "names"})
        S.bump_progress(input_tokens=result["input_tokens"])
        return answer
    except SystemExit:
        raise
    except Exception as e:
        err = {
            "ok": False,
            "kind": "choice",
            "pair_id": pair["pair_id"],
            "order": order,
            "error": f"{type(e).__name__}: {e}",
            "hash_A": ha,
            "hash_B": hb,
            "cache_key": key,
            "names": 1,
        }
        S.append_jsonl(ANSWERS_NAMES, err)
        S.bump_progress(failure=True)
        return err


def load_done_keys() -> set[str]:
    done: set[str] = set()
    if ANSWERS_NAMES.exists():
        for line in ANSWERS_NAMES.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("ok") and d.get("cache_key"):
                done.add(d["cache_key"])
            elif d.get("ok") and d.get("pair_id") and d.get("order"):
                done.add(f"{d['pair_id']}:{d['order']}")
    return done


def aggregate_judgments(pairs: list[dict], answers: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for d in answers:
        if not d.get("ok") or d.get("kind") != "choice":
            continue
        k = f"{d['pair_id']}:{d['order']}"
        prev = by_key.get(k)
        if prev is None:
            by_key[k] = d
        elif prev.get("cache_hit") and not d.get("cache_hit"):
            by_key[k] = d

    judgments = []
    for p in pairs:
        pid = p["pair_id"]
        ab = by_key.get(f"{pid}:ab")
        ba = by_key.get(f"{pid}:ba")
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
        p_a_avg = sum(probs_a) / len(probs_a)
        p_b_avg = sum(probs_b) / len(probs_b)
        winner_avg = "a" if p_a_avg >= p_b_avg else "b"
        gold = p.get("gold")
        inverted = (winner_avg != gold) if gold in ("a", "b") else None
        p_gold = p_a_avg if gold == "a" else p_b_avg
        brier = (p_gold - 1.0) ** 2
        judgments.append({
            "pair_id": pid,
            "source": p.get("source"),
            "gold": gold,
            "p_A_avg": p_a_avg,
            "p_B_avg": p_b_avg,
            "p_gold": p_gold,
            "brier": brier,
            "winner_avg": winner_avg,
            "inverted": inverted,
            "order_flip": len(set(winners)) > 1 if len(winners) == 2 else None,
            "n_orders": len(probs_a),
            "winners_per_order": winners,
            "a": p["a"],
            "b": p["b"],
            "names": 1,
        })
    return judgments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()

    S.RUN_DIR.mkdir(parents=True, exist_ok=True)
    S.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_pairs = S.load_pairs()
    pairs = [p for p in all_pairs if p.get("source") == "extreme"]
    corpus = S.load_corpus()
    print(f"name ablation: {len(pairs)} stratum-A pairs × 2 orders = {len(pairs)*2} calls")

    if args.aggregate_only:
        answers = [json.loads(l) for l in ANSWERS_NAMES.open()] if ANSWERS_NAMES.exists() else []
        judgments = aggregate_judgments(pairs, answers)
        with JUDGMENTS_NAMES.open("w") as f:
            for j in judgments:
                f.write(json.dumps(j) + "\n")
        n_inv = sum(1 for j in judgments if j["inverted"])
        rate = n_inv / len(judgments) if judgments else None
        print(json.dumps({"n": len(judgments), "n_inverted": n_inv, "inversion_rate": rate}, indent=2))
        return

    if not args.live:
        print("Pass --live to run name ablation")
        return

    if not ensure_api_key():
        print("TYPESAFE_API_KEY missing", file=sys.stderr)
        sys.exit(1)

    # Reset progress counters for this run
    S._progress.update({"n": 0, "cache_hits": 0, "failures": 0, "input_tokens": 0, "usd": 0.0})

    done = load_done_keys()
    jobs = []
    for p in pairs:
        for order in ("ab", "ba"):
            # provisional key check via done pair:order markers and cache
            raw_a = get_raw(corpus, p["a"] if order == "ab" else p["b"])
            raw_b = get_raw(corpus, p["b"] if order == "ab" else p["a"])
            ha, hb = S.text_hash(raw_a), S.text_hash(raw_b)
            key = cache_key_names(S.MODEL, S.CRITERION, ha, hb, order)
            if key in done or f"{p['pair_id']}:{order}" in done:
                # still process to refresh answers_names from cache
                pass
            jobs.append((p, order))

    client = S.make_client()
    t0 = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [
            ex.submit(process_names_choice, client, pair=p, order=o, corpus=corpus)
            for p, o in jobs
        ]
        for fut in as_completed(futs):
            results.append(fut.result())
    wall_ms = int((time.perf_counter() - t0) * 1000)

    ok = [r for r in results if r.get("ok")]
    fails = [r for r in results if not r.get("ok")]
    live = [r for r in ok if not r.get("cache_hit")]
    input_tok = sum(int(r.get("input_tokens") or 0) for r in live)
    output_tok = sum(int(r.get("output_tokens") or 0) for r in live)
    usd = input_tok * S.PRICE_PER_MTOK_INPUT / 1e6
    latencies = [int(r.get("latency_ms") or 0) for r in live]

    # Dedup answers_names to latest successful per pair:order
    answers = [json.loads(l) for l in ANSWERS_NAMES.open()] if ANSWERS_NAMES.exists() else []
    judgments = aggregate_judgments(pairs, answers)
    with JUDGMENTS_NAMES.open("w") as f:
        for j in judgments:
            f.write(json.dumps(j) + "\n")

    n_inv = sum(1 for j in judgments if j["inverted"])
    rate = (n_inv / len(judgments)) if judgments else None
    baseline = 0.0
    delta = abs(rate - baseline) if rate is not None else None
    n_flip = sum(1 for j in judgments if j.get("order_flip"))
    passed = (delta is not None and delta <= 0.05)

    summary = {
        "run_id": S.RUN_ID,
        "ablation": "names",
        "stratum": "extreme",
        "n_pairs": len(judgments),
        "n_calls_attempted": len(results),
        "n_ok": len(ok),
        "n_live": len(live),
        "n_cache_hits": len(ok) - len(live),
        "n_failures": len(fails),
        "n_inverted": n_inv,
        "inversion_rate": rate,
        "baseline_inversion": baseline,
        "inversion_delta": delta,
        "pass_line": "Δ inversion ≤ 0.05",
        "pass": passed,
        "order_flip_n": n_flip,
        "order_flip_rate": (n_flip / len(judgments)) if judgments else None,
        "inverted_pairs": [j["pair_id"] for j in judgments if j["inverted"]],
        "usage": {
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "latency_ms_total": sum(latencies),
            "latency_ms_mean": (sum(latencies) / len(latencies)) if latencies else None,
            "wall_ms": wall_ms,
        },
        "cost_usd": {
            "input": round(usd, 8),
            "output": 0.0,
            "total": round(usd, 8),
        },
        "model": sorted({r.get("model") for r in live if r.get("model")}) or [S.MODEL],
        "cache_key_suffix": "names=1",
        "note": "raw_text / unstripped; strip_meta NOT applied",
    }
    ABLATION_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print("=== NAME ABLATION ===")
    print(json.dumps(summary, indent=2))
    if fails:
        print(f"FAILURES: {len(fails)}", file=sys.stderr)
        for f in fails[:5]:
            print(f, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
