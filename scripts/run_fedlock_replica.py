#!/usr/bin/env python3
"""FedLock-faithful protocol replication on chair openings (separate experiment).

Protocol matched to FedLock V3 documentation (jnathan9.github.io/fedlock):
  - Pairwise judge: relative hawkish stance given macro conditions
  - Anonymized texts (strip_meta); no Chair names in state
  - Macro in state: Core PCE (PCEPILFE YoY), UNRATE, GDPC1 growth, VIXCLS
  - TrueSkill μ0=50, σ0=8.33; stop when all σ<2.0 or ~30 comps/doc (cap ~2850)
  - Swiss-style + uncertainty-targeted pairing

Arms: Jev (TypeSafe Choice), Haiku 4.5, FedLock published press_conference (no Llama).

Corpus: data/clean/statements.jsonl (95 openings), matched to FedLock where possible.

This is a SEPARATE experiment from Gate 7 (external consistency only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import trueskill

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.load_typesafe_env import ensure as ensure_typesafe_key  # noqa: E402
from scripts.strip_meta import strip_meta  # noqa: E402

RUN_ID = "fedjev-fedlock-replica-2026-09-20"
JEV_MODEL = "jev-latest"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# FedLock V3 TrueSkill priors
MU0 = 50.0
SIGMA0 = 8.33
SIGMA_STOP = 2.0
MAX_COMPS_PER_DOC = 30
MAX_COMPS_TOTAL = 2850  # ~95 * 30

JEV_PRICE_IN = 0.042  # USD / MTok; output free
HAIKU_PRICE_IN = 1.0
HAIKU_PRICE_OUT = 5.0
HAIKU_USD_CAP = 25.0

# Relative hawkish stance (FedLock), not inflation-only criterion alone
JUDGE_INSTRUCTIONS = (
    "Which of Text A or Text B takes the more hawkish monetary-policy stance "
    "relative to the macroeconomic conditions provided for each text "
    "(Core PCE inflation, unemployment rate, real GDP growth, and VIX). "
    "Judge relative hawkishness given conditions at each speech's time — "
    "not absolute inflation language alone."
)

HAIKU_SYSTEM = (
    "You are a careful rater of central-bank communication. "
    "Compare two anonymized texts on relative hawkish stance given "
    "macroeconomic conditions. "
    "Respond with ONLY a single JSON object, no markdown fences, no commentary."
)

OUT_DIR = ROOT / "results" / "fedlock_replica"
FIG_DIR = ROOT / "results" / "figures"
DOC_FIG = ROOT / "docs" / "figures"
RUN_BASE = ROOT / "runs" / "fedlock_replica"

_write_lock = threading.Lock()
_spend_lock = threading.Lock()
_spend = {"jev_usd": 0.0, "haiku_usd": 0.0, "jev_in": 0, "jev_out": 0,
          "haiku_in": 0, "haiku_out": 0}


def ensure_anthropic_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    for p in (
        Path("/home/box/sand-data/box-secrets.json"),
        Path("/home/box/agent-data/box-secrets.json"),
    ):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        card = d.get("card") or {}
        for k, v in card.items():
            if "ANTHROPIC" in k.upper() and v:
                os.environ["ANTHROPIC_API_KEY"] = v
                return True
    return False


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()


def read_cache(cache_dir: Path, key: str) -> dict[str, Any] | None:
    p = cache_dir / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def write_cache(cache_dir: Path, key: str, obj: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{key}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    tmp.replace(p)


def bump_spend(arm: str, in_tok: int, out_tok: int) -> float:
    with _spend_lock:
        if arm == "jev":
            _spend["jev_in"] += in_tok
            _spend["jev_out"] += out_tok
            _spend["jev_usd"] = _spend["jev_in"] * JEV_PRICE_IN / 1e6
            return _spend["jev_usd"]
        _spend["haiku_in"] += in_tok
        _spend["haiku_out"] += out_tok
        _spend["haiku_usd"] = (
            _spend["haiku_in"] * HAIKU_PRICE_IN / 1e6
            + _spend["haiku_out"] * HAIKU_PRICE_OUT / 1e6
        )
        return _spend["haiku_usd"]


# ---------------------------------------------------------------------------
# Corpus + macro
# ---------------------------------------------------------------------------

def load_statements() -> list[dict[str, Any]]:
    rows = []
    for line in (ROOT / "data/clean/statements.jsonl").open():
        d = json.loads(line)
        raw = d.get("raw_text") or d.get("text") or ""
        stripped = strip_meta(raw)
        if not stripped:
            stripped = strip_meta(d.get("text") or "")
        rows.append({
            "doc_id": d["doc_id"],
            "date": d["date"],
            "stripped": stripped,
            "words": d.get("words"),
            "chair_meta": d.get("chair"),  # not passed to judge
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _asof(df: pd.DataFrame, value_col: str, dt: pd.Timestamp) -> tuple[float | None, str | None]:
    sub = df[df["observation_date"] <= dt]
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    val = row[value_col]
    if pd.isna(val):
        return None, None
    return float(val), str(row["observation_date"].date())


def load_macro_asof(dates: list[str]) -> dict[str, dict[str, Any]]:
    """Core PCE YoY, UNRATE, GDPC1 QoQ SAAR %, VIXCLS as-of each speech date."""
    pce = pd.read_csv(ROOT / "data/raw/fred/PCEPILFE.csv")
    pce["observation_date"] = pd.to_datetime(pce["observation_date"])
    pce = pce.sort_values("observation_date").reset_index(drop=True)
    pce["pce_yoy"] = pce["PCEPILFE"].pct_change(12) * 100.0

    unrate = pd.read_csv(ROOT / "data/raw/fred/UNRATE.csv")
    unrate["observation_date"] = pd.to_datetime(unrate["observation_date"])
    unrate = unrate.sort_values("observation_date")

    gdp = pd.read_csv(ROOT / "data/raw/fred/GDPC1.csv")
    gdp["observation_date"] = pd.to_datetime(gdp["observation_date"])
    gdp = gdp.sort_values("observation_date").reset_index(drop=True)
    # QoQ SAAR percent: ((q/q_prev)^4 - 1) * 100
    gdp["gdp_qoq_saar"] = ((gdp["GDPC1"] / gdp["GDPC1"].shift(1)) ** 4 - 1.0) * 100.0
    gdp["gdp_yoy"] = gdp["GDPC1"].pct_change(4) * 100.0

    vix_path = ROOT / "data/raw/fred/VIXCLS.csv"
    vix_note = None
    if vix_path.exists():
        vix = pd.read_csv(vix_path)
        vix["observation_date"] = pd.to_datetime(vix["observation_date"])
        vix["VIXCLS"] = pd.to_numeric(vix["VIXCLS"], errors="coerce")
        vix = vix.dropna(subset=["VIXCLS"]).sort_values("observation_date")
    else:
        vix = None
        vix_note = "VIXCLS missing from data/raw/fred/"

    out: dict[str, dict[str, Any]] = {}
    for date_str in dates:
        dt = pd.Timestamp(date_str)
        macro: dict[str, Any] = {"asof_date": date_str}
        # Core PCE
        pce_row = pce[pce["observation_date"] <= dt].tail(1)
        if len(pce_row):
            yoy = pce_row["pce_yoy"].iloc[0]
            level = float(pce_row["PCEPILFE"].iloc[0])
            if pd.notna(yoy):
                macro["core_pce_yoy"] = round(float(yoy), 3)
                macro["core_pce"] = round(float(yoy), 3)
                macro["core_pce_source"] = "PCEPILFE_yoy"
            else:
                macro["core_pce_level"] = round(level, 3)
                macro["core_pce"] = round(level, 3)
                macro["core_pce_source"] = "PCEPILFE_level"
            macro["core_pce_obs_date"] = str(pce_row["observation_date"].iloc[0].date())
        # UNRATE
        un_val, un_obs = _asof(unrate, "UNRATE", dt)
        if un_val is not None:
            macro["unrate"] = un_val
            macro["unrate_obs_date"] = un_obs
        # GDPC1
        gdp_row = gdp[gdp["observation_date"] <= dt].tail(1)
        if len(gdp_row):
            qoq = gdp_row["gdp_qoq_saar"].iloc[0]
            yoy_g = gdp_row["gdp_yoy"].iloc[0]
            if pd.notna(qoq):
                macro["gdp_growth"] = round(float(qoq), 3)
                macro["gdp_growth_source"] = "GDPC1_qoq_saar"
            elif pd.notna(yoy_g):
                macro["gdp_growth"] = round(float(yoy_g), 3)
                macro["gdp_growth_source"] = "GDPC1_yoy"
            macro["gdp_obs_date"] = str(gdp_row["observation_date"].iloc[0].date())
        # VIX
        if vix is not None:
            v_val, v_obs = _asof(vix, "VIXCLS", dt)
            if v_val is not None:
                macro["vix"] = round(v_val, 3)
                macro["vix_obs_date"] = v_obs
            else:
                macro["vix_note"] = "no VIXCLS observation on or before date"
        else:
            macro["vix_note"] = vix_note
        out[date_str] = macro
    return out


def compact_macro(m: dict[str, Any]) -> dict[str, Any]:
    """Compact macro blob for judge state (no speaker identity)."""
    keys = [
        "asof_date", "core_pce", "core_pce_source", "unrate",
        "gdp_growth", "gdp_growth_source", "vix",
    ]
    return {k: m[k] for k in keys if k in m and m[k] is not None}


def match_fedlock(stmts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Match statement dates to FedLock press_conference scores."""
    fl = json.loads((ROOT / "data/raw/fedlock/data.json").read_text())
    pcs = {
        s["d"]: s
        for s in fl["speeches"]
        if s.get("st") == "press_conference"
    }
    out: dict[str, dict[str, Any]] = {}
    for s in stmts:
        dt = datetime.strptime(s["date"], "%Y-%m-%d")
        chosen = None
        delta = None
        via = None
        for dlt in (0, 1, -1, 2):
            cand = (dt + timedelta(days=dlt)).strftime("%Y-%m-%d")
            if cand in pcs:
                chosen = pcs[cand]
                delta = dlt
                via = "exact" if dlt == 0 else f"d_field_delta_{dlt}"
                break
        if chosen is None:
            continue
        out[s["doc_id"]] = {
            "fedlock_d": chosen["d"],
            "m": float(chosen["m"]),
            "ma": float(chosen["ma"]),
            "s": float(chosen["s"]),
            "n": int(chosen["n"]),
            "delta_days": delta,
            "match_via": via,
            "tt": chosen.get("tt"),
        }
    return out


