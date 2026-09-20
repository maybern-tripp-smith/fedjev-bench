#!/usr/bin/env python3
"""Live TypeSafe/Jev scoring for fedjev-bench (run_id fedjev-2026-09-20).

Posts Choice (pairwise, both orders) and Score (per-statement) to SystemOne.
Caches answers under runs/jev/cache/. Writes answers as we go for resumability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scripts.load_typesafe_env import ensure as ensure_api_key  # noqa: E402
from scripts.strip_meta import strip_meta  # noqa: E402

API = "https://api.typesafe.ai/v1/systemone"
CRITERION = "more hawkish about inflation"
MODEL = "jev-latest"
PRICE_PER_MTOK_INPUT = 0.042
OUTPUT_FREE = True
RUN_ID = "fedjev-2026-09-20"

CHOICE_INSTRUCTIONS = f"Which of Text A or Text B is {CRITERION}"
SCORE_LEVELS = [
    "much more dovish",
    "somewhat dovish",
    "neutral",
    "somewhat hawkish",
    "much more hawkish",
]
SCORE_INSTRUCTIONS = (
    f"Rate how {CRITERION} this statement is, "
    "from much more dovish to much more hawkish"
)

RUN_DIR = ROOT / "runs" / "jev"
CACHE_DIR = RUN_DIR / "cache"
ANSWERS_PATH = RUN_DIR / "answers.jsonl"
RESPONSES_PATH = RUN_DIR / "responses.jsonl"
REQUESTS_PATH = RUN_DIR / "requests.jsonl"
COST_PATH = ROOT / "results" / "cost.json"
JUDGMENTS_PATH = ROOT / "results" / "pair_judgments.jsonl"

_write_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress = {"n": 0, "cache_hits": 0, "failures": 0, "input_tokens": 0, "usd": 0.0}


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cache_key(model: str, criterion: str, hash_a: str, hash_b: str, order: str) -> str:
    raw = f"{model}|{criterion}|{hash_a}|{hash_b}|{order}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def score_cache_key(model: str, criterion: str, hash_t: str) -> str:
    raw = f"{model}|score|{criterion}|{hash_t}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_corpus() -> dict[str, dict[str, Any]]:
    """Index statements + sentences by id. Prefer pre-stripped `text`; keep raw_text."""
    corpus: dict[str, dict[str, Any]] = {}
    for line in (ROOT / "data" / "clean" / "statements.jsonl").open():
        d = json.loads(line)
        corpus[d["doc_id"]] = d
    for line in (ROOT / "data" / "clean" / "sentences.jsonl").open():
        d = json.loads(line)
        corpus[d["sent_id"]] = d
    return corpus


def load_pairs() -> list[dict[str, Any]]:
    return [json.loads(l) for l in (ROOT / "data" / "pairs" / "gold_pairs.jsonl").open()]


def get_stripped(corpus: dict[str, dict[str, Any]], doc_id: str) -> tuple[str, str]:
    """Return (stripped_text, raw_text). Always run strip_meta for API calls."""
    d = corpus.get(doc_id)
    if not d:
        raise KeyError(f"missing corpus id: {doc_id}")
    raw = d.get("raw_text") or d.get("text") or ""
    # Prefer applying strip_meta to raw for consistency; fall back to text
    stripped = strip_meta(raw)
    if not stripped:
        stripped = strip_meta(d.get("text") or "")
    return stripped, raw


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


def bump_progress(*, cache_hit: bool = False, failure: bool = False,
                  input_tokens: int = 0) -> None:
    with _progress_lock:
        _progress["n"] += 1
        if cache_hit:
            _progress["cache_hits"] += 1
        if failure:
            _progress["failures"] += 1
        _progress["input_tokens"] += input_tokens
        _progress["usd"] = _progress["input_tokens"] * PRICE_PER_MTOK_INPUT / 1e6
        n = _progress["n"]
        if n % 25 == 0 or failure:
            print(
                f"[progress] calls={n} cache_hits={_progress['cache_hits']} "
                f"failures={_progress['failures']} "
                f"input_tok={_progress['input_tokens']} "
                f"usd≈{_progress['usd']:.5f}",
                flush=True,
            )
        if _progress["usd"] > 1.0:
            print("STOP: spend >> $1 — aborting further live calls", flush=True)
            raise SystemExit(99)


def make_client():
    from typesafe_sdk import TypeSafeClient, RetryPolicy

    return TypeSafeClient(
        retry=RetryPolicy(
            max_retries=5,
            backoff_initial=0.5,
            backoff_max=30.0,
            http_statuses={408, 429, 500, 502, 503, 504, 529},
            timeout=120.0,
        ),
        timeout=120.0,
    )


def call_choice(
    client,
    *,
    text_a: str,
    text_b: str,
    model: str = MODEL,
) -> dict[str, Any]:
    from typesafe_sdk import Choice

    t0 = time.perf_counter()
    response = client.system_one(
        model=model,
        state={"Text A": text_a, "Text B": text_b},
        questions={
            "winner": Choice(
                instructions=CHOICE_INSTRUCTIONS,
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
        "raw_answer": {
            "type": "choice",
            "choice": ans.choice,
            "confidence": float(ans.confidence),
            "probabilities": {k: float(v) for k, v in ans.probabilities.items()},
        },
    }


def call_score(
    client,
    *,
    text: str,
    model: str = MODEL,
) -> dict[str, Any]:
    from typesafe_sdk import Score

    t0 = time.perf_counter()
    response = client.system_one(
        model=model,
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
    probs = {str(k): float(v) for k, v in ans.probabilities.items()}
    legend = {str(k): v for k, v in ans.legend.items()}
    return {
        "model": response.model,
        "score": float(ans.score),
        "confidence": float(ans.confidence),
        "probabilities": probs,
        "legend": legend,
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
        "raw_answer": {
            "type": "score",
            "score": float(ans.score),
            "confidence": float(ans.confidence),
            "probabilities": probs,
            "legend": legend,
        },
    }


def process_choice_job(
    client,
    *,
    pair: dict[str, Any],
    order: str,
    corpus: dict[str, dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    text_a_raw_id = pair["a"]
    text_b_raw_id = pair["b"]
    strip_a, raw_a = get_stripped(corpus, text_a_raw_id)
    strip_b, raw_b = get_stripped(corpus, text_b_raw_id)

    if order == "ab":
        display_a, display_b = strip_a, strip_b
        id_a, id_b = text_a_raw_id, text_b_raw_id
    elif order == "ba":
        display_a, display_b = strip_b, strip_a
        id_a, id_b = text_b_raw_id, text_a_raw_id
    else:
        raise ValueError(order)

    ha, hb = text_hash(display_a), text_hash(display_b)
    key = cache_key(MODEL, CRITERION, ha, hb, order)

    payload = {
        "model": MODEL,
        "state": {"Text A": display_a, "Text B": display_b},
        "questions": {
            "winner": {
                "type": "choice",
                "instructions": CHOICE_INSTRUCTIONS,
                "criteria": {"A": "Text A", "B": "Text B"},
            }
        },
    }
    req_rec = {
        "kind": "choice",
        "pair_id": pair["pair_id"],
        "order": order,
        "source": pair.get("source"),
        "gold": pair.get("gold"),
        "id_A": id_a,
        "id_B": id_b,
        "hash_A": ha,
        "hash_B": hb,
        "cache_key": key,
        "payload_meta": {
            "instructions": CHOICE_INSTRUCTIONS,
            "criterion": CRITERION,
            "n_chars_A": len(display_a),
            "n_chars_B": len(display_b),
        },
    }
    append_jsonl(REQUESTS_PATH, req_rec)

    cached = read_cache(key)
    if cached and cached.get("ok"):
        out = dict(cached)
        out["cache_hit"] = True
        out["pair_id"] = pair["pair_id"]
        out["order"] = order
        out["source"] = pair.get("source")
        append_jsonl(ANSWERS_PATH, {k: out[k] for k in out if k != "raw_answer"} | {
            "kind": "choice",
            "winner": out.get("winner"),
            "p_A": out.get("p_A"),
            "p_B": out.get("p_B"),
            "confidence": out.get("confidence"),
            "model": out.get("model"),
            "input_tokens": out.get("input_tokens", 0),
            "output_tokens": out.get("output_tokens", 0),
            "latency_ms": out.get("latency_ms", 0),
            "cache_hit": True,
            "hash_A": ha,
            "hash_B": hb,
            "id_A": id_a,
            "id_B": id_b,
            "gold": pair.get("gold"),
            "source": pair.get("source"),
        })
        bump_progress(cache_hit=True, input_tokens=0)
        return out

    if dry_run:
        return {"ok": False, "dry_run": True, "pair_id": pair["pair_id"], "order": order}

    try:
        result = call_choice(client, text_a=display_a, text_b=display_b)
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
            "criterion": CRITERION,
        }
        write_cache(key, answer)
        append_jsonl(ANSWERS_PATH, answer)
        append_jsonl(RESPONSES_PATH, {
            "pair_id": pair["pair_id"],
            "order": order,
            "kind": "choice",
            "model": result["model"],
            "answer": result["raw_answer"],
            "usage": {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            },
            "latency_ms": result["latency_ms"],
        })
        bump_progress(input_tokens=result["input_tokens"])
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
        }
        append_jsonl(ANSWERS_PATH, err)
        bump_progress(failure=True)
        return err


def process_score_job(
    client,
    *,
    doc: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    doc_id = doc["doc_id"]
    raw = doc.get("raw_text") or doc.get("text") or ""
    stripped = strip_meta(raw) or strip_meta(doc.get("text") or "")
    ht = text_hash(stripped)
    key = score_cache_key(MODEL, CRITERION, ht)

    req_rec = {
        "kind": "score",
        "doc_id": doc_id,
        "hash": ht,
        "cache_key": key,
        "payload_meta": {
            "instructions": SCORE_INSTRUCTIONS,
            "levels": SCORE_LEVELS,
            "n_chars": len(stripped),
        },
    }
    append_jsonl(REQUESTS_PATH, req_rec)

    cached = read_cache(key)
    if cached and cached.get("ok"):
        out = dict(cached)
        out["cache_hit"] = True
        append_jsonl(ANSWERS_PATH, {
            "kind": "score",
            "doc_id": doc_id,
            "score": out.get("score"),
            "confidence": out.get("confidence"),
            "probabilities": out.get("probabilities"),
            "legend": out.get("legend"),
            "model": out.get("model"),
            "input_tokens": out.get("input_tokens", 0),
            "output_tokens": out.get("output_tokens", 0),
            "latency_ms": out.get("latency_ms", 0),
            "cache_hit": True,
            "hash": ht,
            "date": doc.get("date"),
        })
        bump_progress(cache_hit=True)
        return out

    if dry_run:
        return {"ok": False, "dry_run": True, "doc_id": doc_id}

    try:
        result = call_score(client, text=stripped)
        answer = {
            "ok": True,
            "kind": "score",
            "doc_id": doc_id,
            "date": doc.get("date"),
            "hash": ht,
            "score": result["score"],
            "confidence": result["confidence"],
            "probabilities": result["probabilities"],
            "legend": result["legend"],
            "model": result["model"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "latency_ms": result["latency_ms"],
            "cache_hit": False,
            "cache_key": key,
            "criterion": CRITERION,
            "levels": SCORE_LEVELS,
        }
        write_cache(key, answer)
        append_jsonl(ANSWERS_PATH, answer)
        append_jsonl(RESPONSES_PATH, {
            "doc_id": doc_id,
            "kind": "score",
            "model": result["model"],
            "answer": result["raw_answer"],
            "usage": {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            },
            "latency_ms": result["latency_ms"],
        })
        bump_progress(input_tokens=result["input_tokens"])
        return answer
    except SystemExit:
        raise
    except Exception as e:
        err = {
            "ok": False,
            "kind": "score",
            "doc_id": doc_id,
            "error": f"{type(e).__name__}: {e}",
            "hash": ht,
            "cache_key": key,
        }
        append_jsonl(ANSWERS_PATH, err)
        bump_progress(failure=True)
        return err


def load_done_keys_from_answers() -> set[str]:
    """Resume helper: keys already successfully answered in answers.jsonl."""
    done: set[str] = set()
    if not ANSWERS_PATH.exists():
        return done
    for line in ANSWERS_PATH.open():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not d.get("ok", True) and d.get("error"):
            continue
        if d.get("kind") == "choice" and d.get("pair_id") and d.get("order"):
            # Prefer cache_key if present
            if d.get("cache_key"):
                done.add(d["cache_key"])
            else:
                done.add(f"choice:{d['pair_id']}:{d['order']}")
        elif d.get("kind") == "score" and d.get("doc_id"):
            if d.get("cache_key"):
                done.add(d["cache_key"])
            else:
                done.add(f"score:{d['doc_id']}")
    return done


def run_smoke(corpus: dict[str, dict[str, Any]], pairs: list[dict[str, Any]]) -> list[dict]:
    """2–3 live Choice calls: one A pair, one B pair (both orders for A optional)."""
    print("=== SMOKE TEST (live Choice) ===", flush=True)
    client = make_client()
    a_pair = next(p for p in pairs if p["pair_id"].startswith("A"))
    b_pair = next(p for p in pairs if p["pair_id"].startswith("B"))
    results = []
    for pair, order in [(a_pair, "ab"), (b_pair, "ab"), (a_pair, "ba")]:
        print(f"smoke: {pair['pair_id']} order={order} ...", flush=True)
        r = process_choice_job(client, pair=pair, order=order, corpus=corpus)
        results.append(r)
        if r.get("ok"):
            print(
                f"  winner={r['winner']} p_A={r['p_A']:.4f} p_B={r['p_B']:.4f} "
                f"conf={r['confidence']:.4f} model={r['model']} "
                f"tok_in={r['input_tokens']} latency_ms={r['latency_ms']}",
                flush=True,
            )
        else:
            print(f"  FAIL: {r}", flush=True)
    client.close()
    return results


def run_full(
    corpus: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    *,
    concurrency: int = 6,
    skip_score: bool = False,
) -> None:
    print(
        f"=== FULL RUN: {len(pairs)} pairs × 2 orders"
        f"{'' if skip_score else ' + 95 scores'} concurrency={concurrency} ===",
        flush=True,
    )
    client = make_client()

    # Choice jobs
    choice_jobs = [(p, o) for p in pairs for o in ("ab", "ba")]

    def _choice(job):
        pair, order = job
        return process_choice_job(client, pair=pair, order=order, corpus=corpus)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(_choice, j) for j in choice_jobs]
        for fut in as_completed(futs):
            try:
                fut.result()
            except SystemExit:
                raise
            except Exception as e:
                print(f"worker error: {e}", flush=True)

    if not skip_score:
        stmts = [
            d for d in corpus.values()
            if d.get("doc_id", "").startswith("stmt-")
        ]
        stmts.sort(key=lambda d: d.get("date") or "")
        print(f"=== SCORE pass: {len(stmts)} statements ===", flush=True)

        def _score(doc):
            return process_score_job(client, doc=doc)

        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [ex.submit(_score, d) for d in stmts]
            for fut in as_completed(futs):
                try:
                    fut.result()
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"score worker error: {e}", flush=True)

    client.close()


def dedupe_answers_for_cost() -> list[dict[str, Any]]:
    """Latest successful answer per (kind, pair_id/order or doc_id). Prefer non-cache for tokens."""
    if not ANSWERS_PATH.exists():
        return []
    best: dict[str, dict[str, Any]] = {}
    for line in ANSWERS_PATH.open():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("error") and not d.get("ok", True):
            # keep failures out of success set but track separately
            if not d.get("ok", False):
                key = None
                if d.get("kind") == "choice":
                    key = f"choice:{d.get('pair_id')}:{d.get('order')}"
                elif d.get("kind") == "score":
                    key = f"score:{d.get('doc_id')}"
                if key and key not in best:
                    best[key] = d
            continue
        if d.get("kind") == "choice":
            key = f"choice:{d['pair_id']}:{d['order']}"
        elif d.get("kind") == "score":
            key = f"score:{d['doc_id']}"
        else:
            continue
        prev = best.get(key)
        # Prefer successful; among successful prefer non-cache_hit (has real tokens)
        if prev is None:
            best[key] = d
        elif prev.get("error") and not d.get("error"):
            best[key] = d
        elif d.get("ok", True) and not d.get("error"):
            if prev.get("cache_hit") and not d.get("cache_hit"):
                best[key] = d
            elif not prev.get("ok", True):
                best[key] = d
    return list(best.values())


def collect_token_totals_from_cache_and_answers() -> dict[str, Any]:
    """Sum tokens from cache files (authoritative live usage) + answers metadata."""
    records: list[dict[str, Any]] = []
    # Prefer cache directory — each successful live call written once with tokens
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            if d.get("ok"):
                records.append(d)

    # Also merge any answers that somehow aren't cached
    seen_keys = {r.get("cache_key") for r in records if r.get("cache_key")}
    if ANSWERS_PATH.exists():
        for line in ANSWERS_PATH.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not d.get("ok", True) or d.get("error"):
                continue
            ck = d.get("cache_key")
            if ck and ck in seen_keys:
                continue
            if d.get("cache_hit") and not d.get("input_tokens"):
                continue
            records.append(d)
            if ck:
                seen_keys.add(ck)

    return records


def write_cost_and_judgments(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    records = collect_token_totals_from_cache_and_answers()

    # Unique successful choice/score by logical key
    choice_by_key: dict[str, dict] = {}
    score_by_key: dict[str, dict] = {}
    for r in records:
        if r.get("kind") == "choice" and r.get("pair_id") and r.get("order"):
            choice_by_key[f"{r['pair_id']}:{r['order']}"] = r
        elif r.get("kind") == "score" and r.get("doc_id"):
            score_by_key[r["doc_id"]] = r

    # For cost: sum input tokens from ALL cache entries (each live call once)
    # Cache hits don't re-bill; tokens logged at first write
    all_live = [r for r in records if r.get("ok") and not r.get("cache_hit", False)]
    # Actually cache files don't have cache_hit=True on first write
    # All cache files are from live calls
    cache_records = []
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text())
                if d.get("ok"):
                    cache_records.append(d)
            except Exception:
                pass

    input_tokens = sum(int(r.get("input_tokens") or 0) for r in cache_records)
    output_tokens = sum(int(r.get("output_tokens") or 0) for r in cache_records)
    n_calls = len(cache_records)
    latency_total = sum(int(r.get("latency_ms") or 0) for r in cache_records)

    # Count cache hits from answers file (re-reads)
    n_cache_hits = 0
    if ANSWERS_PATH.exists():
        for line in ANSWERS_PATH.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("cache_hit"):
                n_cache_hits += 1

    usd_input = input_tokens * PRICE_PER_MTOK_INPUT / 1e6
    models = {r.get("model") for r in cache_records if r.get("model")}
    model_id = sorted(models)[0] if len(models) == 1 else (sorted(models) if models else MODEL)

    # by stratum
    pair_index = {p["pair_id"]: p for p in pairs}
    by_stratum: dict[str, dict[str, Any]] = {}
    stratum_map = {"extreme": "extreme", "shah": "shah", "adjacent": "adjacent"}

    for key, r in choice_by_key.items():
        pid = r["pair_id"]
        src = r.get("source") or pair_index.get(pid, {}).get("source") or "unknown"
        bucket = stratum_map.get(src, src)
        s = by_stratum.setdefault(
            bucket,
            {
                "n_choice_calls": 0,
                "n_pairs": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "usd": 0.0,
            },
        )
        s["n_choice_calls"] += 1
        # tokens from this call — look up cache record
        tok = int(r.get("input_tokens") or 0)
        s["input_tokens"] += tok
        s["output_tokens"] += int(r.get("output_tokens") or 0)

    # n_pairs per stratum
    for p in pairs:
        bucket = stratum_map.get(p.get("source", ""), p.get("source", "unknown"))
        if bucket in by_stratum:
            by_stratum[bucket]["n_pairs"] = by_stratum[bucket].get("n_pairs", 0)
    # recount pairs properly
    from collections import Counter
    pair_counts = Counter(stratum_map.get(p.get("source", ""), p.get("source")) for p in pairs)
    for bucket, n in pair_counts.items():
        by_stratum.setdefault(bucket, {
            "n_choice_calls": 0, "n_pairs": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0
        })
        by_stratum[bucket]["n_pairs"] = n

    for bucket, s in by_stratum.items():
        s["usd"] = s["input_tokens"] * PRICE_PER_MTOK_INPUT / 1e6
        s["usd_per_pair"] = (s["usd"] / s["n_pairs"]) if s["n_pairs"] else None

    # score_docs stratum
    score_in = sum(int(r.get("input_tokens") or 0) for r in score_by_key.values())
    score_out = sum(int(r.get("output_tokens") or 0) for r in score_by_key.values())
    by_stratum["score_docs"] = {
        "n_score_calls": len(score_by_key),
        "n_docs": len(score_by_key),
        "input_tokens": score_in,
        "output_tokens": score_out,
        "usd": score_in * PRICE_PER_MTOK_INPUT / 1e6,
        "usd_per_doc": (score_in * PRICE_PER_MTOK_INPUT / 1e6 / len(score_by_key))
        if score_by_key else None,
    }

    n_pairs = len(pairs)
    usd_per_pair = (usd_input / n_pairs) if n_pairs else None

    # Failures
    n_failures = 0
    if ANSWERS_PATH.exists():
        # count unique failed keys that have no success
        failed_keys = set()
        ok_keys = set()
        for line in ANSWERS_PATH.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("kind") == "choice":
                k = f"choice:{d.get('pair_id')}:{d.get('order')}"
            elif d.get("kind") == "score":
                k = f"score:{d.get('doc_id')}"
            else:
                continue
            if d.get("error") or d.get("ok") is False:
                failed_keys.add(k)
            else:
                ok_keys.add(k)
        n_failures = len(failed_keys - ok_keys)

    cost = {
        "run_id": RUN_ID,
        "model": model_id if isinstance(model_id, str) else MODEL,
        "model_ids_seen": sorted(models) if models else [MODEL],
        "price_per_mtok_input_usd": PRICE_PER_MTOK_INPUT,
        "output_tokens_free": OUTPUT_FREE,
        "criterion": CRITERION,
        "n_calls": n_calls,
        "n_cache_hits": n_cache_hits,
        "n_failures": n_failures,
        "n_choice_answers": len(choice_by_key),
        "n_score_answers": len(score_by_key),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms_total": latency_total,
            "latency_ms_mean": (latency_total / n_calls) if n_calls else None,
        },
        "cost_usd": {
            "input": round(usd_input, 8),
            "output": 0.0,
            "total": round(usd_input, 8),
        },
        "usd_per_pair": round(usd_per_pair, 8) if usd_per_pair is not None else None,
        "by_stratum": by_stratum,
        "totals": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "n_calls": n_calls,
            "n_cache_hits": n_cache_hits,
            "usd": round(usd_input, 8),
        },
    }
    COST_PATH.parent.mkdir(parents=True, exist_ok=True)
    COST_PATH.write_text(json.dumps(cost, indent=2) + "\n")

    # pair_judgments: average both orders mapped to original a/b
    JUDGMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JUDGMENTS_PATH.open("w") as jf:
        for p in pairs:
            pid = p["pair_id"]
            ab = choice_by_key.get(f"{pid}:ab")
            ba = choice_by_key.get(f"{pid}:ba")
            if not ab and not ba:
                continue
            # Map probs to original gold a/b
            # order ab: Text A = gold a, Text B = gold b → p_A is p(gold a)
            # order ba: Text A = gold b, Text B = gold a → p_A is p(gold b), so p(gold a)=p_B
            probs_a = []
            probs_b = []
            winners_mapped = []
            if ab and ab.get("ok", True) and not ab.get("error"):
                probs_a.append(float(ab["p_A"]))
                probs_b.append(float(ab["p_B"]))
                # winner in display space; map to gold side
                w = ab["winner"]
                winners_mapped.append("a" if w == "A" else "b")
            if ba and ba.get("ok", True) and not ba.get("error"):
                # swap
                probs_a.append(float(ba["p_B"]))
                probs_b.append(float(ba["p_A"]))
                w = ba["winner"]
                # display A = gold b, so winner A means gold b
                winners_mapped.append("b" if w == "A" else "a")

            if not probs_a:
                continue
            p_a_avg = sum(probs_a) / len(probs_a)
            p_b_avg = sum(probs_b) / len(probs_b)
            winner_avg = "a" if p_a_avg >= p_b_avg else "b"
            gold = p.get("gold")
            inverted = (winner_avg != gold) if gold in ("a", "b") else None
            rec = {
                "pair_id": pid,
                "source": p.get("source"),
                "gold": gold,
                "p_A_avg": p_a_avg,
                "p_B_avg": p_b_avg,
                "winner_avg": winner_avg,
                "inverted": inverted,
                "n_orders": len(probs_a),
                "winners_per_order": winners_mapped,
            }
            jf.write(json.dumps(rec) + "\n")

    return cost


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score gold pairs via TypeSafe SystemOne",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Related jsort/jgrep design choices (not flags of this script):\n"
            "  --max-chars defaults to 8000 in jsort/jgrep (design choice; see\n"
            "  results/khaled_sensitivity/ and ANALYSIS §13). This Score/Choice\n"
            "  path does not apply that truncate.\n"
            "  --budget: when running jsort tournaments yourself, set an explicit\n"
            "  dollar budget (or --budget 0) so ranking completes (Khaled tip).\n"
            "  Prefer jgrep --para filter before sorting long openings.\n"
        ),
    )
    parser.add_argument("--live", action="store_true", help="Actually POST to API")
    parser.add_argument("--smoke", action="store_true", help="2–3 live Choice calls only")
    parser.add_argument("--full", action="store_true", help="Full 524 Choice + 95 Score")
    parser.add_argument("--skip-score", action="store_true", help="Skip Score pass")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Only rewrite cost.json + pair_judgments from cache/answers")
    parser.add_argument("--dry-run", action="store_true", help="No API calls")
    args = parser.parse_args()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pairs = load_pairs()
    corpus = load_corpus()
    print(f"loaded {len(pairs)} pairs, {len(corpus)} corpus docs; criterion={CRITERION!r}")

    if args.aggregate_only:
        cost = write_cost_and_judgments(pairs)
        print(json.dumps(cost, indent=2))
        return

    if not args.live and not args.smoke and not args.full:
        print(f"score.py ready. criterion={CRITERION!r} api={API}")
        print(f"pricing: ${PRICE_PER_MTOK_INPUT}/Mtok input; output free={OUTPUT_FREE}")
        print("Pass --live --smoke or --live --full to run.")
        return

    if not ensure_api_key():
        print("TYPESAFE_API_KEY missing", file=sys.stderr)
        sys.exit(1)

    if args.smoke or (args.live and not args.full):
        # default --live alone → smoke first if user asked smoke; else if only --live --smoke
        if args.smoke or not args.full:
            if args.smoke or (args.live and not args.full):
                pass

    if args.smoke:
        results = run_smoke(corpus, pairs)
        write_cost_and_judgments(pairs)
        ok = [r for r in results if r.get("ok")]
        print(f"smoke done: {len(ok)}/{len(results)} ok")
        if len(ok) < 2:
            sys.exit(1)
        return

    if args.full:
        run_full(corpus, pairs, concurrency=args.concurrency, skip_score=args.skip_score)
        cost = write_cost_and_judgments(pairs)
        print("=== COST ===")
        print(json.dumps(cost, indent=2))
        return

    # --live without --full/--smoke: refuse ambiguous
    print("Specify --smoke or --full with --live", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
