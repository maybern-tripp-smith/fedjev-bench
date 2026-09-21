#!/usr/bin/env python3
"""Multi-axis TrueSkill extension on chair openings (Jev only).

run_id: fedjev-multiaxis-2026-09-20

Seven frozen criteria x two designs (text-only, conditional macro).
Adaptive TrueSkill (~sigma<2) with Choice (random presentation order
per pair, matching run_fedlock_replica.py). Paragraph filter via jgrep --para
before each axis tournament. Budget target ~$2-3; hard abort if projected >$5.

Prepared openings only — Q&A drift out of scope (not vendored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import trueskill

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from load_typesafe_env import ensure as ensure_typesafe_key  # noqa: E402
from strip_meta import strip_meta  # noqa: E402

RUN_ID = "fedjev-multiaxis-2026-09-20"
JEV_MODEL = "jev-latest"
JEV_PRICE_IN = 0.042
MU0 = 50.0
SIGMA0 = 8.33
SIGMA_STOP = 2.0
MAX_COMPS_PER_DOC = 30
MAX_COMPS_TOTAL = 1200
USD_HARD_CAP = 5.0
USD_TARGET = 3.0
MAX_CHARS = 8000
FILTER_BUDGET_PER_DOC = 0.02
SEED = 20260920
CONCURRENCY = 8

OUT_DIR = ROOT / "results" / "multiaxis"
FIG_DIR = ROOT / "results" / "figures"
DOC_FIG = ROOT / "docs" / "figures"
RUN_BASE = ROOT / "runs" / "multiaxis"
PDF_DIR = ROOT / "data" / "raw" / "jsort" / "pdfs"
PDF_DIR_ALT = Path("/workspace/fedjev-bench/data/raw/jsort/pdfs")
LABELS_DIR = ROOT / "data" / "labels"

AXES: list[dict[str, str]] = [
    {
        "id": "ax1_inflation_hawkish",
        "short": "inflation hawkish",
        "criterion": "more hawkish about inflation",
        "filter": "states a view on inflation, price stability, or inflationary pressures",
        "role": "baseline",
    },
    {
        "id": "ax2_emp_vs_infl",
        "short": "employment downside weight",
        "criterion": "places more weight on employment downside than on inflation upside",
        "filter": "states a view comparing employment or labor-market downside risks with inflation upside risks, or the relative weight on the dual mandate",
        "role": "alternative",
    },
    {
        "id": "ax3_lookthrough",
        "short": "look-through supply",
        "criterion": "more willing to treat a price-level shift from tariffs, energy, or supply as transitory and look through it",
        "filter": "states a view on tariffs, energy prices, supply shocks, transitory price-level shifts, or looking through temporary inflation",
        "role": "alternative",
    },
    {
        "id": "ax4_forward_path",
        "short": "forward guidance path",
        "criterion": "more explicit about the likely future path of policy; less purely data-dependent",
        "filter": "states a view on forward guidance, the likely future path of policy, or data-dependence of policy",
        "role": "alternative",
    },
    {
        "id": "ax5_qt_eager",
        "short": "QT / balance sheet eager",
        "criterion": "more eager to shrink the balance sheet and less worried that QT will impair reserves or market function",
        "filter": "states a view on quantitative tightening, balance-sheet runoff, securities holdings, reserves, or market function related to the balance sheet",
        "role": "alternative",
    },
    {
        "id": "ax6_fci_restrictive",
        "short": "FCI not restrictive enough",
        "criterion": "more concerned that financial conditions are not restrictive enough, rather than worried they will overshoot",
        "filter": "states a view on financial conditions, restrictiveness of policy, or whether conditions may overshoot",
        "role": "alternative",
    },
    {
        "id": "ax7_infl_vs_labor_risk",
        "short": "inflation upside > labor downside",
        "criterion": "sees upside inflation risks as larger than downside labor-market risks",
        "filter": "states a view on the balance of upside inflation risks versus downside labor-market or employment risks",
        "role": "alternative",
    },
]

DESIGNS = ("text", "conditional")

FURNITURE = re.compile(
    r"^(Page \d+ of \d+|PRELIMINARY|FINAL|[A-Z][a-z]+ \d{1,2}, \d{4}|"
    r"(Transcript of )?Chair\w* \w+[\'']s Press Conference|\d+\s+of\s+\d+)$"
)
SPEAKER = re.compile(r"^((?:[A-Z][A-Z\'\'\-]+\.? ){1,3}[A-Z][A-Z\'\'\-]+)[.:] ")

_write_lock = threading.Lock()
_spend_lock = threading.Lock()
_spend = {"usd": 0.0, "in": 0, "out": 0, "filter_usd": 0.0, "choice_usd": 0.0}


def bump(kind: str, in_tok: int, out_tok: int = 0) -> float:
    with _spend_lock:
        cost = in_tok * JEV_PRICE_IN / 1e6
        _spend["in"] += in_tok
        _spend["out"] += out_tok
        _spend["usd"] += cost
        _spend[kind] = _spend.get(kind, 0.0) + cost
        return _spend["usd"]


def total_usd() -> float:
    with _spend_lock:
        return float(_spend["usd"])


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

def pdf_path_for_date(date: str) -> Path:
    day = date.replace("-", "")
    for base in (PDF_DIR, PDF_DIR_ALT):
        p = base / f"{day}.pdf"
        if p.exists():
            return p
    raise FileNotFoundError(f"No PDF for {date}")


def opening_paragraphs(date: str) -> list[str]:
    pdf = pdf_path_for_date(date)
    raw = subprocess.check_output(
        ["pdftotext", str(pdf), "-"], text=True, errors="replace"
    )
    raw_lines = raw.splitlines()
    lines = [l.strip() for l in raw_lines]
    start = next(
        i
        for i, l in enumerate(lines)
        if (m := SPEAKER.match(l)) and m.group(1).startswith("CHAIR")
    )
    end = next(
        (i for i in range(start + 1, len(lines)) if SPEAKER.match(lines[i])),
        len(lines),
    )
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
    return [p for p in paras if len(p) >= 40]


def load_statements() -> list[dict[str, Any]]:
    rows = []
    for line in (ROOT / "data/clean/statements.jsonl").open():
        d = json.loads(line)
        raw = d.get("raw_text") or d.get("text") or ""
        stripped = strip_meta(raw) or strip_meta(d.get("text") or "")
        rows.append({
            "doc_id": d["doc_id"],
            "date": d["date"],
            "stripped_full": stripped,
            "chair_meta": d.get("chair"),
            "words": d.get("words"),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _asof(df: pd.DataFrame, value_col: str, dt: pd.Timestamp):
    sub = df[df["observation_date"] <= dt]
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    val = row[value_col]
    if pd.isna(val):
        return None, None
    return float(val), str(row["observation_date"].date())


def load_macro_asof(dates: list[str]) -> dict[str, dict[str, Any]]:
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
    gdp["gdp_qoq_saar"] = ((gdp["GDPC1"] / gdp["GDPC1"].shift(1)) ** 4 - 1.0) * 100.0

    vix = pd.read_csv(ROOT / "data/raw/fred/VIXCLS.csv")
    vix["observation_date"] = pd.to_datetime(vix["observation_date"])
    vix["VIXCLS"] = pd.to_numeric(vix["VIXCLS"], errors="coerce")
    vix = vix.dropna(subset=["VIXCLS"]).sort_values("observation_date")

    nfci_path = ROOT / "data/raw/fred/NFCI.csv"
    if nfci_path.exists():
        nfci = pd.read_csv(nfci_path)
        nfci["observation_date"] = pd.to_datetime(nfci["observation_date"])
        nfci["NFCI"] = pd.to_numeric(nfci["NFCI"], errors="coerce")
        nfci = nfci.dropna(subset=["NFCI"]).sort_values("observation_date")
    else:
        nfci = None

    out: dict[str, dict[str, Any]] = {}
    for date_str in dates:
        dt = pd.Timestamp(date_str)
        macro: dict[str, Any] = {"asof_date": date_str}
        pce_row = pce[pce["observation_date"] <= dt].tail(1)
        if len(pce_row) and pd.notna(pce_row["pce_yoy"].iloc[0]):
            macro["core_pce_yoy"] = round(float(pce_row["pce_yoy"].iloc[0]), 3)
            macro["core_pce_obs_date"] = str(pce_row["observation_date"].iloc[0].date())
        un_val, un_obs = _asof(unrate, "UNRATE", dt)
        if un_val is not None:
            macro["unrate"] = un_val
            macro["unrate_obs_date"] = un_obs
        gdp_row = gdp[gdp["observation_date"] <= dt].tail(1)
        if len(gdp_row) and pd.notna(gdp_row["gdp_qoq_saar"].iloc[0]):
            macro["gdp_growth_qoq_saar"] = round(float(gdp_row["gdp_qoq_saar"].iloc[0]), 3)
            macro["gdp_obs_date"] = str(gdp_row["observation_date"].iloc[0].date())
        v_val, v_obs = _asof(vix, "VIXCLS", dt)
        if v_val is not None:
            macro["vix"] = round(v_val, 3)
            macro["vix_obs_date"] = v_obs
        if nfci is not None:
            n_val, n_obs = _asof(nfci, "NFCI", dt)
            if n_val is not None:
                macro["nfci"] = round(n_val, 4)
                macro["nfci_obs_date"] = n_obs
        out[date_str] = macro
    return out


def compact_macro(m: dict[str, Any]) -> dict[str, Any]:
    keys = ["asof_date", "core_pce_yoy", "unrate", "gdp_growth_qoq_saar", "vix", "nfci"]
    return {k: m[k] for k in keys if k in m and m[k] is not None}


def build_meeting_labels(stmts: list[dict]) -> pd.DataFrame:
    meet = pd.read_csv(ROOT / "data/labels/meetings.csv")
    meet["date"] = meet["date"].astype(str)
    dgs2 = pd.read_csv(ROOT / "data/raw/fred/DGS2.csv")
    dgs2["observation_date"] = pd.to_datetime(dgs2["observation_date"])
    dgs2["DGS2"] = pd.to_numeric(dgs2["DGS2"], errors="coerce")
    dgs2 = dgs2.dropna().sort_values("observation_date")

    usd_path = ROOT / "data/raw/fred/DTWEXBGS.csv"
    usd = None
    if usd_path.exists():
        usd = pd.read_csv(usd_path)
        usd["observation_date"] = pd.to_datetime(usd["observation_date"])
        usd["DTWEXBGS"] = pd.to_numeric(usd["DTWEXBGS"], errors="coerce")
        usd = usd.dropna().sort_values("observation_date")

    nfci_path = ROOT / "data/raw/fred/NFCI.csv"
    nfci = None
    if nfci_path.exists():
        nfci = pd.read_csv(nfci_path)
        nfci["observation_date"] = pd.to_datetime(nfci["observation_date"])
        nfci["NFCI"] = pd.to_numeric(nfci["NFCI"], errors="coerce")
        nfci = nfci.dropna().sort_values("observation_date")

    rows = []
    for s in stmts:
        dt = pd.Timestamp(s["date"])
        mrow = meet[meet["date"] == s["date"]]
        base = {
            "doc_id": s["doc_id"],
            "date": s["date"],
            "d_same": float(mrow["d_same"].iloc[0]) if len(mrow) else np.nan,
            "y_action": int(mrow["y_action"].iloc[0]) if len(mrow) else 0,
            "d_2y": float(mrow["d_2y"].iloc[0]) if len(mrow) else np.nan,
            "is_scheduled": bool(mrow["is_scheduled"].iloc[0]) if len(mrow) else True,
            "exclude_main": bool(mrow["exclude_main"].iloc[0]) if len(mrow) else False,
            "flag_svb": bool(mrow["flag_svb"].iloc[0]) if len(mrow) else False,
            "is_sep": bool(mrow["is_sep"].iloc[0]) if len(mrow) else False,
            "chair": mrow["chair"].iloc[0] if len(mrow) else s.get("chair_meta"),
        }
        sub = dgs2[dgs2["observation_date"] <= dt]
        if len(sub) >= 2:
            base["dgs2_level"] = float(sub.iloc[-1]["DGS2"])
            base["dgs2_day_chg"] = float(sub.iloc[-1]["DGS2"] - sub.iloc[-2]["DGS2"])
        else:
            base["dgs2_level"] = np.nan
            base["dgs2_day_chg"] = np.nan
        if usd is not None:
            usub = usd[usd["observation_date"] <= dt]
            base["usd_day_chg"] = (
                float(usub.iloc[-1]["DTWEXBGS"] - usub.iloc[-2]["DTWEXBGS"])
                if len(usub) >= 2 else np.nan
            )
        else:
            base["usd_day_chg"] = np.nan
        if nfci is not None:
            nsub = nfci[nfci["observation_date"] <= dt]
            if len(nsub) >= 2:
                base["nfci_week_chg"] = float(nsub.iloc[-1]["NFCI"] - nsub.iloc[-2]["NFCI"])
                base["nfci_level"] = float(nsub.iloc[-1]["NFCI"])
            else:
                base["nfci_week_chg"] = np.nan
                base["nfci_level"] = np.nan
        else:
            base["nfci_week_chg"] = np.nan
            base["nfci_level"] = np.nan
        ds = base["d_same"]
        if pd.isna(ds):
            base["action"] = "unknown"
        elif ds > 0:
            base["action"] = "hike"
        elif ds < 0:
            base["action"] = "cut"
        else:
            base["action"] = "hold"
        rows.append(base)
    df = pd.DataFrame(rows)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(LABELS_DIR / "multiaxis_meeting_context.csv", index=False)
    return df

def jgrep_available() -> bool:
    from shutil import which
    return which("jgrep") is not None


def filter_paras_jgrep(paras: list[str], criterion: str, *, budget: float = FILTER_BUDGET_PER_DOC):
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n\n".join(paras) + "\n")
        tmp = f.name
    try:
        cmd = [
            "jgrep", "--para", "-p", "0.5",
            "--budget", str(budget),
            "--max-chars", str(MAX_CHARS),
            criterion, tmp,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=os.environ.copy(), timeout=300
        )
        kept = [p.strip() for p in re.split(r"\n\s*\n", proc.stdout) if p.strip()]
        est_in = max(1, sum(len(p) for p in paras) // 4)
        bump("filter_usd", est_in, 0)
        meta = {
            "method": "jgrep --para",
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-400:],
            "n_in": len(paras),
            "n_kept": len(kept),
            "est_input_chars": sum(len(p) for p in paras),
        }
        return kept, meta
    finally:
        Path(tmp).unlink(missing_ok=True)


def lexical_fallback(paras: list[str], axis_id: str):
    patterns = {
        "ax1_inflation_hawkish": r"\b(inflation|price\s+stabilit|PCE|CPI|price\s+pressures?)\b",
        "ax2_emp_vs_infl": r"\b(employment|labor|unemployment|mandate|inflation)\b",
        "ax3_lookthrough": r"\b(tariff|energy|supply|transitory|look\s+through|temporary)\b",
        "ax4_forward_path": r"\b(forward\s+guidance|data[- ]dependent|policy\s+path|appropriate)\b",
        "ax5_qt_eager": r"\b(balance\s+sheet|runoff|securities\s+holdings|reserves|QT|quantitative)\b",
        "ax6_fci_restrictive": r"\b(financial\s+conditions|restrictive|accommodation|overshoot)\b",
        "ax7_infl_vs_labor_risk": r"\b(risks?|upside|downside|inflation|labor|employment)\b",
    }
    rx = re.compile(patterns.get(axis_id, r"\binflation\b"), re.I)
    kept = [p for p in paras if rx.search(p)]
    return kept, {"method": "python_regex_fallback", "n_in": len(paras), "n_kept": len(kept)}


def prepare_filtered_corpus(stmts: list[dict], *, force: bool = False, axes_subset=None) -> dict[str, Any]:
    cache_path = OUT_DIR / "filtered_passages.json"
    if cache_path.exists() and not force:
        print(f"[filter] loading cached {cache_path}", flush=True)
        return json.loads(cache_path.read_text())

    use_jgrep = jgrep_available()
    print(f"[filter] jgrep={use_jgrep}; n_docs={len(stmts)}; n_axes={len(AXES)}", flush=True)

    para_by_doc: dict[str, list[str]] = {}
    for i, s in enumerate(stmts):
        try:
            paras = opening_paragraphs(s["date"])
        except Exception as e:
            print(f"[filter] PDF fail {s['date']}: {e}; text split fallback", flush=True)
            text = s["stripped_full"]
            chunks = re.split(r"(?<=\.)\s+(?=[A-Z])", text)
            paras, buf = [], []
            for c in chunks:
                buf.append(c)
                if sum(len(x) for x in buf) > 400:
                    paras.append(" ".join(buf))
                    buf = []
            if buf:
                paras.append(" ".join(buf))
        para_by_doc[s["doc_id"]] = paras
        if (i + 1) % 20 == 0:
            print(f"[filter] extracted paras {i+1}/{len(stmts)}", flush=True)

    result: dict[str, Any] = {
        "run_id": RUN_ID,
        "max_chars": MAX_CHARS,
        "axes": {},
        "notes": [
            "Openings only (prepared remarks). Q&A drift out of scope — not vendored.",
            "Full-speech robustness: future work (not present in this run).",
        ],
    }

    axes_run = AXES if not axes_subset else [a for a in AXES if a["id"] in axes_subset]
    for ax in axes_run:
        ax_id = ax["id"]
        print(f"[filter] axis {ax_id}", flush=True)
        docs = {}
        empty = 0

        def _filter_one(s):
            paras = para_by_doc[s["doc_id"]]
            if use_jgrep:
                kept, meta = filter_paras_jgrep(paras, ax["filter"])
            else:
                kept, meta = lexical_fallback(paras, ax_id)
            filter_empty = len(kept) == 0
            if filter_empty:
                passage = s["stripped_full"][:MAX_CHARS]
            else:
                passage = strip_meta("\n\n".join(kept))[:MAX_CHARS]
            return s["doc_id"], {
                "date": s["date"],
                "n_paras_in": meta.get("n_in"),
                "n_paras_kept": meta.get("n_kept", len(kept)),
                "filter_empty": filter_empty,
                "method": meta.get("method"),
                "passage_chars": len(passage),
                "passage_hash": text_hash(passage),
                "passage": passage,
            }

        with ThreadPoolExecutor(max_workers=12) as ex:
            futs = [ex.submit(_filter_one, s) for s in stmts]
            for fut in as_completed(futs):
                doc_id, rec = fut.result()
                docs[doc_id] = rec
                if rec["filter_empty"]:
                    empty += 1

        result["axes"][ax_id] = {
            "criterion": ax["criterion"],
            "filter": ax["filter"],
            "role": ax["role"],
            "n_empty": empty,
            "docs": docs,
        }
        print(f"[filter] {ax_id}: empty={empty}/{len(stmts)}; usd≈{total_usd():.4f}", flush=True)
        if total_usd() > USD_HARD_CAP:
            raise RuntimeError(f"Hard cap ${USD_HARD_CAP} hit during filter")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    slim = {
        "run_id": RUN_ID,
        "notes": result["notes"],
        "axes": {
            ax_id: {
                "criterion": v["criterion"],
                "filter": v["filter"],
                "role": v["role"],
                "n_empty": v["n_empty"],
                "n_docs": len(v["docs"]),
                "empty_doc_ids": [d for d, x in v["docs"].items() if x["filter_empty"]],
                "mean_kept": float(np.mean([x["n_paras_kept"] or 0 for x in v["docs"].values()])),
                "mean_chars": float(np.mean([x["passage_chars"] for x in v["docs"].values()])),
            }
            for ax_id, v in result["axes"].items()
        },
    }
    (OUT_DIR / "filter_summary.json").write_text(json.dumps(slim, indent=2))
    return result


def make_env() -> trueskill.TrueSkill:
    return trueskill.TrueSkill(
        mu=MU0, sigma=SIGMA0, beta=SIGMA0 / 2.0, tau=SIGMA0 / 100.0, draw_probability=0.02
    )


def soft_rate(env, r_a, r_b, p_a_wins):
    p = float(np.clip(p_a_wins, 0.0, 1.0))
    ra_w, rb_l = env.rate_1vs1(r_a, r_b)
    rb_w, ra_l = env.rate_1vs1(r_b, r_a)
    mu_a = p * ra_w.mu + (1.0 - p) * ra_l.mu
    sig_a = p * ra_w.sigma + (1.0 - p) * ra_l.sigma
    mu_b = p * rb_l.mu + (1.0 - p) * rb_w.mu
    sig_b = p * rb_l.sigma + (1.0 - p) * rb_w.sigma
    return env.create_rating(mu_a, max(sig_a, 0.01)), env.create_rating(mu_b, max(sig_b, 0.01))


def pair_key(a: str, b: str):
    return (a, b) if a < b else (b, a)


def select_round_pairs(doc_ids, ratings, n_comps, pair_counts, rng, max_pair_repeats=2):
    eligible = [d for d in doc_ids if n_comps[d] < MAX_COMPS_PER_DOC]
    if len(eligible) < 2:
        return []
    unpaired = set(eligible)
    pairs = []
    while len(unpaired) >= 2:
        anchor = max(unpaired, key=lambda d: (ratings[d].sigma, rng.random()))
        unpaired.remove(anchor)
        cands = []
        for o in unpaired:
            pk = pair_key(anchor, o)
            if pair_counts.get(pk, 0) >= max_pair_repeats:
                continue
            dmu = abs(ratings[anchor].mu - ratings[o].mu)
            cands.append((dmu, -ratings[o].sigma, rng.random(), o))
        if not cands:
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


def converged(ratings, n_comps):
    if any(n_comps[d] < 1 for d in ratings):
        return False
    return all(r.sigma < SIGMA_STOP for r in ratings.values())


def make_jev_client():
    from typesafe_sdk import TypeSafeClient, RetryPolicy
    return TypeSafeClient(
        retry=RetryPolicy(
            max_retries=5, backoff_initial=0.5, backoff_max=30.0,
            http_statuses={408, 429, 500, 502, 503, 504, 529}, timeout=180.0,
        ),
        timeout=180.0,
    )


def judge_instructions(criterion: str, design: str) -> str:
    if design == "conditional":
        return (
            f"Which of Text A or Text B is higher on this axis relative to the "
            f"macroeconomic conditions provided for each text "
            f"(Core PCE year-over-year inflation, unemployment rate, real GDP growth, "
            f"VIX, and Chicago Fed National Financial Conditions Index where available): "
            f"{criterion}. "
            f"Judge relative to conditions at each speech's time — not absolute language alone."
        )
    return (
        f"Which of Text A or Text B is higher on this axis (text only; no macro context): "
        f"{criterion}."
    )


def call_jev(client, *, text_a, text_b, criterion, design, macro_a=None, macro_b=None):
    from typesafe_sdk import Choice
    state: dict[str, Any] = {"Text A": text_a, "Text B": text_b}
    if design == "conditional":
        state["macro_A"] = macro_a or {}
        state["macro_B"] = macro_b or {}
    t0 = time.perf_counter()
    response = client.system_one(
        model=JEV_MODEL,
        state=state,
        questions={
            "winner": Choice(
                instructions=judge_instructions(criterion, design),
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


def cache_key_for(axis_id, design, id_a, id_b, order, criterion, macro_a, macro_b, th_a, th_b):
    blob = json.dumps({
        "axis": axis_id, "design": design, "crit": criterion,
        "A": id_a, "B": id_b, "order": order,
        "thA": th_a, "thB": th_b,
        "mA": macro_a, "mB": macro_b,
        "run": RUN_ID,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()

def run_tournament(axis, design, filtered, macros, *, dry_run=False, concurrency=CONCURRENCY):
    ax_id = axis["id"]
    criterion = axis["criterion"]
    docs_meta = filtered["axes"][ax_id]["docs"]
    doc_ids = sorted(docs_meta.keys(), key=lambda d: docs_meta[d]["date"])
    by_id = {d: docs_meta[d] for d in doc_ids}

    tag = f"{ax_id}__{design}"
    cache_dir = RUN_BASE / tag / "cache"
    comps_path = OUT_DIR / "comparisons" / f"{tag}.jsonl"
    state_path = RUN_BASE / tag / "tournament_state.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    comps_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED + hash(tag) % 10_000)
    env = make_env()
    ratings = {d: env.create_rating(MU0, SIGMA0) for d in doc_ids}
    n_comps = {d: 0 for d in doc_ids}
    pair_counts = {}

    prior = []
    if comps_path.exists():
        for line in comps_path.open():
            if line.strip():
                prior.append(json.loads(line))
        print(f"[{tag}] resume {len(prior)} comps", flush=True)
        for c in prior:
            da, db = c["doc_id_a"], c["doc_id_b"]
            p = float(c.get("p_doc_a_wins", c["p_A"]))
            ratings[da], ratings[db] = soft_rate(env, ratings[da], ratings[db], p)
            n_comps[da] += 1
            n_comps[db] += 1
            pk = pair_key(da, db)
            pair_counts[pk] = pair_counts.get(pk, 0) + 1
            if not c.get("cache_hit"):
                bump("choice_usd", int(c.get("input_tokens") or 0), int(c.get("output_tokens") or 0))

    if not ensure_typesafe_key() and not dry_run:
        raise RuntimeError("TYPESAFE_API_KEY missing")
    client = None if dry_run else make_jev_client()

    total_comps = sum(n_comps.values()) // 2
    round_idx = 0
    latencies = []
    near_half = 0
    t0 = time.perf_counter()
    stop_reason = None

    if total_usd() > USD_HARD_CAP:
        return {"tag": tag, "stop_reason": "hard_cap", "n_comps": total_comps, "usd": total_usd()}

    while total_comps < MAX_COMPS_TOTAL and not converged(ratings, n_comps):
        if total_usd() > USD_HARD_CAP:
            stop_reason = "hard_cap"
            break
        pairs = select_round_pairs(doc_ids, ratings, n_comps, pair_counts, rng)
        if not pairs:
            stop_reason = "no_eligible_pairs"
            break
        remaining = MAX_COMPS_TOTAL - total_comps
        if len(pairs) > remaining:
            pairs = pairs[:remaining]

        round_idx += 1
        print(
            f"[{tag}] round {round_idx}: {len(pairs)} pairs; comps={total_comps}; "
            f"max_sigma={max(r.sigma for r in ratings.values()):.3f}; usd≈{total_usd():.4f}",
            flush=True,
        )

        jobs = []
        for da, db in pairs:
            order = "ab" if rng.random() < 0.5 else "ba"
            id_disp_a, id_disp_b = (da, db) if order == "ab" else (db, da)
            ma = compact_macro(macros.get(by_id[id_disp_a]["date"], {})) if design == "conditional" else {}
            mb = compact_macro(macros.get(by_id[id_disp_b]["date"], {})) if design == "conditional" else {}
            th_a = by_id[id_disp_a]["passage_hash"]
            th_b = by_id[id_disp_b]["passage_hash"]
            key = cache_key_for(ax_id, design, id_disp_a, id_disp_b, order, criterion, ma, mb, th_a, th_b)
            jobs.append({
                "doc_id_a": da, "doc_id_b": db,
                "id_disp_a": id_disp_a, "id_disp_b": id_disp_b,
                "order": order, "macro_disp_a": ma, "macro_disp_b": mb,
                "cache_key": key,
                "text_a": by_id[id_disp_a]["passage"],
                "text_b": by_id[id_disp_b]["passage"],
            })

        def run_one(job):
            cached = read_cache(cache_dir, job["cache_key"])
            if cached and cached.get("ok"):
                return {**job, **cached, "cache_hit": True, "ok": True}
            if dry_run:
                h = int(job["cache_key"][:8], 16)
                p = 0.35 + (h % 31) / 100.0
                return {
                    **job, "ok": True, "cache_hit": False, "dry_run": True,
                    "winner": "A" if p >= 0.5 else "B",
                    "p_A": p, "p_B": 1 - p, "confidence": abs(p - 0.5) * 2,
                    "input_tokens": 800, "output_tokens": 20, "latency_ms": 5,
                    "model": "dry-run",
                }
            try:
                res = call_jev(
                    client,
                    text_a=job["text_a"], text_b=job["text_b"],
                    criterion=criterion, design=design,
                    macro_a=job["macro_disp_a"], macro_b=job["macro_disp_b"],
                )
                out = {**job, **res, "ok": True, "cache_hit": False}
                write_cache(cache_dir, job["cache_key"], {
                    "ok": True, "winner": res["winner"], "p_A": res["p_A"], "p_B": res["p_B"],
                    "confidence": res["confidence"],
                    "input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
                    "latency_ms": res["latency_ms"], "model": res["model"],
                })
                return out
            except Exception as e:
                return {**job, "ok": False, "error": repr(e), "cache_hit": False}

        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [ex.submit(run_one, j) for j in jobs]
            for fut in as_completed(futs):
                results.append(fut.result())

        for res in results:
            if not res.get("ok"):
                print(f"[{tag}] FAIL {res.get('error')}", flush=True)
                continue
            if res["id_disp_a"] == res["doc_id_a"]:
                p_doc_a = float(res["p_A"])
            else:
                p_doc_a = float(res["p_B"])
            if 0.45 <= p_doc_a <= 0.55:
                near_half += 1
            da, db = res["doc_id_a"], res["doc_id_b"]
            ratings[da], ratings[db] = soft_rate(env, ratings[da], ratings[db], p_doc_a)
            n_comps[da] += 1
            n_comps[db] += 1
            pair_counts[pair_key(da, db)] = pair_counts.get(pair_key(da, db), 0) + 1
            total_comps += 1
            in_tok = int(res.get("input_tokens") or 0)
            out_tok = int(res.get("output_tokens") or 0)
            lat = float(res.get("latency_ms") or 0)
            if not res.get("cache_hit"):
                usd = bump("choice_usd", in_tok, out_tok)
                latencies.append(lat)
            else:
                usd = total_usd()
            cost = 0.0 if res.get("cache_hit") else in_tok * JEV_PRICE_IN / 1e6
            append_jsonl(comps_path, {
                "run_id": RUN_ID, "axis": ax_id, "design": design,
                "round": round_idx, "doc_id_a": da, "doc_id_b": db,
                "date_a": by_id[da]["date"], "date_b": by_id[db]["date"],
                "order": res["order"], "id_disp_a": res["id_disp_a"], "id_disp_b": res["id_disp_b"],
                "macro_A": res.get("macro_disp_a"), "macro_B": res.get("macro_disp_b"),
                "winner_disp": res.get("winner"),
                "p_A": float(res.get("p_A", 0.5)), "p_B": float(res.get("p_B", 0.5)),
                "p_doc_a_wins": p_doc_a, "confidence": float(res.get("confidence", 0.5)),
                "model": res.get("model"), "input_tokens": in_tok, "output_tokens": out_tok,
                "latency_ms": lat, "cost_usd": cost, "cache_hit": bool(res.get("cache_hit")),
                "mu_a_after": ratings[da].mu, "sigma_a_after": ratings[da].sigma,
                "mu_b_after": ratings[db].mu, "sigma_b_after": ratings[db].sigma,
                "running_usd": usd,
            })

        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "tag": tag, "n_comps_total": total_comps, "n_comps": n_comps,
            "ratings": {d: {"mu": ratings[d].mu, "sigma": ratings[d].sigma} for d in doc_ids},
            "spend_usd": total_usd(),
        }, indent=2))

    if stop_reason is None:
        if converged(ratings, n_comps):
            stop_reason = "all_sigma_lt_2"
        elif total_comps >= MAX_COMPS_TOTAL:
            stop_reason = "max_comps"
        else:
            stop_reason = "loop_exit"

    rows = []
    for d in doc_ids:
        date = by_id[d]["date"]
        rows.append({
            "doc_id": d, "date": date, "mu": ratings[d].mu, "sigma": ratings[d].sigma,
            "n_comps": n_comps[d], "filter_empty": by_id[d]["filter_empty"],
            "passage_chars": by_id[d]["passage_chars"],
            "quarter": f"{date[:4]}Q{(int(date[5:7]) - 1) // 3 + 1}",
        })
    df = pd.DataFrame(rows)
    qmean = df.groupby("quarter")["mu"].transform("mean")
    df["mu_era_adj"] = df["mu"] - qmean
    df["mu_era_adj"] = df["mu_era_adj"] - df["mu_era_adj"].mean() + df["mu"].mean()
    df["percentile"] = df["mu"].rank(pct=True) * 100.0
    df["percentile_era"] = df["mu_era_adj"].rank(pct=True) * 100.0
    csv_path = OUT_DIR / "scores" / f"{tag}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)

    return {
        "tag": tag, "axis": ax_id, "design": design, "criterion": criterion,
        "stop_reason": stop_reason, "n_comps": total_comps, "n_docs": len(doc_ids),
        "wall_seconds": time.perf_counter() - t0,
        "usd_at_end": total_usd(),
        "max_sigma": max(r.sigma for r in ratings.values()),
        "mean_sigma": float(np.mean([r.sigma for r in ratings.values()])),
        "frac_sigma_lt_2": float(np.mean([r.sigma < SIGMA_STOP for r in ratings.values()])),
        "near_half_pairs": near_half,
        "latency_ms_mean": float(np.mean(latencies)) if latencies else None,
        "csv_path": str(csv_path),
        "comps_path": str(comps_path),
        "n_filter_empty": int(df["filter_empty"].sum()),
    }


def order_swap_check(filtered, macros, *, n_pairs=40, dry_run=False):
    ax = AXES[0]
    docs = filtered["axes"][ax["id"]]["docs"]
    ids = sorted(docs.keys(), key=lambda d: docs[d]["date"])
    rng = random.Random(SEED)
    pairs = [tuple(rng.sample(ids, 2)) for _ in range(n_pairs)]
    if not dry_run and not ensure_typesafe_key():
        raise RuntimeError("TYPESAFE_API_KEY missing")
    client = None if dry_run else make_jev_client()
    flips = 0
    abs_dp = []
    cache_dir = RUN_BASE / "order_swap" / "cache"
    for a, b in pairs:
        results = {}
        for order, (ia, ib) in [("ab", (a, b)), ("ba", (b, a))]:
            key = cache_key_for(
                ax["id"], "text", ia, ib, order, ax["criterion"], {}, {},
                docs[ia]["passage_hash"], docs[ib]["passage_hash"],
            )
            cached = read_cache(cache_dir, key)
            if cached and cached.get("ok"):
                results[order] = cached
                continue
            if dry_run:
                h = int(key[:8], 16)
                p = 0.4 + (h % 21) / 100.0
                results[order] = {"p_A": p, "p_B": 1 - p, "ok": True}
                continue
            res = call_jev(
                client, text_a=docs[ia]["passage"], text_b=docs[ib]["passage"],
                criterion=ax["criterion"], design="text",
            )
            bump("choice_usd", res["input_tokens"], res["output_tokens"])
            write_cache(cache_dir, key, {**res, "ok": True})
            results[order] = res
        p_ab = results["ab"]["p_A"]
        p_ba = results["ba"]["p_B"]
        if (p_ab >= 0.5) != (p_ba >= 0.5):
            flips += 1
        abs_dp.append(abs(p_ab - p_ba))
    out = {
        "n_pairs": n_pairs,
        "flip_rate": flips / n_pairs,
        "mean_abs_dp": float(np.mean(abs_dp)),
        "axis": ax["id"],
        "design": "text",
    }
    (OUT_DIR / "order_swap_check.json").write_text(json.dumps(out, indent=2))
    return out

CRISIS = {"2020-03-03", "2020-03-15"}


def bootstrap_spearman(x, y, n_boot=1000, seed=SEED):
    from scipy.stats import spearmanr
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return {"rho": None, "se": None, "ci_low": None, "ci_high": None, "n": n}
    rho, _ = spearmanr(x, y)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r, _ = spearmanr(x[idx], y[idx])
        if np.isfinite(r):
            boots.append(r)
    boots = np.asarray(boots)
    return {
        "rho": float(rho) if np.isfinite(rho) else None,
        "se": float(np.std(boots, ddof=1)) if len(boots) > 1 else None,
        "ci_low": float(np.percentile(boots, 2.5)) if len(boots) else None,
        "ci_high": float(np.percentile(boots, 97.5)) if len(boots) else None,
        "n": n,
    }


def analyze_all(labels: pd.DataFrame, tournament_summaries: list[dict]) -> dict:
    (OUT_DIR / "ranked").mkdir(parents=True, exist_ok=True)
    score_frames = {}
    for ax in AXES:
        for design in DESIGNS:
            tag = f"{ax['id']}__{design}"
            path = OUT_DIR / "scores" / f"{tag}.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path)
            df = df.merge(labels, on=["doc_id", "date"], how="left", suffixes=("", "_lab"))
            score_frames[tag] = df
            ranked = df.sort_values("mu", ascending=False).copy()
            cols = [
                "doc_id", "date", "mu", "mu_era_adj", "sigma", "percentile", "percentile_era",
                "n_comps", "action", "d_same", "d_2y", "dgs2_day_chg", "usd_day_chg",
                "nfci_week_chg", "filter_empty",
            ]
            cols = [c for c in cols if c in ranked.columns]
            ranked[cols].to_csv(OUT_DIR / "ranked" / f"{tag}.csv", index=False)

    factor_out = {}
    for design in DESIGNS:
        mats, names, base_ids = [], [], None
        for ax in AXES:
            tag = f"{ax['id']}__{design}"
            if tag not in score_frames:
                continue
            df = score_frames[tag].sort_values("doc_id")
            if base_ids is None:
                base_ids = df["doc_id"].tolist()
            mats.append(df.set_index("doc_id").loc[base_ids, "mu"].to_numpy())
            names.append(ax["id"])
        if not mats:
            continue
        M = np.vstack(mats).T
        corr = np.zeros((len(names), len(names)))
        for i in range(len(names)):
            for j in range(len(names)):
                r = bootstrap_spearman(M[:, i], M[:, j], n_boot=200)
                corr[i, j] = r["rho"] if r["rho"] is not None else np.nan
        X = (M - M.mean(0)) / (M.std(0) + 1e-9)
        U, S, Vt = np.linalg.svd(X, full_matrices=False)
        var_exp = (S ** 2) / (S ** 2).sum()
        pc1_axis = names[int(np.argmax(np.abs(Vt[0])))]
        factor_out[design] = {
            "axes": names,
            "corr": corr.tolist(),
            "var_explained": var_exp.tolist(),
            "loadings_Vt": Vt.tolist(),
            "pc1_dominant_axis": pc1_axis,
            "pc1_loadings": {names[i]: float(Vt[0, i]) for i in range(len(names))},
            "pc2_loadings": {names[i]: float(Vt[1, i]) for i in range(len(names))} if len(Vt) > 1 else {},
            "n_docs": len(base_ids),
        }
        pd.DataFrame(corr, index=names, columns=names).to_csv(OUT_DIR / f"corr_{design}.csv")
        pd.DataFrame(Vt.T, index=names, columns=[f"PC{i+1}" for i in range(len(names))]).to_csv(
            OUT_DIR / f"loadings_{design}.csv"
        )

    gates = {"pre_registered": True, "run_id": RUN_ID, "by_tag": {}}
    for tag, df in score_frames.items():
        main = df[
            df["is_scheduled"].fillna(True)
            & ~df["exclude_main"].fillna(False)
            & ~df["date"].isin(CRISIS)
        ].copy()
        action = main[main["d_same"].fillna(0) != 0]
        holds = main[main["d_same"] == 0]
        cuts = main[main["d_same"] < 0]
        g = {}
        g["d_same_action"] = bootstrap_spearman(action["mu"], action["d_same"])
        g["d_same_action_era"] = bootstrap_spearman(action["mu_era_adj"], action["d_same"])
        if len(holds) and len(cuts):
            gap = float(holds["mu"].mean() - cuts["mu"].mean())
            rng = np.random.default_rng(SEED)
            hmu, cmu = holds["mu"].to_numpy(), cuts["mu"].to_numpy()
            boots = [
                float(np.mean(rng.choice(hmu, len(hmu))) - np.mean(rng.choice(cmu, len(cmu))))
                for _ in range(1000)
            ]
            g["hold_vs_cut"] = {
                "gap": gap, "se": float(np.std(boots, ddof=1)),
                "mean_hold": float(holds["mu"].mean()), "mean_cut": float(cuts["mu"].mean()),
                "n_hold": len(holds), "n_cut": len(cuts), "pass": gap > 0,
            }
        else:
            g["hold_vs_cut"] = {"pass": None, "note": "insufficient holds/cuts"}
        g["d_2y_action"] = bootstrap_spearman(action["mu"], action["d_2y"])
        g["d_2y_holds"] = bootstrap_spearman(holds["mu"], holds["d_2y"]) if len(holds) else {"n": 0}
        if "dgs2_day_chg" in action.columns:
            g["dgs2_day_chg_action"] = bootstrap_spearman(action["mu"], action["dgs2_day_chg"])
        if "usd_day_chg" in action.columns and action["usd_day_chg"].notna().sum() >= 5:
            g["usd_day_chg_action"] = bootstrap_spearman(action["mu"], action["usd_day_chg"])
            g["usd_day_chg_holds"] = (
                bootstrap_spearman(holds["mu"], holds["usd_day_chg"]) if len(holds) else {"n": 0}
            )
        else:
            g["usd_note"] = "USD day-change sparse or missing"
        if "nfci_week_chg" in action.columns and action["nfci_week_chg"].notna().sum() >= 5:
            g["nfci_week_chg_action"] = bootstrap_spearman(action["mu"], action["nfci_week_chg"])
        else:
            g["fci_note"] = "NFCI weekly change used as FCI proxy; no market FCI surprise series vendored"
        g["sep_note"] = "Next-meeting SEP medians not vendored as a panel in this repo; skipped."
        if "ax5" in tag:
            g["qt_note"] = "No separate QT-pace numeric label in meetings.csv; axis-5 uses d_same / d_2y only."
        if tag.startswith("ax1_"):
            try:
                fl = json.loads((ROOT / "data/raw/fedlock/data.json").read_text())
                pcs = {s["d"]: s for s in fl["speeches"] if s.get("st") == "press_conference"}
                mus, ms = [], []
                for _, row in main.iterrows():
                    if row["date"] in pcs:
                        mus.append(row["mu"])
                        ms.append(float(pcs[row["date"]]["m"]))
                g["fedlock_m"] = bootstrap_spearman(mus, ms)
            except Exception as e:
                g["fedlock_m"] = {"error": repr(e)}
        rho = g["d_same_action"].get("rho")
        g["gate_d_same_pass"] = bool(rho is not None and rho >= 0.30)
        g["gate_hold_cut_pass"] = g.get("hold_vs_cut", {}).get("pass")
        gates["by_tag"][tag] = g

    redundancy = {}
    for design in DESIGNS:
        if design not in factor_out:
            continue
        names = factor_out[design]["axes"]
        corr = np.asarray(factor_out[design]["corr"])
        ax1_i = names.index("ax1_inflation_hawkish") if "ax1_inflation_hawkish" in names else 0
        red = {}
        for i, name in enumerate(names):
            if i == ax1_i:
                continue
            rho = corr[ax1_i, i]
            g1 = gates["by_tag"].get(f"ax1_inflation_hawkish__{design}", {}).get("d_same_action", {})
            gi = gates["by_tag"].get(f"{name}__{design}", {}).get("d_same_action", {})
            se_comb = math.sqrt((g1.get("se") or 0.1) ** 2 + (gi.get("se") or 0.1) ** 2)
            red[name] = {
                "spearman_vs_ax1": float(rho) if rho == rho else None,
                "near_duplicate": bool(rho == rho and abs(rho) >= 0.90),
                "ax1_d_same_rho": g1.get("rho"),
                "alt_d_same_rho": gi.get("rho"),
                "indistinguishable_gate": bool(
                    g1.get("rho") is not None and gi.get("rho") is not None
                    and abs(g1["rho"] - gi["rho"]) < 1.96 * se_comb
                ),
            }
        redundancy[design] = red

    _plot_corr(factor_out)
    _plot_loadings(factor_out)
    _plot_timeseries(score_frames)
    _plot_gates(gates)

    summary = {
        "run_id": RUN_ID,
        "tournaments": tournament_summaries,
        "factor": {
            d: {
                "pc1_dominant_axis": factor_out[d]["pc1_dominant_axis"],
                "var_explained": factor_out[d]["var_explained"][:4],
                "pc1_loadings": factor_out[d]["pc1_loadings"],
                "pc2_loadings": factor_out[d]["pc2_loadings"],
                "axes": factor_out[d]["axes"],
            }
            for d in factor_out
        },
        "redundancy": redundancy,
        "gates": gates,
        "cost": dict(_spend),
        "scope_notes": [
            "Corpus: 95 chair press-conference openings (prepared remarks only).",
            "Q&A drift: out of scope — Q&A not vendored; do not invent.",
            "Full-speech robustness: future work.",
            "SEP medians: not available as a vendored panel; skipped.",
            "FCI surprise: NFCI weekly change used as proxy.",
        ],
    }
    (OUT_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (OUT_DIR / "gates.json").write_text(json.dumps(gates, indent=2, default=str))
    write_findings(summary, factor_out, redundancy, gates, tournament_summaries)
    return summary


def _save_fig(name: str):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DOC_FIG.mkdir(parents=True, exist_ok=True)
    for d in (FIG_DIR, DOC_FIG):
        plt.savefig(d / name, dpi=150, bbox_inches="tight")
    plt.close()


def _plot_corr(factor_out):
    for design, fo in factor_out.items():
        corr = np.asarray(fo["corr"])
        fig, ax = plt.subplots(figsize=(8, 6.5))
        im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(fo["axes"])))
        ax.set_yticks(range(len(fo["axes"])))
        ax.set_xticklabels(fo["axes"], rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(fo["axes"], fontsize=8)
        for i in range(len(fo["axes"])):
            for j in range(len(fo["axes"])):
                ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center", fontsize=7)
        ax.set_title(f"Multi-axis Spearman correlation ({design})")
        fig.colorbar(im, ax=ax, fraction=0.046)
        _save_fig(f"multiaxis_corr_{design}.png")


def _plot_loadings(factor_out):
    for design, fo in factor_out.items():
        axes = fo["axes"]
        pc1 = [fo["pc1_loadings"][a] for a in axes]
        pc2 = [fo["pc2_loadings"].get(a, 0) for a in axes]
        fig, ax = plt.subplots(figsize=(8, 5))
        x = np.arange(len(axes))
        w = 0.35
        ax.bar(x - w / 2, pc1, w, label="PC1")
        ax.bar(x + w / 2, pc2, w, label="PC2")
        ax.set_xticks(x)
        ax.set_xticklabels(axes, rotation=35, ha="right", fontsize=8)
        ax.axhline(0, color="gray", lw=0.8)
        ax.legend()
        ve = fo["var_explained"]
        ax.set_title(
            f"Factor loadings ({design}); var PC1={ve[0]*100:.0f}% PC2={ve[1]*100:.0f}%"
        )
        ax.set_ylabel("Loading (SVD)")
        _save_fig(f"multiaxis_loadings_{design}.png")


def _plot_timeseries(score_frames):
    for design in DESIGNS:
        fig, ax = plt.subplots(figsize=(10, 5))
        for axdef in AXES:
            tag = f"{axdef['id']}__{design}"
            if tag not in score_frames:
                continue
            df = score_frames[tag].sort_values("date")
            ax.plot(pd.to_datetime(df["date"]), df["percentile"], lw=1.0, label=axdef["id"][:14])
        ax.set_ylabel("Percentile rank of mu")
        ax.set_xlabel("Meeting date")
        ax.set_title(f"Multi-axis percentile ranks over time ({design})")
        ax.legend(fontsize=7, ncol=2, loc="best")
        ax.set_ylim(0, 100)
        _save_fig(f"multiaxis_timeseries_{design}.png")


def _plot_gates(gates):
    tags = sorted(gates["by_tag"].keys())
    rhos = [gates["by_tag"][t]["d_same_action"].get("rho") or 0 for t in tags]
    ses = [gates["by_tag"][t]["d_same_action"].get("se") or 0 for t in tags]
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(tags))
    colors = ["#1a365d" if "ax1_" in t else "#2b6cb0" for t in tags]
    ax.bar(x, rhos, yerr=ses, color=colors, alpha=0.85, capsize=3)
    ax.axhline(0.30, color="crimson", ls="--", lw=1, label="pass line rho=0.30")
    ax.set_xticks(x)
    ax.set_xticklabels(tags, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("Spearman rho vs d_same (action days)")
    ax.set_title("Multi-axis validation: action-day funds-target agreement")
    ax.legend(fontsize=8)
    _save_fig("multiaxis_gates_dsame.png")

def write_findings(summary, factor_out, redundancy, gates, tournaments):
    lines = []
    lines.append("# Multi-axis FINDINGS")
    lines.append("")
    lines.append(f"**run_id:** `{RUN_ID}`  ")
    lines.append("**model:** Jev only (`jev-latest`) — Haiku not run  ")
    lines.append(f"**spend (tracked):** ${summary['cost'].get('usd', 0):.4f}  ")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(
        "Prepared chair press-conference **openings** only (n=95). "
        "Q&A drift is **out of scope** (Q&A not vendored). "
        "Full-speech robustness is **future work**."
    )
    lines.append("")
    lines.append("## Designs")
    lines.append("")
    lines.append("1. **Text-only** — no macro in the judge state.")
    lines.append(
        "2. **Conditional** — same-era Core PCE year-over-year, unemployment rate, "
        "real GDP growth (QoQ SAAR), VIX, and Chicago Fed National Financial Conditions "
        "Index (NFCI) attached; ask which passage is higher on the axis *given* conditions."
    )
    lines.append("")
    lines.append("## Does “something else” survive after tightness?")
    lines.append("")
    for design in DESIGNS:
        if design not in factor_out:
            continue
        fo = factor_out[design]
        lines.append(f"### {design}")
        lines.append("")
        lines.append(
            f"- PC1 variance share: **{fo['var_explained'][0]*100:.1f}%**; "
            f"dominant loading axis: `{fo['pc1_dominant_axis']}`."
        )
        if len(fo["var_explained"]) > 1:
            lines.append(f"- PC2 variance share: **{fo['var_explained'][1]*100:.1f}%**.")
        lines.append(
            f"- PC1 loadings: `{json.dumps({k: round(v, 3) for k, v in fo['pc1_loadings'].items()})}`"
        )
        lines.append(
            f"- PC2 loadings: `{json.dumps({k: round(v, 3) for k, v in fo['pc2_loadings'].items()})}`"
        )
        red = redundancy.get(design, {})
        dups = [k for k, v in red.items() if v.get("near_duplicate")]
        lines.append(
            "- Near-duplicates to axis 1 (|rho|>=0.90): "
            + (", ".join(f"`{d}`" for d in dups) if dups else "_none_")
            + "."
        )
        lines.append("")
    lines.append("## Gate snapshot (action-day Spearman vs `d_same`)")
    lines.append("")
    lines.append("| tag | rho | s.e. | n | pass (>=0.30) |")
    lines.append("|-----|----:|-----:|--:|:-------------:|")
    for tag in sorted(gates["by_tag"].keys()):
        g = gates["by_tag"][tag]["d_same_action"]
        rho, se, n = g.get("rho"), g.get("se"), g.get("n")
        passed = gates["by_tag"][tag].get("gate_d_same_pass")
        if rho is not None and se is not None:
            lines.append(
                f"| `{tag}` | {rho:+.3f} | {se:.3f} | {n} | {'PASS' if passed else 'fail'} |"
            )
        else:
            lines.append(f"| `{tag}` | — | — | {n} | — |")
    lines.append("")
    lines.append("## Tournament cost / comps")
    lines.append("")
    lines.append("| tag | n_comps | stop | max sigma | near-0.5 |")
    lines.append("|-----|--------:|------|----------:|---------:|")
    for t in tournaments:
        lines.append(
            f"| `{t['tag']}` | {t['n_comps']} | {t['stop_reason']} | "
            f"{t['max_sigma']:.3f} | {t.get('near_half_pairs', 0)} |"
        )
    lines.append("")
    lines.append("## Interpretation (non-causal)")
    lines.append("")
    lines.append(
        "Text ranks do **not** cause rate changes. Associations with `d_same` and yield "
        "moves are construct-validity checks on whether an axis separates meetings the "
        "way a funds-target observer would expect — not structural estimates."
    )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `results/multiaxis/scores/*.csv`, `ranked/*.csv`, `comparisons/*.jsonl`")
    lines.append("- `results/multiaxis/corr_{text,conditional}.csv`, `loadings_*.csv`")
    lines.append("- `results/multiaxis/gates.json`, `analysis_summary.json`, `cost.json`")
    lines.append(
        "- Figures: `multiaxis_corr_*.png`, `multiaxis_loadings_*.png`, "
        "`multiaxis_timeseries_*.png`, `multiaxis_gates_dsame.png`"
    )
    # Machine snapshot only. Do not overwrite the Pages note FINDINGS.md.
    (OUT_DIR / "FINDINGS_RUN.md").write_text("\n".join(lines) + "\n")


def write_cost(tournaments, t0):
    cost = {
        "run_id": RUN_ID,
        "usd_total": total_usd(),
        "usd_filter": _spend.get("filter_usd", 0),
        "usd_choice": _spend.get("choice_usd", 0),
        "input_tokens": _spend.get("in", 0),
        "output_tokens": _spend.get("out", 0),
        "price_per_mtok_input": JEV_PRICE_IN,
        "tournaments": [
            {
                "tag": t["tag"],
                "n_comps": t["n_comps"],
                "stop_reason": t["stop_reason"],
                "max_sigma": t["max_sigma"],
                "wall_seconds": t["wall_seconds"],
            }
            for t in tournaments
        ],
        "wall_seconds_total": time.perf_counter() - t0,
        "hard_cap_usd": USD_HARD_CAP,
        "target_usd": USD_TARGET,
    }
    (OUT_DIR / "cost.json").write_text(json.dumps(cost, indent=2))
    (OUT_DIR / "timing.json").write_text(json.dumps({
        "run_id": RUN_ID,
        "wall_seconds_total": cost["wall_seconds_total"],
        "per_tournament": {t["tag"]: t["wall_seconds"] for t in tournaments},
    }, indent=2))
    return cost


def preflight_projection(n_axes=7, n_designs=2) -> dict:
    filter_est = n_axes * 95 * 0.000136
    choice_est = n_axes * n_designs * 0.14
    order_swap = 0.02
    total = filter_est + choice_est + order_swap
    return {
        "filter_est_usd": filter_est,
        "choice_est_usd": choice_est,
        "order_swap_est_usd": order_swap,
        "total_est_usd": total,
        "abort_if_over": USD_HARD_CAP,
        "ok": total <= USD_HARD_CAP,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-filter", action="store_true")
    ap.add_argument("--force-filter", action="store_true")
    ap.add_argument("--skip-tournaments", action="store_true")
    ap.add_argument("--skip-analyze", action="store_true")
    ap.add_argument("--axes", nargs="*", default=None)
    ap.add_argument("--designs", nargs="*", default=None)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    pf = preflight_projection()
    (OUT_DIR / "preflight.json").write_text(json.dumps(pf, indent=2))
    print(f"[preflight] est ${pf['total_est_usd']:.2f} (cap ${USD_HARD_CAP})", flush=True)
    if not pf["ok"]:
        print("[preflight] ABORT: projected over hard cap", flush=True)
        return 2

    stmts = load_statements()
    print(f"[corpus] {len(stmts)} openings", flush=True)
    labels = build_meeting_labels(stmts)
    macros = load_macro_asof([s["date"] for s in stmts])
    (OUT_DIR / "macro_asof.json").write_text(json.dumps(macros, indent=2))
    (LABELS_DIR / "multiaxis_macro_asof.json").write_text(json.dumps(macros, indent=2))

    if args.skip_filter and (OUT_DIR / "filtered_passages.json").exists():
        filtered = json.loads((OUT_DIR / "filtered_passages.json").read_text())
    else:
        ax_ids = args.axes if args.axes else [a["id"] for a in AXES]
        filtered = prepare_filtered_corpus(stmts, force=args.force_filter, axes_subset=ax_ids)

    axes = AXES
    if args.axes:
        axes = [a for a in AXES if a["id"] in args.axes]
    designs = list(args.designs) if args.designs else list(DESIGNS)

    tournaments = []
    if not args.skip_tournaments:
        n_remaining = len(axes) * len(designs)
        stop_all = False
        for ax in axes:
            if stop_all:
                break
            for design in designs:
                proj = total_usd() + n_remaining * 0.14
                print(
                    f"[budget] spent ${total_usd():.3f}; project remaining→total ${proj:.2f}",
                    flush=True,
                )
                if proj > USD_HARD_CAP and total_usd() > 0.5:
                    print("[budget] STOP: projecting over hard cap", flush=True)
                    (OUT_DIR / "BUDGET_STOP.json").write_text(json.dumps({
                        "spent": total_usd(), "projected": proj,
                        "remaining_tournaments": n_remaining,
                    }, indent=2))
                    stop_all = True
                    break
                summary = run_tournament(
                    ax, design, filtered, macros,
                    dry_run=args.dry_run, concurrency=args.concurrency,
                )
                tournaments.append(summary)
                (OUT_DIR / "tournament_summaries.json").write_text(
                    json.dumps(tournaments, indent=2, default=str)
                )
                n_remaining -= 1
                if summary.get("stop_reason") == "hard_cap":
                    stop_all = True
                    break

        if total_usd() + 0.05 < USD_HARD_CAP:
            try:
                swap = order_swap_check(filtered, macros, n_pairs=30, dry_run=args.dry_run)
                print(f"[order_swap] flip_rate={swap['flip_rate']:.3f}", flush=True)
            except Exception as e:
                print(f"[order_swap] skipped: {e}", flush=True)
    else:
        if (OUT_DIR / "tournament_summaries.json").exists():
            tournaments = json.loads((OUT_DIR / "tournament_summaries.json").read_text())

    cost = write_cost(tournaments, t0)
    print(f"[cost] total ${cost['usd_total']:.4f}", flush=True)

    if not args.skip_analyze:
        summary = analyze_all(labels, tournaments)
        print(
            f"[analyze] PC1 text={summary['factor'].get('text', {}).get('pc1_dominant_axis')}; "
            f"cond={summary['factor'].get('conditional', {}).get('pc1_dominant_axis')}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
