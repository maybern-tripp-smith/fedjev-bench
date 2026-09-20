#!/usr/bin/env python3
"""fedjev-bench analysis: judgments, BT scores, gates, timing, REPORT fill."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data" / "raw" / "jsort" / "src"))
from jsort.model import fit as bt_fit, standard_errors as bt_se  # noqa: E402

RUN_ID = "fedjev-2026-09-20"
CRISIS = {"2020-03-03", "2020-03-15"}
SVB = "2023-03-22"
CONCURRENCY = 6


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


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


def bootstrap_spearman(x, y, n_boot=1000, seed=20260920):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    point, _ = spearman(x, y)
    if n < 3 or not np.isfinite(point):
        return {"rho": None if not np.isfinite(point) else float(point), "n": n, "ci_low": None, "ci_high": None}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r, _ = spearman(x[idx], y[idx])
        if np.isfinite(r):
            boots.append(r)
    boots = np.asarray(boots)
    return {
        "rho": float(point),
        "n": n,
        "ci_low": float(np.percentile(boots, 2.5)) if len(boots) else None,
        "ci_high": float(np.percentile(boots, 97.5)) if len(boots) else None,
        "n_boot": len(boots),
    }


def pct(arr, q):
    return float(np.percentile(arr, q)) if len(arr) else None


def summarize_lat(arr):
    arr = np.asarray(list(arr), dtype=float)
    if len(arr) == 0:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "max": None, "total_ms": 0}
    return {
        "n": int(len(arr)),
        "mean": float(arr.mean()),
        "p50": pct(arr, 50),
        "p95": pct(arr, 95),
        "max": float(arr.max()),
        "total_ms": float(arr.sum()),
    }


def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        if not np.isfinite(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def gate3_block(df, label, score_col="score"):
    d = df[df[score_col].notna()].copy()
    out = {"label": label, "score_col": score_col, "n": int(len(d))}
    out["all_scheduled"] = bootstrap_spearman(d[score_col], d["d_same"])
    d_nosvb = d[d["date"] != SVB]
    out["all_scheduled_excl_svb"] = bootstrap_spearman(d_nosvb[score_col], d_nosvb["d_same"])
    act = d[d["d_same"] != 0]
    hld = d[d["d_same"] == 0].copy()
    out["action_days"] = bootstrap_spearman(act[score_col], act["d_same"])
    out["action_days_excl_svb"] = bootstrap_spearman(
        act[act["date"] != SVB][score_col], act[act["date"] != SVB]["d_same"]
    )
    hld["dissent_net"] = hld["n_hawk_dissent"].fillna(0) - hld["n_dove_dissent"].fillna(0)
    out["hold_days_n"] = int(len(hld))
    out["hold_vs_dissent_net"] = bootstrap_spearman(hld[score_col], hld["dissent_net"])
    out["hold_vs_d_2y"] = bootstrap_spearman(hld[score_col], hld["d_2y"])
    out["hold_vs_dissent_excl_svb"] = bootstrap_spearman(
        hld[hld["date"] != SVB][score_col], hld[hld["date"] != SVB]["dissent_net"]
    )
    out["hold_vs_d_2y_excl_svb"] = bootstrap_spearman(
        hld[hld["date"] != SVB][score_col], hld[hld["date"] != SVB]["d_2y"]
    )
    return out


def means_holds_cuts(df, score_col="score"):
    d = df[df[score_col].notna()]
    holds = d[d["d_same"] == 0][score_col]
    cuts = d[d["d_same"] < 0][score_col]
    hikes = d[d["d_same"] > 0][score_col]
    gap = None
    passed = None
    if len(holds) and len(cuts):
        gap = float(holds.mean() - cuts.mean())
        passed = bool(holds.mean() > cuts.mean())
    return {
        "mean_holds": float(holds.mean()) if len(holds) else None,
        "n_holds": int(len(holds)),
        "mean_cuts": float(cuts.mean()) if len(cuts) else None,
        "n_cuts": int(len(cuts)),
        "mean_hikes": float(hikes.mean()) if len(hikes) else None,
        "n_hikes": int(len(hikes)),
        "gap_holds_minus_cuts": gap,
        "pass": passed,
    }


def main() -> None:
    pairs = load_jsonl(ROOT / "data/pairs/gold_pairs.jsonl")
    pair_index = {p["pair_id"]: p for p in pairs}
    answers = load_jsonl(ROOT / "runs/jev/answers.jsonl")
    meetings = pd.read_parquet(ROOT / "data/labels/meetings.parquet")
    meetings["date"] = meetings["date"].astype(str)

    choice: dict[str, dict] = {}
    score_docs: dict[str, dict] = {}
    for a in answers:
        if a.get("error") or a.get("ok") is False:
            continue
        if a.get("kind") == "choice" and a.get("pair_id") and a.get("order"):
            key = f"{a['pair_id']}:{a['order']}"
            prev = choice.get(key)
            if prev is None or (prev.get("cache_hit") and not a.get("cache_hit")):
                choice[key] = a
        elif a.get("kind") == "score" and a.get("doc_id"):
            prev = score_docs.get(a["doc_id"])
            if prev is None or (prev.get("cache_hit") and not a.get("cache_hit")):
                score_docs[a["doc_id"]] = a

    # --- pair judgments ---
    judgments = []
    for p in pairs:
        pid = p["pair_id"]
        ab = choice.get(f"{pid}:ab")
        ba = choice.get(f"{pid}:ba")
        probs_a, probs_b, winners = [], [], []
        if ab and ab.get("ok", True) and not ab.get("error"):
            probs_a.append(float(ab["p_A"]))
            probs_b.append(float(ab["p_B"]))
            winners.append("a" if ab["winner"] == "A" else "b")
        if ba and ba.get("ok", True) and not ba.get("error"):
            probs_a.append(float(ba["p_B"]))
            probs_b.append(float(ba["p_A"]))
            winners.append("b" if ba["winner"] == "A" else "a")
        if not probs_a:
            continue
        p_a = sum(probs_a) / len(probs_a)
        p_b = sum(probs_b) / len(probs_b)
        winner_avg = "a" if p_a >= p_b else "b"
        gold = p.get("gold")
        inverted = (winner_avg != gold) if gold in ("a", "b") else None
        p_gold = p_a if gold == "a" else (p_b if gold == "b" else None)
        brier = (p_gold - 1.0) ** 2 if p_gold is not None else None
        order_flip = len(set(winners)) > 1 if len(winners) == 2 else None
        judgments.append({
            "pair_id": pid,
            "source": p.get("source"),
            "gold": gold,
            "p_A_avg": p_a,
            "p_B_avg": p_b,
            "p_gold": p_gold,
            "brier": brier,
            "winner_avg": winner_avg,
            "inverted": inverted,
            "order_flip": order_flip,
            "n_orders": len(probs_a),
            "winners_per_order": winners,
            "a": p.get("a"),
            "b": p.get("b"),
            "hawk_date": p.get("hawk_date"),
            "dove_date": p.get("dove_date"),
        })

    judgments_path = ROOT / "results/pair_judgments.jsonl"
    with judgments_path.open("w") as f:
        for r in judgments:
            f.write(json.dumps(r) + "\n")

    inv_tables = {}
    for src in ("extreme", "shah", "adjacent"):
        subset = [j for j in judgments if j["source"] == src]
        n = len(subset)
        n_inv = sum(1 for j in subset if j["inverted"])
        brier_vals = [j["brier"] for j in subset if j["brier"] is not None]
        p_golds = [j["p_gold"] for j in subset if j["p_gold"] is not None]
        flips = [j for j in subset if j["order_flip"]]
        inv_tables[src] = {
            "n": n,
            "n_inverted": n_inv,
            "inversion_rate": (n_inv / n) if n else None,
            "mean_brier": float(np.mean(brier_vals)) if brier_vals else None,
            "mean_p_gold": float(np.mean(p_golds)) if p_golds else None,
            "n_order_flip": len(flips),
            "order_flip_rate": (len(flips) / n) if n else None,
            "inverted_pair_ids": [j["pair_id"] for j in subset if j["inverted"]],
        }

    # --- BT on statement pairs (A + C) ---
    id_list: list[str] = []
    id_to_idx: dict[str, int] = {}

    def ensure(i: str) -> int:
        if i not in id_to_idx:
            id_to_idx[i] = len(id_list)
            id_list.append(i)
        return id_to_idx[i]

    first_ids, second_ids, ys = [], [], []
    stmt_comparisons = []
    for a in choice.values():
        p = pair_index.get(a["pair_id"])
        if not p or p.get("source") not in ("extreme", "adjacent"):
            continue
        id_a, id_b = a["id_A"], a["id_B"]
        if not (str(id_a).startswith("stmt-") and str(id_b).startswith("stmt-")):
            continue
        y = float(a["p_A"])
        first_ids.append(ensure(id_a))
        second_ids.append(ensure(id_b))
        ys.append(y)
        stmt_comparisons.append((id_a, id_b, y, a.get("order"), a["pair_id"]))

    fitted = bt_fit(len(id_list), first_ids, second_ids, ys)
    ses = bt_se(len(id_list), first_ids, second_ids, ys, fitted)
    pair_involvement: dict[str, set] = defaultdict(set)
    for id_a, id_b, y, order, pid in stmt_comparisons:
        pair_involvement[id_a].add(pid)
        pair_involvement[id_b].add(pid)

    score_by_date = {}
    for doc_id, s in score_docs.items():
        date = s.get("date") or doc_id.replace("stmt-", "")
        score_by_date[date] = float(s["score"])

    bt_map = {}
    for i, doc_id in enumerate(id_list):
        date = doc_id.replace("stmt-", "")
        bt_map[date] = {
            "date": date,
            "score": float(fitted.theta[i]),
            "se": float(ses[i]),
            "n_pairs": len(pair_involvement[doc_id]),
            "score_jev": score_by_date.get(date),
        }

    all_dates = sorted(set(score_by_date) | set(bt_map))
    out_rows = []
    for d in all_dates:
        if d in bt_map:
            out_rows.append(bt_map[d])
        else:
            out_rows.append({
                "date": d,
                "score": np.nan,
                "se": np.nan,
                "n_pairs": 0,
                "score_jev": score_by_date.get(d),
            })
    df_scores = pd.DataFrame(out_rows).sort_values("date")
    # CSV columns: date, score, se, n_pairs (+ score_jev secondary)
    df_scores[["date", "score", "se", "n_pairs", "score_jev"]].to_csv(
        ROOT / "results/statement_scores.csv", index=False
    )

    m = meetings.merge(df_scores, on="date", how="left")
    main = m[
        (m["is_scheduled"] == True)
        & (m["exclude_main"] == False)
        & m["score"].notna()
        & ~m["date"].isin(CRISIS)
    ].copy()
    main_score = m[
        (m["is_scheduled"] == True)
        & (m["exclude_main"] == False)
        & m["score_jev"].notna()
        & ~m["date"].isin(CRISIS)
    ].copy()

    gate3_bt = gate3_block(main, "BT statement score", "score")
    gate3_jev = gate3_block(main_score, "Score-pass score_jev", "score_jev")
    gate4_bt = means_holds_cuts(main, "score")
    gate4_jev = means_holds_cuts(main_score, "score_jev")
    g5_bt = bootstrap_spearman(main["score"], main["d_90"])
    g5_jev = bootstrap_spearman(main_score["score_jev"], main_score["d_90"])

    # Gate 6 — name ablation (load results/name_ablation.json if present)
    a_judgments = [j for j in judgments if j["source"] == "extreme"]
    n_flip = sum(1 for j in a_judgments if j["order_flip"])
    abl_path = ROOT / "results/name_ablation.json"
    if abl_path.exists():
        abl = json.loads(abl_path.read_text())
        gate6 = {
            "name_ablation": "RUN",
            "metric": "Stratum A names-in inversion delta vs stripped baseline",
            "pass_line": "Δ inversion ≤ 0.05",
            "stratum_A_baseline_inversion": inv_tables["extreme"]["inversion_rate"],
            "stratum_A_names_inversion": abl.get("inversion_rate"),
            "stratum_A_n": abl.get("n_pairs", len(a_judgments)),
            "n_inverted_names": abl.get("n_inverted"),
            "inverted_pairs_names": abl.get("inverted_pairs", []),
            "stratum_A_order_flip_n": abl.get("order_flip_n", n_flip),
            "stratum_A_order_flip_rate": abl.get("order_flip_rate", (n_flip / len(a_judgments)) if a_judgments else None),
            "inversion_delta_vs_names": abl.get("inversion_delta"),
            "names_ablation_cost_usd": (abl.get("cost_usd") or {}).get("total"),
            "names_ablation_input_tokens": (abl.get("usage") or {}).get("input_tokens"),
            "names_ablation_n_calls": abl.get("n_live"),
            "cache_key_suffix": "names=1",
            "text_mode": "raw_text / unstripped",
            "status": "PASS" if abl.get("pass") else "FAIL",
            "pass": bool(abl.get("pass")),
        }
    else:
        gate6 = {
            "name_ablation": "NOT RUN",
            "reason": "results/name_ablation.json missing; run scripts/run_name_ablation.py --live",
            "stratum_A_baseline_inversion": inv_tables["extreme"]["inversion_rate"],
            "stratum_A_n": len(a_judgments),
            "stratum_A_order_flip_n": n_flip,
            "stratum_A_order_flip_rate": (n_flip / len(a_judgments)) if a_judgments else None,
            "inversion_delta_vs_names": None,
            "pass_line": "Δ inversion ≤ 0.05 (names-in vs baseline)",
            "status": "NOT RUN (order-flip stability reported)",
            "pass": None,
        }

    # Gate 7 FedLock
    fl = json.loads((ROOT / "data/raw/fedlock/data.json").read_text())
    pcs = {s["d"]: s for s in fl["speeches"] if s["st"] == "press_conference"}

    def parse_d(d):
        return datetime.strptime(d, "%Y-%m-%d")

    fedlock_by_meeting = {}
    for d in m["date"].unique():
        for delta in (0, 1, -1, 2):
            cand = (parse_d(str(d)) + timedelta(days=delta)).strftime("%Y-%m-%d")
            if cand in pcs:
                fedlock_by_meeting[str(d)] = {
                    "fedlock_date": cand,
                    "delta_days": delta,
                    "m": float(pcs[cand]["m"]),
                    "author": pcs[cand]["a"],
                }
                break
    fl_df = pd.DataFrame([
        {"date": d, "fedlock_m": info["m"], "fedlock_date": info["fedlock_date"], "fedlock_delta": info["delta_days"]}
        for d, info in fedlock_by_meeting.items()
    ])
    m2 = m.merge(fl_df, on="date", how="left")
    main_fl = m2[
        (m2["is_scheduled"] == True)
        & (m2["exclude_main"] == False)
        & ~m2["date"].isin(CRISIS)
    ]
    g7_bt = bootstrap_spearman(
        main_fl.loc[main_fl["score"].notna() & main_fl["fedlock_m"].notna(), "score"],
        main_fl.loc[main_fl["score"].notna() & main_fl["fedlock_m"].notna(), "fedlock_m"],
    )
    g7_jev = bootstrap_spearman(
        main_fl.loc[main_fl["score_jev"].notna() & main_fl["fedlock_m"].notna(), "score_jev"],
        main_fl.loc[main_fl["score_jev"].notna() & main_fl["fedlock_m"].notna(), "fedlock_m"],
    )

    # Timing
    seen_logical: dict[str, dict] = {}
    for a in answers:
        if a.get("kind") == "choice" and a.get("pair_id") and a.get("order"):
            key = f"choice:{a['pair_id']}:{a['order']}"
        elif a.get("kind") == "score" and a.get("doc_id"):
            key = f"score:{a['doc_id']}"
        else:
            continue
        if a.get("latency_ms") is None:
            continue
        prev = seen_logical.get(key)
        if prev is None or (prev.get("cache_hit") and not a.get("cache_hit")):
            seen_logical[key] = a

    lat_records = []
    for a in seen_logical.values():
        if a.get("kind") == "score":
            stratum = "score_docs"
        else:
            stratum = {"extreme": "extreme", "shah": "shah", "adjacent": "adjacent"}.get(
                a.get("source"), a.get("source") or "unknown"
            )
        lat_records.append({
            "kind": a["kind"],
            "stratum": stratum,
            "latency_ms": int(a["latency_ms"]),
            "cache_hit": bool(a.get("cache_hit")),
        })
    all_lats = [r["latency_ms"] for r in lat_records]
    timing = {
        "run_id": RUN_ID,
        "n_calls": len(lat_records),
        "concurrency": CONCURRENCY,
        "concurrency_note": "score.py ThreadPoolExecutor max_workers=6 (default --concurrency 6)",
        "total_wall_ms": None,
        "total_wall_note": (
            "Full-run wall clock was not separately logged. "
            "sum_latency_ms is the sum of per-call latency_ms; under concurrency=6, "
            "approx_wall_ms_if_perfect_parallel ≈ sum/6 is a lower bound on wall."
        ),
        "sum_latency_ms": int(sum(all_lats)),
        "approx_wall_ms_if_perfect_parallel": int(sum(all_lats) / CONCURRENCY) if all_lats else None,
        "overall": summarize_lat(all_lats),
        "by_stratum": {
            s: summarize_lat([r["latency_ms"] for r in lat_records if r["stratum"] == s])
            for s in ("extreme", "shah", "adjacent", "score_docs")
        },
        "by_kind": {
            "choice": summarize_lat([r["latency_ms"] for r in lat_records if r["kind"] == "choice"]),
            "score": summarize_lat([r["latency_ms"] for r in lat_records if r["kind"] == "score"]),
        },
        "cache_hits_among_deduped_calls": sum(1 for r in lat_records if r["cache_hit"]),
    }
    (ROOT / "results/timing.json").write_text(json.dumps(sanitize(timing), indent=2) + "\n")

    cost = json.loads((ROOT / "results/cost.json").read_text())

    g1_rate = inv_tables["extreme"]["inversion_rate"]
    g1_pass = g1_rate is not None and g1_rate <= 0.05
    g1_inverted = []
    for j in judgments:
        if j["source"] == "extreme" and j["inverted"]:
            g1_inverted.append({
                "pair_id": j["pair_id"],
                "a": j["a"],
                "b": j["b"],
                "hawk_date": j.get("hawk_date"),
                "dove_date": j.get("dove_date"),
                "p_A_avg": j["p_A_avg"],
                "p_B_avg": j["p_B_avg"],
                "winner_avg": j["winner_avg"],
            })

    g3_rho = gate3_bt["all_scheduled"]["rho"]
    g3_action_rho = gate3_bt["action_days"]["rho"]
    g3_pass = False
    if g3_rho is not None and g3_rho >= 0.30:
        g3_pass = True
    if g3_action_rho is not None and g3_action_rho >= 0.30:
        g3_pass = True

    if gate4_bt["pass"] is not None:
        gate4_primary, gate4_primary_source = gate4_bt, "BT"
        g4_pass = gate4_bt["pass"]
    else:
        gate4_primary, gate4_primary_source = gate4_jev, "score_jev"
        g4_pass = gate4_jev["pass"]

    gates = {
        "run_id": RUN_ID,
        "criterion": "more hawkish about inflation",
        "model": cost.get("model"),
        "bt_fit": {
            "n_statements": len(id_list),
            "n_comparisons": len(ys),
            "converged": bool(fitted.converged),
            "gamma": float(fitted.gamma),
            "sources": ["extreme", "adjacent"],
            "excluded": ["shah (sentence-level)"],
        },
        "gates": {
            "1_easy_pair_inversion": {
                "metric": "Stratum A (extreme) inversion rate",
                "pass_line": "≤ 0.05",
                "value": g1_rate,
                "n": inv_tables["extreme"]["n"],
                "n_inverted": inv_tables["extreme"]["n_inverted"],
                "mean_brier": inv_tables["extreme"]["mean_brier"],
                "inverted_pairs": g1_inverted,
                "pass": g1_pass,
            },
            "2_sentence_discrimination": {
                "metric": "Stratum B inversion + Brier",
                "pass_line": "report only",
                "inversion_rate": inv_tables["shah"]["inversion_rate"],
                "n": inv_tables["shah"]["n"],
                "n_inverted": inv_tables["shah"]["n_inverted"],
                "mean_brier": inv_tables["shah"]["mean_brier"],
                "mean_p_gold": inv_tables["shah"]["mean_p_gold"],
                "pass": None,
                "status": "report_only",
            },
            "3_action_ranking": {
                "metric": "Spearman(BT score, d_same) scheduled excl crisis",
                "pass_line": "≥ +0.30",
                "signal_line": 0.30,
                "jsort_published": 0.46,
                "primary": gate3_bt,
                "secondary_score_jev": gate3_jev,
                "pass": bool(g3_pass),
                "pass_detail": {
                    "all_scheduled_rho": g3_rho,
                    "action_days_rho": g3_action_rho,
                },
            },
            "4_holds_vs_cuts": {
                "metric": "mean(holds) > mean(cuts)",
                "primary_source": gate4_primary_source,
                "primary": gate4_primary,
                "bt": gate4_bt,
                "score_jev": gate4_jev,
                "pass": g4_pass,
            },
            "5_forward_path": {
                "metric": "Spearman vs d_90",
                "pass_line": "secondary",
                "bt": g5_bt,
                "score_jev": g5_jev,
                "pass": None,
                "status": "secondary",
            },
            "6_order_name_stability": gate6,
            "7_fedlock_consistency": {
                "metric": "Spearman Jev vs FedLock press_conference m (meeting±1d match)",
                "pass_line": "report only",
                "n_fedlock_matched_meetings": len(fedlock_by_meeting),
                "bt": g7_bt,
                "score_jev": g7_jev,
                "pass": None,
                "status": "report_only",
            },
        },
        "inversion_tables": inv_tables,
        "adjacent_labeled": {
            "inversion_rate": inv_tables["adjacent"]["inversion_rate"],
            "n": inv_tables["adjacent"]["n"],
            "n_inverted": inv_tables["adjacent"]["n_inverted"],
            "mean_brier": inv_tables["adjacent"]["mean_brier"],
            "inverted_pair_ids": inv_tables["adjacent"]["inverted_pair_ids"],
        },
        "cost_usd_total": cost.get("cost_usd", {}).get("total"),
        "timing_summary": {
            "n_calls": timing["n_calls"],
            "mean_latency_ms": timing["overall"]["mean"],
            "p50_latency_ms": timing["overall"]["p50"],
            "p95_latency_ms": timing["overall"]["p95"],
            "concurrency": CONCURRENCY,
        },
    }
    gates = sanitize(gates)
    (ROOT / "results/gates.json").write_text(json.dumps(gates, indent=2) + "\n")

    # --- REPORT.md ---
    def fmt_rho(block):
        if not block or block.get("rho") is None:
            return "n/a"
        ci = ""
        if block.get("ci_low") is not None:
            ci = f" [{block['ci_low']:+.3f}, {block['ci_high']:+.3f}]"
        return f"{block['rho']:+.3f} (n={block['n']}){ci}"

    def fmt_mean(x):
        return "n/a" if x is None else f"{x:.4f}"

    inv_a = inv_tables["extreme"]
    inv_b = inv_tables["shah"]
    inv_c = inv_tables["adjacent"]
    g3 = gate3_bt
    g4 = gate4_primary

    verdict = (
        f"Gate 1 {'PASSES' if g1_pass else 'FAILS'} "
        f"(Stratum A inversion={g1_rate:.3f}"
        f"{'' if not g1_inverted else '; inverted: ' + ','.join(x['pair_id'] for x in g1_inverted)}"
        f"). Gate 3 "
        f"{'CLEARS' if g3_pass else 'does NOT clear'} the +0.30 signal "
        f"(BT Spearman vs d_same all-scheduled={fmt_rho(g3['all_scheduled'])}, "
        f"action_days={fmt_rho(g3['action_days'])}"
        f"; score_jev secondary all={fmt_rho(gate3_jev['all_scheduled'])}). "
        f"Gate 4 "
        f"{'holds > cuts' if g4_pass else 'does NOT show holds > cuts'} "
        f"on {gate4_primary_source}: mean(holds)={fmt_mean(g4['mean_holds'])} "
        f"(n={g4['n_holds']}) vs mean(cuts)={fmt_mean(g4['mean_cuts'])} "
        f"(n={g4['n_cuts']}), gap={fmt_mean(g4['gap_holds_minus_cuts'])}."
    )

    report = f"""# fedjev-bench REPORT — pre-registered gates