# ---------------------------------------------------------------------------
# TrueSkill + pairing
# ---------------------------------------------------------------------------

def make_env() -> trueskill.TrueSkill:
    return trueskill.TrueSkill(
        mu=MU0,
        sigma=SIGMA0,
        beta=SIGMA0 / 2.0,
        tau=SIGMA0 / 100.0,
        draw_probability=0.02,
    )


def soft_rate(
    env: trueskill.TrueSkill,
    r_a: trueskill.Rating,
    r_b: trueskill.Rating,
    p_a_wins: float,
) -> tuple[trueskill.Rating, trueskill.Rating]:
    """Confidence-weighted TrueSkill update via outcome interpolation."""
    p = float(np.clip(p_a_wins, 0.0, 1.0))
    ra_w, rb_l = env.rate_1vs1(r_a, r_b)
    rb_w, ra_l = env.rate_1vs1(r_b, r_a)
    mu_a = p * ra_w.mu + (1.0 - p) * ra_l.mu
    sig_a = p * ra_w.sigma + (1.0 - p) * ra_l.sigma
    mu_b = p * rb_l.mu + (1.0 - p) * rb_w.mu
    sig_b = p * rb_l.sigma + (1.0 - p) * rb_w.sigma
    # floor sigma slightly above 0
    sig_a = max(sig_a, 0.01)
    sig_b = max(sig_b, 0.01)
    return env.create_rating(mu_a, sig_a), env.create_rating(mu_b, sig_b)


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def select_round_pairs(
    doc_ids: list[str],
    ratings: dict[str, trueskill.Rating],
    n_comps: dict[str, int],
    pair_counts: dict[tuple[str, str], int],
    rng: random.Random,
    max_pair_repeats: int = 2,
) -> list[tuple[str, str]]:
    """Swiss-style + uncertainty-targeted: prefer high-σ, similar μ."""
    eligible = [d for d in doc_ids if n_comps[d] < MAX_COMPS_PER_DOC]
    if len(eligible) < 2:
        return []
    # sort by sigma desc, break ties randomly
    eligible.sort(key=lambda d: (-ratings[d].sigma, rng.random()))
    unpaired = set(eligible)
    pairs: list[tuple[str, str]] = []
    while len(unpaired) >= 2:
        # pick highest-σ remaining
        anchor = max(unpaired, key=lambda d: (ratings[d].sigma, rng.random()))
        unpaired.remove(anchor)
        # candidates: similar μ, prefer high σ, respect repeat cap
        cands = []
        for o in unpaired:
            pk = pair_key(anchor, o)
            if pair_counts.get(pk, 0) >= max_pair_repeats:
                continue
            dmu = abs(ratings[anchor].mu - ratings[o].mu)
            cands.append((dmu, -ratings[o].sigma, rng.random(), o))
        if not cands:
            # allow one more repeat if stuck
            for o in unpaired:
                dmu = abs(ratings[anchor].mu - ratings[o].mu)
                cands.append((dmu, -ratings[o].sigma, rng.random(), o))
        if not cands:
            continue
        cands.sort()
        opp = cands[0][3]
        unpaired.remove(opp)
        pairs.append((anchor, opp))
    return pairs


def converged(ratings: dict[str, trueskill.Rating], n_comps: dict[str, int]) -> bool:
    if any(n_comps[d] < 1 for d in ratings):
        return False
    return all(r.sigma < SIGMA_STOP for r in ratings.values())


# ---------------------------------------------------------------------------
# Judges
# ---------------------------------------------------------------------------

def make_jev_client():
    from typesafe_sdk import TypeSafeClient, RetryPolicy
    return TypeSafeClient(
        retry=RetryPolicy(
            max_retries=5,
            backoff_initial=0.5,
            backoff_max=30.0,
            http_statuses={408, 429, 500, 502, 503, 504, 529},
            timeout=180.0,
        ),
        timeout=180.0,
    )