**run_id:** `{RUN_ID}`  
**phase:** Jev half complete — results filled  
**model:** {cost.get('model', 'jev-1.13.0')}  
**pricing:** $0.042 / Mtok input; output free  
**cost log:** `results/cost.json` · timing: `results/timing.json`

## Thesis

Rate changes label *policy*. Jev labels *text*. Gate 1 says whether Jev can see an obvious hawk vs dove document. Gate 3 says whether that text ranking tracks the decision on scheduled days. Gate 4 is the important disagreement: if Jev ranks 2023 holds and 2026 hawkish-hold-with-dissents above 2020 cuts while d_same=0, the model is reading tone and the rate series is the wrong sole GT. That is the result, not a bug to paper over.

## Analysis exclusions (pre-registered)

- **Exclude from main analysis:** 2020-03-03, 2020-03-15 (unscheduled / intermeeting cuts), and any other intermeeting moves (`exclude_main` / `is_scheduled=false`).
- **Flag, do not drop:** 2023-03-22 (SVB) — column `flag_svb`.

## Gates (registered before any Jev output)

| # | Gate | Metric / rule | Pass line |
|---|------|---------------|-----------|
| 1 | Easy-pair inversion | Stratum A; average both presentation orders | inversion ≤ 0.05 |
| 2 | Sentence discrimination | Stratum B; inversion + Brier on p(gold) | **report only** |
| 3 | Statement score vs action | Spearman(Jev statement score, `d_same`) on scheduled meetings, crisis excluded; signal line +0.30 (jsort published +0.46). Split `action_days` vs `hold_days`; on holds correlate with `(n_hawk_dissent − n_dove_dissent)` and `d_2y` instead | Spearman ≥ +0.30 on action/all scheduled (signal) |
| 4 | Holds vs cuts | Mean score on holds (`d_same=0`) vs mean score on cuts (`d_same<0`) | mean(holds) > mean(cuts) |
| 5 | Forward path | Spearman vs `d_90` | **secondary** |
| 6 | Order/name stability | Stratum A with names in + order flip; inversion delta | Δ inversion ≤ 0.05 |
| 7 | FedLock consistency | Spearman vs FedLock hawkishness scores (`data/raw/fedlock/`) | **report only** |

## Scoring protocol

- Criterion string (exact): `more hawkish about inflation`
- Choice: Text A / Text B (meta stripped via `scripts/strip_meta.py`); options A/B; both orders
- Secondary Score levels: much more dovish / somewhat dovish / neutral / somewhat hawkish / much more hawkish
- Entry: `score.py` → `runs/jev/`
- **Every answer logged** `usage.input_tokens`, `usage.output_tokens`, `latency_ms`; roll up to `results/cost.json` at $0.042/Mtok input

## Results

### Verdict

{verdict}

### Gate pass/fail

| # | Gate | Result | Detail |
|---|------|--------|--------|
| 1 | Easy-pair inversion | **{'PASS' if g1_pass else 'FAIL'}** | rate={g1_rate:.4f} (n={inv_a['n']}, inverted={inv_a['n_inverted']}) |
| 2 | Sentence discrimination | report | inv={inv_b['inversion_rate']:.4f}, Brier={inv_b['mean_brier']:.4f}, p(gold)={inv_b['mean_p_gold']:.4f} (n={inv_b['n']}) |
| 3 | Action ranking | **{'PASS' if g3_pass else 'FAIL'}** | BT all={fmt_rho(g3['all_scheduled'])}; action={fmt_rho(g3['action_days'])} |
| 4 | Holds vs cuts | **{'PASS' if g4_pass else 'FAIL'}** | {gate4_primary_source}: holds={fmt_mean(g4['mean_holds'])} (n={g4['n_holds']}) > cuts={fmt_mean(g4['mean_cuts'])} (n={g4['n_cuts']})? gap={fmt_mean(g4['gap_holds_minus_cuts'])} |
| 5 | Forward path | secondary | BT vs d_90={fmt_rho(g5_bt)}; score_jev={fmt_rho(g5_jev)} |
| 6 | Order/name stability | {'**PASS**' if gate6.get('pass') else ('NOT RUN' if gate6.get('pass') is None else '**FAIL**')} | names Δ={gate6.get('inversion_delta_vs_names')}; names-inv={gate6.get('stratum_A_names_inversion')}; baseline={gate6['stratum_A_baseline_inversion']:.4f}; order-flip={gate6['stratum_A_order_flip_rate']:.4f} |
| 7 | FedLock consistency | report | BT={fmt_rho(g7_bt)}; score_jev={fmt_rho(g7_jev)}; matched meetings={len(fedlock_by_meeting)} |