def call_jev(
    client,
    *,
    text_a: str,
    text_b: str,
    macro_a: dict[str, Any],
    macro_b: dict[str, Any],
) -> dict[str, Any]:
    from typesafe_sdk import Choice

    state = {
        "Text A": text_a,
        "Text B": text_b,
        "macro_A": macro_a,
        "macro_B": macro_b,
    }
    t0 = time.perf_counter()
    response = client.system_one(
        model=JEV_MODEL,
        state=state,
        questions={
            "winner": Choice(
                instructions=JUDGE_INSTRUCTIONS,
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
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "latency_ms": latency_ms,
    }


def build_haiku_user(
    text_a: str, text_b: str, macro_a: dict[str, Any], macro_b: dict[str, Any]
) -> str:
    return (
        f"Criterion: which text takes the more hawkish monetary-policy stance "
        f"relative to the macroeconomic conditions at the time of each text?\n\n"
        f"Macro conditions for Text A:\n{json.dumps(macro_a, sort_keys=True)}\n\n"
        f"Macro conditions for Text B:\n{json.dumps(macro_b, sort_keys=True)}\n\n"
        f"Text A:\n{text_a}\n\n"
        f"Text B:\n{text_b}\n\n"
        "Return JSON with keys:\n"
        '  "winner": "A" or "B",\n'
        '  "p_A": probability Text A is more hawkish given its conditions (0-1),\n'
        '  "p_B": probability Text B is more hawkish given its conditions (0-1),\n'
        '  "confidence": your confidence in the winner (0-1).\n'
        "Require p_A + p_B = 1. Prefer calibrated probabilities, not 0/1 unless certain.\n"
        "Judge relative to conditions — the same language can be hawkish under low "
        "inflation and merely baseline under high inflation."
    )


def parse_haiku_answer(text: str) -> dict[str, Any]:
    import re
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    obj = None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
        except Exception:
            obj = None
    if obj is None:
        # Truncated or messy JSON: pull fields with regex
        wm = re.search(r'"winner"\s*:\s*"(A|B)"', text, re.I)
        pam = re.search(r'"p_A"\s*:\s*([0-9.]+)', text)
        pbm = re.search(r'"p_B"\s*:\s*([0-9.]+)', text)
        cm = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
        if not wm:
            raise ValueError(f"no JSON in response: {text[:200]!r}")
        obj = {
            "winner": wm.group(1).upper(),
            "p_A": float(pam.group(1)) if pam else 0.5,
            "p_B": float(pbm.group(1)) if pbm else 0.5,
            "confidence": float(cm.group(1)) if cm else 0.5,
        }
    winner = str(obj.get("winner", "")).strip().upper()
    if winner not in ("A", "B"):
        raise ValueError(f"bad winner: {winner!r}")
    p_a = float(obj.get("p_A", 0.5))
    p_b = float(obj.get("p_B", 1.0 - p_a))
    s = p_a + p_b
    if s <= 0:
        p_a, p_b = (1.0, 0.0) if winner == "A" else (0.0, 1.0)
    else:
        p_a, p_b = p_a / s, p_b / s
    if (p_a >= p_b and winner != "A") or (p_b > p_a and winner != "B"):
        winner = "A" if p_a >= p_b else "B"
    conf = float(obj.get("confidence", max(p_a, p_b)))
    return {"winner": winner, "p_A": p_a, "p_B": p_b, "confidence": conf}


def call_haiku(
    client,
    *,
    text_a: str,
    text_b: str,
    macro_a: dict[str, Any],
    macro_b: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    last_err = None
    msg = None
    for attempt in range(8):
        try:
            msg = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=512,
                system=HAIKU_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": build_haiku_user(text_a, text_b, macro_a, macro_b),
                }],
            )
            break
        except Exception as e:
            last_err = e
            name = type(e).__name__
            status = getattr(e, "status_code", None)
            retryable = (
                name in ("RateLimitError", "APIStatusError", "APIConnectionError",
                         "APITimeoutError")
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
    parsed = parse_haiku_answer(raw_text)
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
        "raw_text": raw_text[:1500],
    }


def cache_key_for(
    arm: str,
    id_a: str,
    id_b: str,
    order: str,
    macro_a: dict,
    macro_b: dict,
) -> str:
    blob = json.dumps({"A": macro_a, "B": macro_b}, sort_keys=True)
    raw = f"{arm}|{JUDGE_INSTRUCTIONS}|{id_a}|{id_b}|{order}|{blob}|fedlock_replica_v1"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Tournament runner
# ---------------------------------------------------------------------------