### Inversion tables (both orders averaged → original A/B)

| Stratum | source | n | inverted | inversion rate | mean p(gold) | mean Brier | order-flip rate |
|---------|--------|--:|--------:|---------------:|-------------:|-------------:|----------------:|
| A easy | extreme | {inv_a['n']} | {inv_a['n_inverted']} | {inv_a['inversion_rate']:.4f} | {inv_a['mean_p_gold']:.4f} | {inv_a['mean_brier']:.4f} | {inv_a['order_flip_rate']:.4f} |
| B Shah | shah | {inv_b['n']} | {inv_b['n_inverted']} | {inv_b['inversion_rate']:.4f} | {inv_b['mean_p_gold']:.4f} | {inv_b['mean_brier']:.4f} | {inv_b['order_flip_rate']:.4f} |
| C adjacent | adjacent | {inv_c['n']} | {inv_c['n_inverted']} | {inv_c['inversion_rate']:.4f} | {inv_c['mean_p_gold']:.4f} | {inv_c['mean_brier']:.4f} | {inv_c['order_flip_rate']:.4f} |

**Inverted Stratum A pairs:** {( 'none' if not g1_inverted else ', '.join(x['pair_id'] for x in g1_inverted) )}

**Inverted Stratum C pairs:** {(', '.join(inv_c['inverted_pair_ids']) if inv_c['inverted_pair_ids'] else 'none')}