def run_arm(
    arm: str,
    stmts: list[dict[str, Any]],
    macros: dict[str, dict[str, Any]],
    *,
    concurrency: int = 6,
    seed: int = 20260920,
    dry_run: bool = False,
    max_comps: int = MAX_COMPS_TOTAL,
) -> dict[str, Any]:
    assert arm in ("jev", "haiku")
    rng = random.Random(seed)
    env = make_env()
    by_id = {s["doc_id"]: s for s in stmts}
    doc_ids = [s["doc_id"] for s in stmts]
    ratings = {d: env.create_rating(MU0, SIGMA0) for d in doc_ids}
    n_comps = {d: 0 for d in doc_ids}
    pair_counts: dict[tuple[str, str], int] = {}

    cache_dir = RUN_BASE / arm / "cache"
    comps_path = OUT_DIR / f"comparisons_{arm}.jsonl"
    state_path = RUN_BASE / arm / "tournament_state.json"
    sigma_hist_path = RUN_BASE / arm / "sigma_history.jsonl"
    cache_dir.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Resume from prior comparisons if present
    prior_comps: list[dict] = []
    if comps_path.exists():
        for line in comps_path.open():
            if line.strip():
                prior_comps.append(json.loads(line))
        print(f"[{arm}] resuming: replaying {len(prior_comps)} prior comparisons", flush=True)
        for c in prior_comps:
            id_a, id_b = c["doc_id_a"], c["doc_id_b"]
            p_doc_a = float(c.get("p_doc_a_wins", c["p_A"]))
            ratings[id_a], ratings[id_b] = soft_rate(
                env, ratings[id_a], ratings[id_b], p_doc_a
            )
            n_comps[id_a] += 1
            n_comps[id_b] += 1
            pk = pair_key(id_a, id_b)
            pair_counts[pk] = pair_counts.get(pk, 0) + 1
        bump_spend(arm, sum(c.get("input_tokens", 0) for c in prior_comps
                            if not c.get("cache_hit")),
                   sum(c.get("output_tokens", 0) for c in prior_comps
                       if not c.get("cache_hit")))

    if arm == "jev":
        if not ensure_typesafe_key():
            raise RuntimeError("TYPESAFE_API_KEY missing")
        client = None if dry_run else make_jev_client()
    else:
        if not ensure_anthropic_key():
            raise RuntimeError("ANTHROPIC_API_KEY missing")
        if dry_run:
            client = None
        else:
            import anthropic
            client = anthropic.Anthropic()

    total_comps = sum(n_comps.values()) // 2
    round_idx = 0
    latencies: list[float] = []
    t_wall0 = time.perf_counter()
    stop_reason = None

    while total_comps < max_comps and not converged(ratings, n_comps):
        if arm == "haiku" and _spend["haiku_usd"] > HAIKU_USD_CAP:
            stop_reason = f"haiku_usd_cap_{HAIKU_USD_CAP}"
            print(f"[haiku] STOP: spend ${_spend['haiku_usd']:.2f} > ${HAIKU_USD_CAP}", flush=True)
            break

        pairs = select_round_pairs(doc_ids, ratings, n_comps, pair_counts, rng)
        if not pairs:
            stop_reason = "no_eligible_pairs"
            break
        # trim if would exceed cap
        remaining = max_comps - total_comps
        if len(pairs) > remaining:
            pairs = pairs[:remaining]

        round_idx += 1
        print(
            f"[{arm}] round {round_idx}: {len(pairs)} pairs; "
            f"comps={total_comps}; max_σ={max(r.sigma for r in ratings.values()):.3f}; "
            f"usd≈{_spend[arm + '_usd']:.4f}",
            flush=True,
        )

        # Prepare jobs with randomized presentation order
        jobs = []
        for da, db in pairs:
            order = "ab" if rng.random() < 0.5 else "ba"
            if order == "ab":
                id_disp_a, id_disp_b = da, db
            else:
                id_disp_a, id_disp_b = db, da
            ma = compact_macro(macros[by_id[id_disp_a]["date"]])
            mb = compact_macro(macros[by_id[id_disp_b]["date"]])
            key = cache_key_for(arm, id_disp_a, id_disp_b, order, ma, mb)
            jobs.append({
                "doc_id_a": da,  # TrueSkill side A = first in pair tuple (anchor)
                "doc_id_b": db,
                "id_disp_a": id_disp_a,
                "id_disp_b": id_disp_b,
                "order": order,
                "macro_disp_a": ma,
                "macro_disp_b": mb,
                "cache_key": key,
                "text_a": by_id[id_disp_a]["stripped"],
                "text_b": by_id[id_disp_b]["stripped"],
            })

        def run_one(job: dict) -> dict:
            cached = read_cache(cache_dir, job["cache_key"])
            if cached and cached.get("ok"):
                return {**job, **cached, "cache_hit": True, "ok": True}
            if dry_run:
                # deterministic pseudo outcome from hashes
                h = int(job["cache_key"][:8], 16)
                p = 0.35 + (h % 31) / 100.0
                return {
                    **job, "ok": True, "cache_hit": False, "dry_run": True,
                    "winner": "A" if p >= 0.5 else "B",
                    "p_A": p, "p_B": 1 - p, "confidence": abs(p - 0.5) * 2,
                    "input_tokens": 1000, "output_tokens": 30, "latency_ms": 10,
                    "model": "dry-run",
                }
            try:
                if arm == "jev":
                    res = call_jev(
                        client,
                        text_a=job["text_a"], text_b=job["text_b"],
                        macro_a=job["macro_disp_a"], macro_b=job["macro_disp_b"],
                    )
                else:
                    res = call_haiku(
                        client,
                        text_a=job["text_a"], text_b=job["text_b"],
                        macro_a=job["macro_disp_a"], macro_b=job["macro_disp_b"],
                    )
                out = {**job, **res, "ok": True, "cache_hit": False}
                write_cache(cache_dir, job["cache_key"], {
                    "ok": True,
                    "winner": res["winner"], "p_A": res["p_A"], "p_B": res["p_B"],
                    "confidence": res["confidence"],
                    "input_tokens": res["input_tokens"],
                    "output_tokens": res["output_tokens"],
                    "latency_ms": res["latency_ms"],
                    "model": res["model"],
                })
                return out
            except Exception as e:
                return {**job, "ok": False, "error": repr(e), "cache_hit": False}

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [ex.submit(run_one, j) for j in jobs]
            for fut in as_completed(futs):
                results.append(fut.result())

        # Sequential TrueSkill updates (order by completed list is fine)
        for res in results:
            if not res.get("ok"):
                print(f"[{arm}] FAIL {res.get('error')}", flush=True)
                continue
            # Map display probs → doc_id_a / doc_id_b
            # display A is id_disp_a; we need P(doc_id_a beats doc_id_b)
            if res["id_disp_a"] == res["doc_id_a"]:
                p_doc_a = float(res["p_A"])
            else:
                p_doc_a = float(res["p_B"])

            da, db = res["doc_id_a"], res["doc_id_b"]
            ratings[da], ratings[db] = soft_rate(env, ratings[da], ratings[db], p_doc_a)
            n_comps[da] += 1
            n_comps[db] += 1
            pk = pair_key(da, db)
            pair_counts[pk] = pair_counts.get(pk, 0) + 1
            total_comps += 1

            in_tok = int(res.get("input_tokens") or 0)
            out_tok = int(res.get("output_tokens") or 0)
            lat = float(res.get("latency_ms") or 0)
            if not res.get("cache_hit"):
                usd = bump_spend(arm, in_tok, out_tok)
                latencies.append(lat)
            else:
                usd = _spend[arm + "_usd"]

            # cost for this comparison (0 if cache hit)
            if arm == "jev":
                cost = 0.0 if res.get("cache_hit") else in_tok * JEV_PRICE_IN / 1e6
            else:
                cost = 0.0 if res.get("cache_hit") else (
                    in_tok * HAIKU_PRICE_IN / 1e6 + out_tok * HAIKU_PRICE_OUT / 1e6
                )

            rec = {
                "run_id": RUN_ID,
                "arm": arm,
                "round": round_idx,
                "doc_id_a": da,
                "doc_id_b": db,
                "date_a": by_id[da]["date"],
                "date_b": by_id[db]["date"],
                "order": res["order"],
                "id_disp_a": res["id_disp_a"],
                "id_disp_b": res["id_disp_b"],
                "macro_A": res["macro_disp_a"],
                "macro_B": res["macro_disp_b"],
                "winner_disp": res.get("winner"),
                "p_A": float(res.get("p_A", 0.5)),
                "p_B": float(res.get("p_B", 0.5)),
                "p_doc_a_wins": p_doc_a,
                "confidence": float(res.get("confidence", 0.5)),
                "model": res.get("model"),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "latency_ms": lat,
                "cost_usd": cost,
                "cache_hit": bool(res.get("cache_hit")),
                "mu_a_after": ratings[da].mu,
                "sigma_a_after": ratings[da].sigma,
                "mu_b_after": ratings[db].mu,
                "sigma_b_after": ratings[db].sigma,
                "running_usd": usd,
            }
            append_jsonl(comps_path, rec)

        # sigma history snapshot
        append_jsonl(sigma_hist_path, {
            "round": round_idx,
            "n_comps": total_comps,
            "max_sigma": max(r.sigma for r in ratings.values()),
            "mean_sigma": float(np.mean([r.sigma for r in ratings.values()])),
            "frac_below_2": float(np.mean([r.sigma < SIGMA_STOP for r in ratings.values()])),
            "usd": _spend[arm + "_usd"],
        })

        # persist state
        state_path.write_text(json.dumps({
            "arm": arm,
            "n_comps_total": total_comps,
            "n_comps": n_comps,
            "ratings": {d: {"mu": ratings[d].mu, "sigma": ratings[d].sigma} for d in doc_ids},
            "pair_counts": {f"{a}|{b}": c for (a, b), c in pair_counts.items()},
            "spend_usd": _spend[arm + "_usd"],
        }, indent=2))

        if arm == "haiku" and _spend["haiku_usd"] > HAIKU_USD_CAP:
            stop_reason = f"haiku_usd_cap_{HAIKU_USD_CAP}"
            break

    if stop_reason is None:
        if converged(ratings, n_comps):
            stop_reason = "all_sigma_lt_2"
        elif total_comps >= max_comps:
            stop_reason = "max_comps"
        else:
            stop_reason = "loop_exit"

    wall_s = time.perf_counter() - t_wall0
    # Write trueskill CSV
    rows = []
    for s in stmts:
        d = s["doc_id"]
        rows.append({
            "date": s["date"],
            "doc_id": d,
            "mu": ratings[d].mu,
            "sigma": ratings[d].sigma,
            "n_comps": n_comps[d],
        })
    csv_path = OUT_DIR / f"trueskill_{arm}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    return {
        "arm": arm,
        "stop_reason": stop_reason,
        "n_comps": total_comps,
        "n_docs": len(doc_ids),
        "wall_seconds": wall_s,
        "latencies_ms": latencies,
        "ratings": {d: {"mu": ratings[d].mu, "sigma": ratings[d].sigma} for d in doc_ids},
        "n_comps_by_doc": n_comps,
        "csv_path": str(csv_path),
        "comps_path": str(comps_path),
        "input_tokens": _spend[arm + "_in"],
        "output_tokens": _spend[arm + "_out"],
        "usd": _spend[arm + "_usd"],
        "max_sigma": max(r.sigma for r in ratings.values()),
        "mean_sigma": float(np.mean([r.sigma for r in ratings.values()])),
        "frac_sigma_lt_2": float(np.mean([r.sigma < SIGMA_STOP for r in ratings.values()])),
    }