### Gate 3 detail (BT primary; bootstrap 1000 meetings)

| Slice | Spearman ρ [95% CI] |
|-------|---------------------|
| All scheduled (excl crisis) | {fmt_rho(g3['all_scheduled'])} |
| All scheduled excl SVB 2023-03-22 | {fmt_rho(g3['all_scheduled_excl_svb'])} |
| action_days (d_same≠0) | {fmt_rho(g3['action_days'])} |
| action_days excl SVB | {fmt_rho(g3['action_days_excl_svb'])} |
| hold_days vs (n_hawk−n_dove) dissent | {fmt_rho(g3['hold_vs_dissent_net'])} |
| hold_days vs d_2y | {fmt_rho(g3['hold_vs_d_2y'])} |
| holds vs dissent excl SVB | {fmt_rho(g3['hold_vs_dissent_excl_svb'])} |
| holds vs d_2y excl SVB | {fmt_rho(g3['hold_vs_d_2y_excl_svb'])} |

Secondary Score-pass (`score_jev`): all={fmt_rho(gate3_jev['all_scheduled'])}; action={fmt_rho(gate3_jev['action_days'])}; holds vs dissent={fmt_rho(gate3_jev['hold_vs_dissent_net'])}; holds vs d_2y={fmt_rho(gate3_jev['hold_vs_d_2y'])}.

BT fit: n_statements={len(id_list)}, n_comparisons={len(ys)} (strata A+C Choice probs; Shah excluded), converged={fitted.converged}, γ(position)={fitted.gamma:.4f}.

### Gate 4 holds vs cuts

| Score | mean holds (n) | mean cuts (n) | mean hikes (n) | gap (holds−cuts) |
|-------|----------------|---------------|----------------|------------------|
| BT | {fmt_mean(gate4_bt['mean_holds'])} ({gate4_bt['n_holds']}) | {fmt_mean(gate4_bt['mean_cuts'])} ({gate4_bt['n_cuts']}) | {fmt_mean(gate4_bt['mean_hikes'])} ({gate4_bt['n_hikes']}) | {fmt_mean(gate4_bt['gap_holds_minus_cuts'])} |
| score_jev | {fmt_mean(gate4_jev['mean_holds'])} ({gate4_jev['n_holds']}) | {fmt_mean(gate4_jev['mean_cuts'])} ({gate4_jev['n_cuts']}) | {fmt_mean(gate4_jev['mean_hikes'])} ({gate4_jev['n_hikes']}) | {fmt_mean(gate4_jev['gap_holds_minus_cuts'])} |

### Cost

| | |
|--|--:|
| Total USD | ${cost.get('cost_usd',{}).get('total',0):.6f} |
| Input tokens | {cost.get('usage',{}).get('input_tokens',0):,} |
| Output tokens | {cost.get('usage',{}).get('output_tokens',0):,} (free) |
| n_calls (cache-backed) | {cost.get('n_calls')} |
| n_choice / n_score | {cost.get('n_choice_answers')} / {cost.get('n_score_answers')} |
| USD / gold pair | ${cost.get('usd_per_pair') or 0:.6f} |