# ---------------------------------------------------------------------------
# Agreement + cost + figures + FINDINGS
# ---------------------------------------------------------------------------

def bootstrap_rank_corr(
    x: np.ndarray, y: np.ndarray, *, method: str, n_boot: int = 1000, seed: int = 20260920
) -> dict[str, Any]:
    from scipy.stats import spearmanr, kendalltau
    n = len(x)
    if n < 3:
        return {"rho": None, "ste": None, "ci_low": None, "ci_high": None, "n": n}
    if method == "spearman":
        rho, _ = spearmanr(x, y)
        def fn(a, b):
            r, _ = spearmanr(a, b)
            return r
    else:
        rho, _ = kendalltau(x, y)
        def fn(a, b):
            r, _ = kendalltau(a, b)
            return r
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots.append(fn(x[idx], y[idx]))
    boots = np.asarray(boots, dtype=float)
    boots = boots[np.isfinite(boots)]
    ste = float(np.std(boots, ddof=1)) if len(boots) > 1 else None
    lo = float(np.percentile(boots, 2.5)) if len(boots) else None
    hi = float(np.percentile(boots, 97.5)) if len(boots) else None
    return {
        "rho": float(rho) if rho is not None and np.isfinite(rho) else None,
        "ste": ste,
        "ci_low": lo,
        "ci_high": hi,
        "n": n,
        "n_boot": len(boots),
    }


def latency_stats(xs: list[float]) -> dict[str, float | None]:
    if not xs:
        return {"mean": None, "p50": None, "p95": None}
    a = np.asarray(xs, dtype=float)
    return {
        "mean": float(np.mean(a)),
        "p50": float(np.percentile(a, 50)),
        "p95": float(np.percentile(a, 95)),
    }


def build_cost_performance(jev_sum: dict, haiku_sum: dict) -> dict:
    out = {}
    for arm, s in (("jev", jev_sum), ("haiku", haiku_sum)):
        if not s:
            continue
        n = s["n_comps"]
        in_tok = s["input_tokens"]
        out_tok = s["output_tokens"]
        usd = s["usd"]
        lstat = latency_stats(s.get("latencies_ms") or [])
        wall = s.get("wall_seconds") or 0.0
        # effective $/MTok: total usd / (in+out) * 1e6 for haiku; for jev output free
        tot_tok = in_tok + out_tok
        usd_per_mtok_eff = (usd / tot_tok * 1e6) if tot_tok else None
        out[arm] = {
            "n_comps": n,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "usd": usd,
            "usd_per_mtok_effective": usd_per_mtok_eff,
            "usd_per_comparison": (usd / n) if n else None,
            "latency_ms": lstat,
            "comps_per_second": (n / wall) if wall > 0 else None,
            "wall_seconds": wall,
            "stop_reason": s.get("stop_reason"),
            "max_sigma": s.get("max_sigma"),
            "mean_sigma": s.get("mean_sigma"),
            "frac_sigma_lt_2": s.get("frac_sigma_lt_2"),
        }
    # FedLock published: no API cost
    out["fedlock_published"] = {
        "n_comps": None,
        "note": "Published press_conference m/ma/s/n from data/raw/fedlock/data.json; Llama not re-called",
        "usd": 0.0,
    }
    return out


def build_agreement(
    stmts: list[dict],
    jev_csv: Path,
    haiku_csv: Path,
    fedlock: dict[str, dict],
) -> dict:
    jev = pd.read_csv(jev_csv).set_index("doc_id") if jev_csv.exists() else None
    haiku = pd.read_csv(haiku_csv).set_index("doc_id") if haiku_csv.exists() else None

    # Align on docs present in all relevant sets
    def corr_pair(left: pd.Series, right: pd.Series, label: str) -> dict:
        common = left.index.intersection(right.index)
        x = left.loc[common].astype(float).values
        y = right.loc[common].astype(float).values
        sp = bootstrap_rank_corr(x, y, method="spearman")
        kd = bootstrap_rank_corr(x, y, method="kendall", seed=20260921)
        return {
            "contrast": label,
            "n": int(len(common)),
            "spearman": sp,
            "kendall": kd,
        }

    results = []
    # Build FedLock series indexed by doc_id
    fl_m = pd.Series({d: fedlock[d]["m"] for d in fedlock})
    fl_ma = pd.Series({d: fedlock[d]["ma"] for d in fedlock})

    if jev is not None and haiku is not None:
        results.append(corr_pair(jev["mu"], haiku["mu"], "Jev↔Haiku"))
    if jev is not None:
        results.append(corr_pair(jev["mu"], fl_m, "Jev↔FedLock m"))
        results.append(corr_pair(jev["mu"], fl_ma, "Jev↔FedLock ma"))
    if haiku is not None:
        results.append(corr_pair(haiku["mu"], fl_m, "Haiku↔FedLock m"))
        results.append(corr_pair(haiku["mu"], fl_ma, "Haiku↔FedLock ma"))

    return {
        "run_id": RUN_ID,
        "n_statements": len(stmts),
        "n_fedlock_matched": len(fedlock),
        "contrasts": results,
    }