By stratum: extreme ${cost.get('by_stratum',{}).get('extreme',{}).get('usd',0):.5f}; shah ${cost.get('by_stratum',{}).get('shah',{}).get('usd',0):.5f}; adjacent ${cost.get('by_stratum',{}).get('adjacent',{}).get('usd',0):.5f}; score_docs ${cost.get('by_stratum',{}).get('score_docs',{}).get('usd',0):.5f}.

### Timing

Concurrency: **{CONCURRENCY}** (`score.py` ThreadPoolExecutor). Full-run wall clock was not separately logged; figures below are per-call `latency_ms` from `runs/jev/answers.jsonl` (deduped to one record per logical call).

| Scope | n | mean ms | p50 | p95 | max | sum ms |
|-------|--:|--------:|----:|----:|----:|-------:|
| Overall | {timing['overall']['n']} | {timing['overall']['mean']:.1f} | {timing['overall']['p50']:.1f} | {timing['overall']['p95']:.1f} | {timing['overall']['max']:.0f} | {timing['overall']['total_ms']:.0f} |
| Choice | {timing['by_kind']['choice']['n']} | {timing['by_kind']['choice']['mean']:.1f} | {timing['by_kind']['choice']['p50']:.1f} | {timing['by_kind']['choice']['p95']:.1f} | {timing['by_kind']['choice']['max']:.0f} | {timing['by_kind']['choice']['total_ms']:.0f} |
| Score | {timing['by_kind']['score']['n']} | {timing['by_kind']['score']['mean']:.1f} | {timing['by_kind']['score']['p50']:.1f} | {timing['by_kind']['score']['p95']:.1f} | {timing['by_kind']['score']['max']:.0f} | {timing['by_kind']['score']['total_ms']:.0f} |
| extreme | {timing['by_stratum']['extreme']['n']} | {timing['by_stratum']['extreme']['mean']:.1f} | {timing['by_stratum']['extreme']['p50']:.1f} | {timing['by_stratum']['extreme']['p95']:.1f} | {timing['by_stratum']['extreme']['max']:.0f} | {timing['by_stratum']['extreme']['total_ms']:.0f} |
| shah | {timing['by_stratum']['shah']['n']} | {timing['by_stratum']['shah']['mean']:.1f} | {timing['by_stratum']['shah']['p50']:.1f} | {timing['by_stratum']['shah']['p95']:.1f} | {timing['by_stratum']['shah']['max']:.0f} | {timing['by_stratum']['shah']['total_ms']:.0f} |
| adjacent | {timing['by_stratum']['adjacent']['n']} | {timing['by_stratum']['adjacent']['mean']:.1f} | {timing['by_stratum']['adjacent']['p50']:.1f} | {timing['by_stratum']['adjacent']['p95']:.1f} | {timing['by_stratum']['adjacent']['max']:.0f} | {timing['by_stratum']['adjacent']['total_ms']:.0f} |
| score_docs | {timing['by_stratum']['score_docs']['n']} | {timing['by_stratum']['score_docs']['mean']:.1f} | {timing['by_stratum']['score_docs']['p50']:.1f} | {timing['by_stratum']['score_docs']['p95']:.1f} | {timing['by_stratum']['score_docs']['max']:.0f} | {timing['by_stratum']['score_docs']['total_ms']:.0f} |

Approx wall if perfect parallel (sum/6): **{timing['approx_wall_ms_if_perfect_parallel']} ms** (~{timing['approx_wall_ms_if_perfect_parallel']/1000:.1f}s).

### Artifacts

| Path | Role |
|------|------|
| `results/pair_judgments.jsonl` | Per gold pair, both orders averaged, Brier on p(gold) |
| `results/statement_scores.csv` | BT `score`/`se`/`n_pairs` + `score_jev` |
| `results/gates.json` | Machine-readable gate results |
| `results/cost.json` | Token/USD rollup |
| `results/timing.json` | Latency summary |
| `runs/jev/answers.jsonl` | Raw Jev answers |

"""
    (ROOT / "REPORT.md").write_text(report)
    print("=== SUMMARY ===")
    print("G1", g1_pass, g1_rate, "inverted", g1_inverted)
    print("G3", g3_pass, "all", g3_rho, "action", g3_action_rho)
    print("G4", g4_pass, gate4_primary_source, gate4_primary)
    print("G5 BT", g5_bt)
    print("G7 BT", g7_bt, "jev", g7_jev)
    print("timing n", timing["n_calls"], "mean", timing["overall"]["mean"])
    print("wrote REPORT.md, gates.json, timing.json, statement_scores.csv, pair_judgments.jsonl")


if __name__ == "__main__":
    main()