def make_figures(
    stmts: list[dict],
    jev_csv: Path,
    haiku_csv: Path,
    fedlock: dict[str, dict],
    cost: dict,
) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DOC_FIG.mkdir(parents=True, exist_ok=True)
    paths = []

    jev = pd.read_csv(jev_csv) if jev_csv.exists() else None
    haiku = pd.read_csv(haiku_csv) if haiku_csv.exists() else None

    def save(fig, name: str):
        for base in (FIG_DIR, DOC_FIG):
            p = base / name
            fig.savefig(p, dpi=140, bbox_inches="tight")
            paths.append(str(p))
        plt.close(fig)

    # Rank scatters
    def scatter_mu(df_left, label_l, right_map, label_r, fname):
        xs, ys, dates = [], [], []
        for _, row in df_left.iterrows():
            did = row["doc_id"]
            if did not in right_map:
                continue
            xs.append(row["mu"])
            ys.append(right_map[did])
            dates.append(row["date"])
        if len(xs) < 3:
            return
        fig, ax = plt.subplots(figsize=(5.5, 5.0))
        ax.scatter(xs, ys, s=28, alpha=0.75, edgecolors="none", c="#1f4e79")
        lo = min(min(xs), min(ys)) - 2
        hi = max(max(xs), max(ys)) + 2
        ax.plot([lo, hi], [lo, hi], ls="--", c="0.6", lw=1)
        ax.set_xlabel(f"{label_l} TrueSkill μ")
        ax.set_ylabel(f"{label_r}")
        ax.set_title(f"{label_l} vs {label_r} (n={len(xs)})")
        ax.set_aspect("equal", adjustable="box")
        save(fig, fname)

    fl_m = {d: fedlock[d]["m"] for d in fedlock}
    if jev is not None:
        scatter_mu(jev, "Jev", fl_m, "FedLock m", "fedlock_replica_scatter_jev_vs_fedlock.png")
    if haiku is not None:
        scatter_mu(haiku, "Haiku", fl_m, "FedLock m", "fedlock_replica_scatter_haiku_vs_fedlock.png")
    if jev is not None and haiku is not None:
        hmap = dict(zip(haiku["doc_id"], haiku["mu"]))
        scatter_mu(jev, "Jev", hmap, "Haiku μ", "fedlock_replica_scatter_jev_vs_haiku.png")

    # μ timelines
    fig, ax = plt.subplots(figsize=(9, 4.2))
    if jev is not None:
        j = jev.sort_values("date")
        ax.plot(pd.to_datetime(j["date"]), j["mu"], label="Jev μ", lw=1.6, c="#1f4e79")
    if haiku is not None:
        h = haiku.sort_values("date")
        ax.plot(pd.to_datetime(h["date"]), h["mu"], label="Haiku μ", lw=1.6, c="#c45c26")
    # FedLock on matched dates
    fl_dates, fl_ms = [], []
    for s in stmts:
        if s["doc_id"] in fedlock:
            fl_dates.append(pd.Timestamp(s["date"]))
            fl_ms.append(fedlock[s["doc_id"]]["m"])
    if fl_dates:
        order = np.argsort(fl_dates)
        ax.plot(
            np.array(fl_dates)[order], np.array(fl_ms)[order],
            label="FedLock m", lw=1.2, c="0.35", ls="--",
        )
    ax.axhline(50, c="0.7", lw=0.8)
    ax.set_ylabel("TrueSkill μ (50 = prior mean)")
    ax.set_title("Hawkishness μ timelines (openings corpus)")
    ax.legend(frameon=False, fontsize=9)
    fig.autofmt_xdate()
    save(fig, "fedlock_replica_mu_timelines.png")

    # Cost / latency bars
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.8))
    arms = []
    usd_mtok = []
    lat_mean = []
    for arm in ("jev", "haiku"):
        if arm not in cost:
            continue
        arms.append(arm)
        usd_mtok.append(cost[arm].get("usd_per_mtok_effective") or 0)
        lat_mean.append((cost[arm].get("latency_ms") or {}).get("mean") or 0)
    if arms:
        axes[0].bar(arms, usd_mtok, color=["#1f4e79", "#c45c26"][:len(arms)])
        axes[0].set_ylabel("USD per effective MTok")
        axes[0].set_title("Cost efficiency")
        axes[1].bar(arms, lat_mean, color=["#1f4e79", "#c45c26"][:len(arms)])
        axes[1].set_ylabel("Mean latency (ms)")
        axes[1].set_title("Latency")
    fig.suptitle("FedLock-replica arms: cost and latency", fontsize=11)
    fig.tight_layout()
    save(fig, "fedlock_replica_cost_latency.png")

    # σ convergence curves
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    for arm, color in (("jev", "#1f4e79"), ("haiku", "#c45c26")):
        p = RUN_BASE / arm / "sigma_history.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.open() if l.strip()]
        if not rows:
            continue
        ax.plot(
            [r["n_comps"] for r in rows],
            [r["max_sigma"] for r in rows],
            label=f"{arm} max σ", c=color, lw=1.6,
        )
        ax.plot(
            [r["n_comps"] for r in rows],
            [r["mean_sigma"] for r in rows],
            label=f"{arm} mean σ", c=color, lw=1.0, ls="--",
        )
    ax.axhline(SIGMA_STOP, c="0.5", ls=":", label="σ=2.0 stop")
    ax.set_xlabel("Comparisons completed")
    ax.set_ylabel("σ")
    ax.set_title("TrueSkill σ convergence")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "fedlock_replica_sigma_convergence.png")

    return paths


def write_findings(
    agreement: dict,
    cost: dict,
    jev_sum: dict | None,
    haiku_sum: dict | None,
    fedlock: dict,
    protocol_notes: list[str],
) -> Path:
    path = OUT_DIR / "FINDINGS.md"

    def fmt_corr(c: dict) -> str:
        sp = c["spearman"]
        kd = c["kendall"]
        def one(lab, d):
            if d.get("rho") is None:
                return f"{lab}: n/a"
            return (
                f"{lab} = {d['rho']:+.3f} (s.e. = {d['ste']:.3f}; "
                f"95% CI [{d['ci_low']:+.3f}, {d['ci_high']:+.3f}]; n = {d['n']})"
            )
        return f"- **{c['contrast']}.** {one('Spearman', sp)}; {one('Kendall', kd)}."

    n_stmt = agreement.get("n_statements", 95)
    n_match = len(fedlock)
    lines = []
    lines.append("# FedLock-faithful protocol replication — Findings")
    lines.append("")
    lines.append(f"**run_id:** `{RUN_ID}`  ")
    lines.append(
        "**Companion claim (do not conflate):** Gate 7 in the main bench is a different "
        "experiment. Gate 7 asks whether this repository’s Bradley–Terry and Score series "
        "*agree in rank* with published FedLock scores. This note asks whether a *separate* "
        "tournament, run on the same chair openings under FedLock V3’s documented protocol, "
        "recovers a similar ordering. It is not a 4,000-speech / ~60,000-comparison scale "
        "copy of the published FedLock run."
    )
    lines.append("")
    lines.append(
        "This document is written so a reader fluent in finance and monetary policy, "
        "but not in natural-language processing, can re-implement the comparison from "
        "the prose and the frozen artifacts. Numbers below are taken from `agreement.json` "
        "and `cost_performance.json`. None were invented for this write-up."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. What each name means in this note")
    lines.append("")
    lines.append(
        "**Federal Open Market Committee (FOMC).** The Federal Reserve committee that "
        "sets the federal funds target. The documents scored here are the Chair’s opening "
        f"remarks at post-meeting press conferences ({n_stmt} openings in "
        "`data/clean/statements.jsonl`)."
    )
    lines.append("")
    lines.append(
        "**Behavioral label versus textual hawkishness.** The Committee’s voted action "
        "is a *behavioral* label. In the main bench that label is `d_same`, the same-day "
        "change in the federal funds target: hike, hold, or cut. A hold day has "
        "`d_same = 0` by construction, so the behavioral label cannot say whether the "
        "*wording* of a hold was hawkish or dovish. *Textual hawkishness* is a separate "
        "construct: how hawkish the opening sounds about inflation and the policy path. "
        "This replica ranks openings on textual hawkishness *relative to the macro "
        "conditions attached to each text*. It does not use `d_same` as the scoring target."
    )
    lines.append("")
    lines.append(
        "**FedLock.** An independent, published scoring project "
        "([methodology](https://jnathan9.github.io/fedlock/); snapshot in "
        "`data/raw/fedlock/data.json`). FedLock V3 runs a large pairwise tournament: a "
        "large language model (Llama 3.3 70B) is shown two anonymized speeches and asked "
        "which takes the more hawkish monetary-policy stance *given* contemporaneous macro "
        "conditions. Those pairwise wins are aggregated with TrueSkill (defined below) "
        "over roughly 60,000 comparisons and 4,000 speeches. This repository does **not** "
        "re-invoke Llama. It only reads the published `press_conference` fields: `m` "
        "(raw TrueSkill mean), `ma` (era-adjusted mean), `s` (uncertainty), `n` "
        "(comparisons in FedLock’s own run), `st` (speech type), and `d` (date)."
    )
    lines.append("")
    lines.append(
        "**TrueSkill versus Bradley–Terry.** Bradley–Terry (main bench, Gates 1–7) fits "
        "one strength per document from a fixed gold-pair graph. TrueSkill (published "
        "FedLock and this replica) is Microsoft’s Bayesian skill-rating system. Each "
        "document starts at prior mean μ₀ = 50 and prior uncertainty σ₀ = 8.33. The "
        "replica stops when every document has σ < 2.0, or when it hits the comparison "
        "caps. **σ < 2** is a convergence rule, not a hawkishness threshold."
    )
    lines.append("")
    lines.append(
        "**Anonymized pairwise tournament.** Each comparison shows two stripped texts. "
        "`scripts/strip_meta.py` removes speaker titles, calendar dates, and chair "
        "surnames. Chair identity is not placed in the judge’s input. Presentation order "
        "of Text A / Text B is randomized each match."
    )
    lines.append("")
    lines.append(
        "**Macro-conditioned judgment.** Each text is paired with four Federal Reserve "
        "Economic Data (FRED) series as of that speech date: core personal consumption "
        "expenditures inflation (PCEPILFE, year-over-year when computable, otherwise the "
        "level); the civilian unemployment rate (UNRATE); real gross domestic product "
        "growth (GDPC1, quarter-over-quarter at a seasonally adjusted annual rate when "
        "available, otherwise year-over-year); and the CBOE Volatility Index close "
        "(VIXCLS). The instruction is relative hawkishness *given those conditions*."
    )
    lines.append("")
    lines.append(
        f"**Arms.** (i) Jev — TypeSafe SystemOne Choice (`{JEV_MODEL}`). "
        f"(ii) Haiku — Claude `{HAIKU_MODEL}`, structured JSON winner and a soft "
        "probability. (iii) Published FedLock — frozen `m` / `ma` / `s` / `n` from "
        "`data/raw/fedlock/data.json` (Llama not re-invoked)."
    )
    lines.append("")
    lines.append(
        f"FedLock date matching (offsets 0, +1, −1, +2 on `d`): "
        f"**{n_match}** of {n_stmt} openings matched."
    )
    if protocol_notes:
        lines.append("")
        lines.append("### Protocol deviations / notes (observed)")
        lines.append("")
        for n in protocol_notes:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("## 2. Rank agreement")
    lines.append("")
    lines.append(
        "**Spearman’s rank correlation** compares two orderings of meetings. "
        "**Kendall’s rank correlation** is the pairwise version of the same question. "
        "The **standard error (s.e.)** is the standard deviation of 1,000 bootstrap "
        "meeting resamples; the 95 percent interval is the percentile interval from "
        "the same resamples. This note writes “standard error” or “s.e.” It does not "
        "use the label STE."
    )
    lines.append("")
    for c in agreement.get("contrasts", []):
        lines.append(fmt_corr(c))
    lines.append("")
    lines.append("## 3. Cost and performance (listed prices; not an accuracy claim)")
    lines.append("")
    lines.append(
        "Prices used for the accounting: "
        f"Jev ${JEV_PRICE_IN} per million input tokens, output free; "
        f"Haiku ${HAIKU_PRICE_IN} per million input tokens and "
        f"${HAIKU_PRICE_OUT} per million output tokens."
    )
    lines.append("")
    lines.append(
        "| Arm | Comparisons | Input tokens | Output tokens | USD | "
        "Effective $/million tokens | $/comparison | "
        "Latency mean / median / 95th percentile (ms) | Comparisons/s |"
    )
    lines.append(
        "|-----|------------:|-------------:|--------------:|----:"
        "|---------------------------:|-------------:"
        "|---------------------------------------------:|--------------:|"
    )
    arm_labels = {"jev": "Jev", "haiku": "Haiku"}
    for arm in ("jev", "haiku"):
        c = cost.get(arm) or {}
        if not c:
            continue
        lat = c.get("latency_ms") or {}
        lines.append(
            f"| {arm_labels[arm]} | {c.get('n_comps')} | {c.get('input_tokens')} | "
            f"{c.get('output_tokens')} | "
            f"{c.get('usd'):.4f} | "
            f"{(c.get('usd_per_mtok_effective') or 0):.4f} | "
            f"{(c.get('usd_per_comparison') or 0):.6f} | "
            f"{(lat.get('mean') or 0):.0f} / {(lat.get('p50') or 0):.0f} / "
            f"{(lat.get('p95') or 0):.0f} | "
            f"{(c.get('comps_per_second') or 0):.3f} |"
        )
    lines.append("")
    if jev_sum:
        lines.append(
            f"Jev stop: `{jev_sum.get('stop_reason')}`; "
            f"max σ = {jev_sum.get('max_sigma'):.3f}; "
            f"fraction with σ < 2 = {jev_sum.get('frac_sigma_lt_2'):.3f}."
        )
    if haiku_sum:
        lines.append(
            f"Haiku stop: `{haiku_sum.get('stop_reason')}`; "
            f"max σ = {haiku_sum.get('max_sigma'):.3f}; "
            f"fraction with σ < 2 = {haiku_sum.get('frac_sigma_lt_2'):.3f}."
        )
    lines.append("")
    lines.append("## 4. Interpretation")
    lines.append("")
    lines.append(
        "Spearman / Kendall concordance between Jev and Haiku, under a shared "
        "FedLock-style protocol, measures whether two different live judges produce a "
        "stable relative-hawkishness ordering on this openings sample. Concordance with "
        "published FedLock `m` / `ma` asks whether that same protocol family, applied to "
        "chair openings rather than FedLock’s broader speech corpus and Llama 3.3 70B "
        "judge, recovers a similar ordering of meeting-day stance. Era-adjusted `ma` "
        "removes quarterly means; disagreement between the `m` and `ma` contrasts "
        "therefore partly reflects era composition of the 2011–2026 openings window."
    )
    lines.append("")
    lines.append(
        "Cost and latency columns are accounting facts at the listed prices above. "
        "They are not accuracy claims and are not a gate. This replica does not replace "
        "Gate 7. See [`results/fedlock_fidelity.md`](results/fedlock_fidelity.md) "
        "and ANALYSIS §6."
    )
    lines.append("")
    lines.append("## 5. Limitations")
    lines.append("")
    lines.append(
        "- **Scale.** FedLock reports ~60,000 comparisons on ~4,000 speeches; this run "
        "uses the openings corpus with a 2,850-comparison cap. Convergence to σ < 2 for "
        "every document is not guaranteed at this scale."
    )
    lines.append(
        "- **Document mismatch.** Openings are a subset of press-conference communication; "
        "FedLock `press_conference` scores may reflect fuller presser text."
    )
    lines.append(
        "- **Judge stack.** FedLock’s published scores use Llama 3.3 70B; this replica "
        "uses Jev and Haiku. Agreement with `m` / `ma` mixes protocol fidelity and model "
        "differences."
    )
    lines.append(
        "- **Soft TrueSkill.** Confidence-weighted updates via outcome interpolation are "
        "an approximation to FedLock’s documented “updates by judge confidence,” not a "
        "bit-exact unpublished kernel."
    )
    lines.append(
        "- **Macro vintage.** FRED series are taken as-of the speech date from the local "
        "dump (plus downloaded VIXCLS / GDPC1). Real-time vintages differ from revised "
        "series."
    )
    lines.append("")
    lines.append("## 6. Artifacts")
    lines.append("")
    lines.append("- `results/fedlock_replica/trueskill_{jev,haiku}.csv`")
    lines.append("- `results/fedlock_replica/comparisons_{jev,haiku}.jsonl`")
    lines.append("- `results/fedlock_replica/cost_performance.json`")
    lines.append("- `results/fedlock_replica/agreement.json`")
    lines.append("- `results/fedlock_replica/fedlock_matches.json`")
    lines.append("- `results/fedlock_replica/macro_asof.json`")
    lines.append(
        "- `results/figures/fedlock_replica_*.png` when the replica plotting path is run "
        "(copied to `docs/figures/`)"
    )
    lines.append("")

    path.write_text("\n".join(lines) + "\n")
    return path


def analyze_only(stmts, macros, fedlock) -> None:
    jev_csv = OUT_DIR / "trueskill_jev.csv"
    haiku_csv = OUT_DIR / "trueskill_haiku.csv"
    # Rebuild summaries from comparison logs if present
    def summary_from_log(arm: str) -> dict | None:
        p = OUT_DIR / f"comparisons_{arm}.jsonl"
        csv_p = OUT_DIR / f"trueskill_{arm}.csv"
        if not p.exists() or not csv_p.exists():
            return None
        comps = [json.loads(l) for l in p.open() if l.strip()]
        live = [c for c in comps if not c.get("cache_hit")]
        # recount tokens from live only for spend; but total tokens for accounting =
        # sum of all non-cache rows' tokens (cache hits have tokens recorded as prior)
        in_tok = sum(c.get("input_tokens", 0) for c in comps if not c.get("cache_hit"))
        out_tok = sum(c.get("output_tokens", 0) for c in comps if not c.get("cache_hit"))
        if arm == "jev":
            usd = in_tok * JEV_PRICE_IN / 1e6
        else:
            usd = in_tok * HAIKU_PRICE_IN / 1e6 + out_tok * HAIKU_PRICE_OUT / 1e6
        df = pd.read_csv(csv_p)
        lats = [float(c["latency_ms"]) for c in comps if not c.get("cache_hit") and c.get("latency_ms")]
        return {
            "arm": arm,
            "n_comps": len(comps),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "usd": usd,
            "latencies_ms": lats,
            "wall_seconds": None,
            "stop_reason": "from_log",
            "max_sigma": float(df["sigma"].max()),
            "mean_sigma": float(df["sigma"].mean()),
            "frac_sigma_lt_2": float((df["sigma"] < SIGMA_STOP).mean()),
        }

    jev_sum = summary_from_log("jev")
    haiku_sum = summary_from_log("haiku")
    # Prefer live wall from tournament_state if we just ran — handled by callers
    cost = build_cost_performance(jev_sum or {}, haiku_sum or {})
    (OUT_DIR / "cost_performance.json").write_text(json.dumps(cost, indent=2) + "\n")
    agreement = build_agreement(stmts, jev_csv, haiku_csv, fedlock)
    (OUT_DIR / "agreement.json").write_text(json.dumps(agreement, indent=2) + "\n")
    notes = [
        "Corpus is 95 chair openings (jsort-style), not FedLock’s ~4k-speech pool.",
        "Soft TrueSkill via outcome interpolation of rate_1vs1 under p_A / p_B.",
        "VIXCLS and GDPC1 downloaded into data/raw/fred/ for this experiment.",
    ]
    write_findings(agreement, cost, jev_sum, haiku_sum, fedlock, notes)
    paths = make_figures(stmts, jev_csv, haiku_csv, fedlock, cost)
    print(json.dumps({"agreement": agreement, "cost": cost, "figures": paths}, indent=2)[:3000])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["jev", "haiku", "both", "analyze"], default="both")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--max-comps", type=int, default=MAX_COMPS_TOTAL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=20260920)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_BASE.mkdir(parents=True, exist_ok=True)

    stmts = load_statements()
    print(f"loaded {len(stmts)} statements", flush=True)
    macros = load_macro_asof([s["date"] for s in stmts])
    # macro coverage check
    n_vix = sum(1 for m in macros.values() if "vix" in m)
    n_gdp = sum(1 for m in macros.values() if "gdp_growth" in m)
    print(f"macro: vix={n_vix}/{len(macros)} gdp={n_gdp}/{len(macros)}", flush=True)
    (OUT_DIR / "macro_asof.json").write_text(json.dumps(macros, indent=2) + "\n")

    fedlock = match_fedlock(stmts)
    print(f"fedlock matched {len(fedlock)}/{len(stmts)}", flush=True)
    (OUT_DIR / "fedlock_matches.json").write_text(json.dumps(fedlock, indent=2) + "\n")

    jev_sum = haiku_sum = None

    if args.arm in ("jev", "both"):
        jev_sum = run_arm(
            "jev", stmts, macros,
            concurrency=args.concurrency, seed=args.seed,
            dry_run=args.dry_run, max_comps=args.max_comps,
        )
        print(f"[jev] done: comps={jev_sum['n_comps']} usd={jev_sum['usd']:.4f} "
              f"stop={jev_sum['stop_reason']}", flush=True)

    if args.arm in ("haiku", "both"):
        haiku_sum = run_arm(
            "haiku", stmts, macros,
            concurrency=min(args.concurrency, 8), seed=args.seed + 1,
            dry_run=args.dry_run, max_comps=args.max_comps,
        )
        print(f"[haiku] done: comps={haiku_sum['n_comps']} usd={haiku_sum['usd']:.4f} "
              f"stop={haiku_sum['stop_reason']}", flush=True)

    # Always analyze at end
    # Merge wall times into summaries written from logs
    analyze_only(stmts, macros, fedlock)

    # If we have live sums, overwrite cost with wall-aware stats
    if jev_sum or haiku_sum:
        # re-read log-based and patch wall
        cost_path = OUT_DIR / "cost_performance.json"
        cost = json.loads(cost_path.read_text())
        if jev_sum:
            cost.setdefault("jev", {})
            cost["jev"]["wall_seconds"] = jev_sum["wall_seconds"]
            cost["jev"]["comps_per_second"] = (
                jev_sum["n_comps"] / jev_sum["wall_seconds"]
                if jev_sum["wall_seconds"] else None
            )
            cost["jev"]["stop_reason"] = jev_sum["stop_reason"]
            cost["jev"]["latency_ms"] = latency_stats(jev_sum.get("latencies_ms") or [])
            cost["jev"]["usd"] = jev_sum["usd"]
            cost["jev"]["input_tokens"] = jev_sum["input_tokens"]
            cost["jev"]["output_tokens"] = jev_sum["output_tokens"]
            cost["jev"]["n_comps"] = jev_sum["n_comps"]
            tot = jev_sum["input_tokens"] + jev_sum["output_tokens"]
            cost["jev"]["usd_per_mtok_effective"] = (
                jev_sum["usd"] / tot * 1e6 if tot else None
            )
            cost["jev"]["usd_per_comparison"] = (
                jev_sum["usd"] / jev_sum["n_comps"] if jev_sum["n_comps"] else None
            )
        if haiku_sum:
            cost.setdefault("haiku", {})
            cost["haiku"]["wall_seconds"] = haiku_sum["wall_seconds"]
            cost["haiku"]["comps_per_second"] = (
                haiku_sum["n_comps"] / haiku_sum["wall_seconds"]
                if haiku_sum["wall_seconds"] else None
            )
            cost["haiku"]["stop_reason"] = haiku_sum["stop_reason"]
            cost["haiku"]["latency_ms"] = latency_stats(haiku_sum.get("latencies_ms") or [])
            cost["haiku"]["usd"] = haiku_sum["usd"]
            cost["haiku"]["input_tokens"] = haiku_sum["input_tokens"]
            cost["haiku"]["output_tokens"] = haiku_sum["output_tokens"]
            cost["haiku"]["n_comps"] = haiku_sum["n_comps"]
            tot = haiku_sum["input_tokens"] + haiku_sum["output_tokens"]
            cost["haiku"]["usd_per_mtok_effective"] = (
                haiku_sum["usd"] / tot * 1e6 if tot else None
            )
            cost["haiku"]["usd_per_comparison"] = (
                haiku_sum["usd"] / haiku_sum["n_comps"] if haiku_sum["n_comps"] else None
            )
        cost_path.write_text(json.dumps(cost, indent=2) + "\n")
        # refresh FINDINGS with live stop reasons
        agreement = json.loads((OUT_DIR / "agreement.json").read_text())
        notes = [
            "Corpus is 95 chair openings (jsort-style), not FedLock’s ~4k-speech pool.",
            "Soft TrueSkill via outcome interpolation of rate_1vs1 under p_A / p_B.",
            "VIXCLS and GDPC1 downloaded into data/raw/fred/ for this experiment.",
        ]
        write_findings(agreement, cost, jev_sum, haiku_sum, fedlock, notes)
        make_figures(
            stmts,
            OUT_DIR / "trueskill_jev.csv",
            OUT_DIR / "trueskill_haiku.csv",
            fedlock,
            cost,
        )

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
