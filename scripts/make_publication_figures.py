#!/usr/bin/env python3
"""Publication-quality Economist-style figures for fedjev-bench.

Writes PNG (180 dpi) + PDF to results/figures/ and copies to docs/figures/.
Uses only real artifacts under results/ and data/.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = RES / "figures"
DOCFIG = ROOT / "docs" / "figures"
CRISIS = {"2020-03-03", "2020-03-15"}

# Economist / paper palette
BG = "#f7f5f0"
INK = "#1a1a1a"
MUTED = "#4a5568"
GRID = "#d4cfc4"
C_ACTION = "#1a365d"  # navy
C_HOLD = "#718096"  # gray-blue
C_HIKE = "#9b2c2c"  # muted brick
C_CUT = "#2b6cb0"  # muted blue
C_HOLD2 = "#744210"  # muted brown
C_JEV = "#276749"  # green
C_HAIKU = "#6b46c1"  # muted purple
C_ACCENT = "#c05621"  # terracotta


def style():
    mpl.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": BG,
            "savefig.facecolor": BG,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "grid.alpha": 0.85,
            "axes.axisbelow": True,
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial", "sans-serif"],
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 120,
            "savefig.dpi": 180,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save(fig, stem: str):
    FIG.mkdir(parents=True, exist_ok=True)
    DOCFIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        p = FIG / f"{stem}.{ext}"
        fig.savefig(p, bbox_inches="tight", facecolor=BG, edgecolor="none")
        shutil.copy2(p, DOCFIG / p.name)
    plt.close(fig)
    print(f"  wrote {stem}.png/.pdf")


def binomial_ste(p: float, n: int) -> float:
    if n <= 0:
        return float("nan")
    return math.sqrt(max(p, 0.0) * max(1.0 - p, 0.0) / n)


def load_json(path: Path):
    return json.loads(path.read_text())


def match_fedlock(meetings: pd.DataFrame) -> pd.DataFrame:
    fl = load_json(ROOT / "data/raw/fedlock/data.json")
    pcs_list = [s for s in fl["speeches"] if s.get("st") == "press_conference"]
    pcs = {s["d"]: s for s in pcs_list}

    def parse_d(d: str):
        return datetime.strptime(d, "%Y-%m-%d")

    title_date_index: dict[str, list] = {}
    for s in pcs_list:
        tt = s.get("tt") or ""
        mtitle = re.search(r"(20\d{2}-\d{2}-\d{2})", tt)
        if mtitle:
            title_date_index.setdefault(mtitle.group(1), []).append(s)

    rows = []
    for d in meetings["date"].astype(str).unique():
        chosen = None
        match_via = None
        if d in title_date_index:
            chosen = title_date_index[d][0]
            match_via = "title_date"
        else:
            for delta in (0, 1, -1, 2):
                cand = (parse_d(d) + timedelta(days=delta)).strftime("%Y-%m-%d")
                if cand in pcs:
                    chosen = pcs[cand]
                    match_via = f"d_field_delta_{delta}"
                    break
        if chosen is None:
            continue
        rows.append(
            {
                "date": d,
                "fedlock_m": float(chosen["m"]),
                "fedlock_ma": float(chosen["ma"]),
                "fedlock_s": float(chosen["s"]),
                "fedlock_match_via": match_via,
            }
        )
    return pd.DataFrame(rows)


def fig_gate3(meetings: pd.DataFrame, scores: pd.DataFrame, gates: dict):
    g3 = gates["gates"]["3_action_ranking"]
    df = meetings.merge(scores, on="date", how="inner")
    df = df[
        (df["is_scheduled"] == True)
        & (df["exclude_main"] == False)
        & ~df["date"].astype(str).isin(CRISIS)
    ].copy()
    df["is_action"] = df["y_action"] != 0

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2), sharey=False)
    panels = [
        ("score", "BT statement score", g3["primary"]["action_days"], g3["primary"]["all_scheduled"]),
        (
            "score_jev",
            "score_jev (Score pass)",
            g3["secondary_score_jev"]["action_days"],
            g3["secondary_score_jev"]["all_scheduled"],
        ),
    ]
    for ax, (col, ylab, act_stats, all_stats) in zip(axes, panels):
        sub = df.dropna(subset=[col, "d_same"])
        for mask, color, label, marker in (
            (sub["is_action"], C_ACTION, "Action (hike/cut)", "o"),
            (~sub["is_action"], C_HOLD, "Hold", "s"),
        ):
            s = sub[mask]
            ax.scatter(
                s["d_same"],
                s[col],
                c=color,
                marker=marker,
                s=36,
                alpha=0.85,
                edgecolors="white",
                linewidths=0.4,
                label=f"{label} (n={len(s)})",
                zorder=3,
            )
        ax.axhline(0 if col == "score" else sub[col].median(), color=GRID, lw=0.8)
        ax.axvline(0, color=GRID, lw=0.8)
        ax.set_xlabel("Same-day funds-target change, d_same (pp)")
        ax.set_ylabel(ylab)
        rho_a, n_a, ste_a = act_stats["rho"], act_stats["n"], act_stats["ste"]
        rho_all, n_all, ste_all = all_stats["rho"], all_stats["n"], all_stats["ste"]
        ax.set_title(
            f"Action days: ρ={rho_a:.2f} (STE {ste_a:.2f}, n={n_a})\n"
            f"All scheduled: ρ={rho_all:.2f} (STE {ste_all:.2f}, n={n_all})",
            loc="left",
            fontsize=9,
            color=MUTED,
        )
        ax.legend(frameon=False, loc="best")
    fig.suptitle("Gate 3 — Text scores vs same-day policy action", fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "gate3_score_vs_dsame")


def fig_gate1_2(gates: dict, haiku: dict):
    inv = gates["inversion_tables"]
    strata = [("extreme", "A · extreme"), ("shah", "B · Shah"), ("adjacent", "C · adjacent")]
    jev_p, jev_ste, jev_n = [], [], []
    hai_p, hai_ste, hai_n = [], [], []
    labels = []
    for key, lab in strata:
        labels.append(lab)
        p, n = inv[key]["inversion_rate"], inv[key]["n"]
        jev_p.append(p)
        jev_n.append(n)
        jev_ste.append(inv[key].get("ste_inversion") or binomial_ste(p, n))
        hi = haiku["haiku_inversion"][key]
        hp, hn = hi["inversion_rate"], hi["n"]
        hai_p.append(hp)
        hai_n.append(hn)
        hai_ste.append(binomial_ste(hp, hn))

    x = np.arange(len(labels))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(x - w / 2, jev_p, w, yerr=jev_ste, color=C_JEV, ecolor=INK, capsize=3, label="Jev", alpha=0.9)
    ax.bar(x + w / 2, hai_p, w, yerr=hai_ste, color=C_HAIKU, ecolor=INK, capsize=3, label="Haiku 4.5", alpha=0.85)
    ax.axhline(0.05, color=C_ACCENT, ls="--", lw=1, label="Gate 1 pass line (0.05)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Inversion rate")
    ax.set_ylim(0, max(0.35, max(jev_p + hai_p) + 0.08))
    for i, (jp, jn, hp, hn) in enumerate(zip(jev_p, jev_n, hai_p, hai_n)):
        ax.text(i - w / 2, jp + jev_ste[i] + 0.008, f"n={jn}", ha="center", va="bottom", fontsize=7, color=MUTED)
        ax.text(i + w / 2, hp + hai_ste[i] + 0.008, f"n={hn}", ha="center", va="bottom", fontsize=7, color=MUTED)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title(
        "Gates 1–2 — Inversion rate ± binomial STE by stratum\n"
        "(winner ≠ gold after averaging both presentation orders)",
        loc="left",
        fontsize=10,
    )
    fig.tight_layout()
    save(fig, "gate1_2_inversion_bars")


def fig_gate4(gates: dict):
    g4 = gates["gates"]["4_holds_vs_cuts"]
    cats = ["Cuts", "Holds", "Hikes"]
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 4.0), sharey=False)
    specs = [
        ("BT score", g4["bt"], C_ACTION),
        ("score_jev", g4["score_jev"], C_JEV),
    ]
    for ax, (title, block, color) in zip(axes, specs):
        means = [block["mean_cuts"], block["mean_holds"], block["mean_hikes"]]
        stes = [block["ste_cuts"], block["ste_holds"], block["ste_hikes"]]
        ns = [block["n_cuts"], block["n_holds"], block["n_hikes"]]
        colors = [C_CUT, C_HOLD2, C_HIKE]
        ax.bar(cats, means, yerr=stes, color=colors, ecolor=INK, capsize=3, width=0.65, alpha=0.9)
        ax.axhline(0, color=GRID, lw=0.8)
        for i, (m, s, n) in enumerate(zip(means, stes, ns)):
            y = m + (s if m >= 0 else -s)
            ax.text(i, y + (0.08 if m >= 0 else -0.08), f"n={n}", ha="center", va="bottom" if m >= 0 else "top", fontsize=8, color=MUTED)
        gap = block["gap_holds_minus_cuts"]
        gste = block["ste_gap_holds_minus_cuts"]
        ax.set_title(
            f"{title}\nHolds−cuts gap={gap:.2f} (STE {gste:.2f})",
            loc="left",
            fontsize=9,
            color=MUTED,
        )
        ax.set_ylabel("Mean score")
    fig.suptitle("Gate 4 — Mean text hawkishness by same-day action", fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "gate4_holds_cuts_hikes")


def fig_gate7(meetings: pd.DataFrame, scores: pd.DataFrame, gates: dict):
    fl = match_fedlock(meetings)
    df = meetings.merge(scores, on="date", how="left").merge(fl, on="date", how="inner")
    df = df[
        (df["is_scheduled"] == True)
        & (df["exclude_main"] == False)
        & ~df["date"].astype(str).isin(CRISIS)
        & df["score_jev"].notna()
        & df["fedlock_m"].notna()
    ].copy()
    stats = gates["gates"]["7_fedlock_consistency"]["score_jev_vs_m"]
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    ax.scatter(
        df["fedlock_m"],
        df["score_jev"],
        c=C_ACTION,
        s=28,
        alpha=0.75,
        edgecolors="white",
        linewidths=0.3,
        zorder=3,
    )
    # simple OLS guide line
    x, y = df["fedlock_m"].to_numpy(), df["score_jev"].to_numpy()
    if len(x) >= 2 and np.std(x) > 0:
        b1, b0 = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, b0 + b1 * xs, color=C_ACCENT, lw=1.2, alpha=0.85, label="OLS guide")
    ax.set_xlabel("FedLock press_conference m (raw)")
    ax.set_ylabel("score_jev (Jev Score pass)")
    ax.set_title(
        f"Gate 7 — score_jev vs published FedLock m (not a TrueSkill replica)\n"
        f"Spearman ρ={stats['rho']:.3f} (s.e. {stats['ste']:.3f}, n={stats['n']}; "
        f"95% CI [{stats['ci_low']:.3f}, {stats['ci_high']:.3f}])",
        loc="left",
        fontsize=9,
    )
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    save(fig, "gate7_fedlock_scatter")


def fig_haiku_cost_latency(haiku: dict):
    totals = haiku.get("totals") or {}
    # Prefer totals if present; else nested cost/timing
    if totals:
        cost_h = totals["haiku"]["usd"]
        cost_j = totals["jev_choice"]["usd"]
        p50_h = totals["haiku"]["latency_ms_p50"]
        p50_j = totals["jev_choice"]["latency_ms_p50"]
        n_h = totals["haiku"]["n_calls"]
        n_j = totals["jev_choice"]["n_calls"]
    else:
        cost_h = haiku["haiku_cost"]["cost_usd"]["total"]
        cost_j = haiku["jev_cost_choice_approx"]["choice_usd"]
        p50_h = haiku["haiku_timing"]["overall"]["p50"]
        p50_j = haiku["jev_timing_choice"]["p50"]
        n_h = haiku["haiku_cost"]["n_calls"]
        n_j = haiku["jev_cost_choice_approx"]["n_choice"]

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.8))
    models = ["Jev\n(Choice)", "Haiku 4.5\n(Choice)"]
    colors = [C_JEV, C_HAIKU]

    axes[0].bar(models, [cost_j, cost_h], color=colors, width=0.55, alpha=0.9)
    axes[0].set_ylabel("USD (listed API prices)")
    axes[0].set_title(f"Total Choice cost\n(n={n_j} / {n_h} calls)", loc="left", fontsize=9, color=MUTED)
    for i, v in enumerate([cost_j, cost_h]):
        axes[0].text(i, v + max(cost_h, cost_j) * 0.02, f"${v:.3f}", ha="center", va="bottom", fontsize=9)

    axes[1].bar(models, [p50_j, p50_h], color=colors, width=0.55, alpha=0.9)
    axes[1].set_ylabel("Latency p50 (ms, per call)")
    axes[1].set_title("Median per-call latency", loc="left", fontsize=9, color=MUTED)
    for i, v in enumerate([p50_j, p50_h]):
        axes[1].text(i, v + max(p50_h, p50_j) * 0.02, f"{v:.0f} ms", ha="center", va="bottom", fontsize=9)

    ratio_c = cost_h / cost_j if cost_j else float("nan")
    ratio_l = p50_h / p50_j if p50_j else float("nan")
    fig.suptitle(
        f"Haiku vs Jev — cost and latency (Choice protocol)\n"
        f"Haiku/Jev cost ×{ratio_c:.0f}; latency p50 ×{ratio_l:.1f}",
        fontsize=11,
        fontweight="bold",
        y=1.05,
    )
    fig.tight_layout()
    save(fig, "haiku_vs_jev_cost_latency")


def fig_exp3(e3: dict):
    rows = pd.DataFrame(e3["rows"])
    rows = rows[(rows.get("exclude_main", False) == False) if "exclude_main" in rows.columns else slice(None)]
    if "exclude_main" in rows.columns:
        rows = rows[rows["exclude_main"] == False]
    if "is_scheduled" in rows.columns:
        rows = rows[rows["is_scheduled"] == True]
    rows = rows.dropna(subset=["composite", "d_same"])
    corr = e3["correlations"]["vs_d_same"]
    corr_a = e3["correlations"].get("vs_d_same_action_days")

    fig, ax = plt.subplots(figsize=(5.8, 4.6))
    if "y_action" in rows.columns:
        act = rows["y_action"] != 0
    else:
        act = rows["d_same"] != 0
    ax.scatter(rows.loc[act, "d_same"], rows.loc[act, "composite"], c=C_ACTION, s=32, alpha=0.85, label=f"Action (n={act.sum()})", edgecolors="white", linewidths=0.3)
    ax.scatter(rows.loc[~act, "d_same"], rows.loc[~act, "composite"], c=C_HOLD, s=32, alpha=0.75, marker="s", label=f"Hold (n={(~act).sum()})", edgecolors="white", linewidths=0.3)
    ax.set_xlabel("d_same (pp)")
    ax.set_ylabel("Equal-weight composite Score")
    title = f"Exp. 3 — Composite vs d_same\nρ={corr['rho']:.3f} (STE {corr['ste']:.3f}, n={corr['n']})"
    if corr_a:
        title += f"\nAction days: ρ={corr_a['rho']:.3f} (STE {corr_a['ste']:.3f}, n={corr_a['n']})"
    ax.set_title(title, loc="left", fontsize=9)
    ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, "exp3_composite_vs_dsame")

    # Ablation
    abl = e3["ablations_drop_one"]
    full_rho = corr["rho"]
    labels, rhos, stes, deltas = [], [], [], []
    for k, v in abl.items():
        lab = k.replace("drop_", "").replace("_", " ")
        labels.append(lab)
        rhos.append(v["rho"])
        stes.append(v["ste"])
        deltas.append(v.get("delta_rho_vs_full", v["rho"] - full_rho))
    order = np.argsort(deltas)
    labels = [labels[i] for i in order]
    rhos = [rhos[i] for i in order]
    stes = [stes[i] for i in order]
    deltas = [deltas[i] for i in order]

    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    colors = [C_HIKE if d < 0 else C_JEV for d in deltas]
    ax.barh(labels, deltas, xerr=stes, color=colors, ecolor=INK, capsize=3, alpha=0.9, height=0.6)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel("Δρ vs full composite (vs d_same)")
    ax.set_title(
        f"Exp. 3 — Leave-one-dimension-out ablation\nFull composite ρ={full_rho:.3f} (n={corr['n']})",
        loc="left",
        fontsize=9,
    )
    for i, (d, r) in enumerate(zip(deltas, rhos)):
        ax.text(d + (0.01 if d >= 0 else -0.01), i, f"ρ={r:.2f}", va="center", ha="left" if d >= 0 else "right", fontsize=8, color=MUTED)
    fig.tight_layout()
    save(fig, "exp3_ablation")


def fig_exp4(e4: dict):
    by_era = e4["by_era"]
    keys = e4["noul_keys"]
    eras = list(by_era.keys())
    # Prefer chronological-ish order if present
    preferred = ["2020", "2022_hikes", "2023_SVB", "2023_other", "2024", "2025_26", "other"]
    eras = [e for e in preferred if e in by_era] + [e for e in eras if e not in preferred]

    short = {
        "signals_cut_soon": "Cut soon",
        "signals_higher_for_longer": "Higher-for-longer",
        "acknowledges_banking_stress": "Banking stress",
        "blames_supply_shocks": "Supply shocks",
    }
    colors = [C_CUT, C_HIKE, C_ACCENT, C_HOLD]
    x = np.arange(len(eras))
    w = 0.18
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    for i, key in enumerate(keys):
        means, stes = [], []
        for era in eras:
            block = by_era[era][key]
            n = by_era[era]["n"]
            m = block["mean"]
            sd = block.get("std") or 0.0
            ste = sd / math.sqrt(n) if n else float("nan")
            means.append(m)
            stes.append(ste)
        ax.bar(x + (i - 1.5) * w, means, w, yerr=stes, label=short.get(key, key), color=colors[i % len(colors)], ecolor=INK, capsize=2, alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{e}\n(n={by_era[e]['n']})" for e in eras], fontsize=8)
    ax.set_ylabel("Mean Noul probability")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, ncol=2, loc="upper right")
    ax.set_title("Exp. 4 — Multi-label Nouls by era (mean ± STE)", loc="left", fontsize=10)
    fig.tight_layout()
    save(fig, "exp4_noul_by_era")


def fig_exp5(e5: dict) -> bool:
    bins = e5["baseline"]["calibration"]["bins"]
    nonempty = [b for b in bins if b.get("n")]
    if not nonempty:
        print("  SKIP exp5_reliability — no non-empty calibration bins")
        return False
    # Reliability diagram: all bins with n>0; also show empty as light markers optional
    xs, ys, ns = [], [], []
    for b in bins:
        if not b.get("n"):
            continue
        xs.append(b["mean_p"])
        ys.append(b["emp_freq"])
        ns.append(b["n"])
    ece = e5["baseline"]["calibration"]["ece"]
    n_pairs = e5["baseline"]["n_pairs"]

    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    ax.plot([0, 1], [0, 1], ls="--", color=GRID, lw=1.2, label="Perfect calibration")
    ax.scatter(xs, ys, s=[40 + 4 * n for n in ns], c=C_ACTION, zorder=3, edgecolors="white", label="Occupied bins")
    for x, y, n in zip(xs, ys, ns):
        ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(6, 6), fontsize=8, color=MUTED)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Mean reported p_gold (bin)")
    ax.set_ylabel("Empirical non-inversion frequency")
    ax.set_title(
        f"Exp. 5 — Reliability (baseline criterion)\n"
        f"ECE={ece:.3f}; n_pairs={n_pairs}; occupied bins={len(nonempty)}/{len(bins)}",
        loc="left",
        fontsize=9,
    )
    ax.legend(frameon=False, loc="lower right")
    # Note if mass is concentrated
    if len(nonempty) == 1:
        ax.text(
            0.05,
            0.85,
            "Note: all mass in top bin\n(easy Stratum A pairs;\np_gold≈1).",
            transform=ax.transAxes,
            fontsize=8,
            color=MUTED,
            va="top",
        )
    fig.tight_layout()
    save(fig, "exp5_reliability")
    return True


def fig_exp6(e6: dict):
    items = [it for it in e6["items"] if it.get("ok", True)]
    p = np.array([it["p_gold"] for it in items], dtype=float)
    inv = e6["inversion"]
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    ax.hist(p, bins=np.linspace(0, 1, 11), color=C_ACTION, edgecolor="white", alpha=0.9)
    ax.axvline(p.mean(), color=C_ACCENT, lw=1.4, label=f"Mean p_gold={p.mean():.2f}")
    ax.set_xlabel("p_gold (probability on gold span)")
    ax.set_ylabel("Count of items")
    ax.set_title(
        f"Exp. 6 — Span Choice p_gold distribution\n"
        f"Inversion={inv['rate']:.2f} (STE {inv['ste']:.2f}, n={inv['n']})",
        loc="left",
        fontsize=9,
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, "exp6_span_pgold")


def fig_exp7(e7: dict):
    metrics = [
        ("Inversion\n(absolute)", e7["inversion_absolute"]),
        ("Inversion\n(macro)", e7["inversion_macro"]),
        ("Winner agreement\n(abs vs macro)", e7["agreement_abs_vs_macro_winners"]),
    ]
    labels = [m[0] for m in metrics]
    rates = [m[1]["rate"] for m in metrics]
    stes = [m[1]["ste"] for m in metrics]
    ns = [m[1]["n"] for m in metrics]
    colors = [C_HOLD, C_ACTION, C_JEV]

    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.bar(labels, rates, yerr=stes, color=colors, ecolor=INK, capsize=3, width=0.55, alpha=0.9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Rate")
    for i, (r, n) in enumerate(zip(rates, ns)):
        ax.text(i, r + 0.03, f"{r:.2f}\nn={n}", ha="center", va="bottom", fontsize=8, color=MUTED)
    ax.set_title(
        "Exp. 7 — Macro-conditioned vs absolute Choice\n"
        f"Mean p_gold abs={e7['mean_p_gold_absolute']:.3f}; macro={e7['mean_p_gold_macro']:.3f}",
        loc="left",
        fontsize=9,
    )
    fig.tight_layout()
    save(fig, "exp7_macro_agreement")


def write_captions(meta: dict):
    lines = [
        "# Figure captions",
        "",
        "Economist-voice captions for `results/figures/` (also copied to `docs/figures/`).",
        "All quantities are from the frozen `fedjev-2026-09-20` run artifacts; STE denotes the reported standard error.",
        "",
    ]
    for stem, cap in meta.items():
        lines.append(f"## `{stem}.png`")
        lines.append("")
        lines.append(cap)
        lines.append("")
    (FIG / "CAPTIONS.md").write_text("\n".join(lines))
    shutil.copy2(FIG / "CAPTIONS.md", DOCFIG / "CAPTIONS.md")
    print("  wrote CAPTIONS.md")


def main():
    style()
    FIG.mkdir(parents=True, exist_ok=True)
    DOCFIG.mkdir(parents=True, exist_ok=True)

    meetings = pd.read_parquet(ROOT / "data/labels/meetings.parquet")
    scores = pd.read_csv(ROOT / "results/statement_scores.csv")
    gates = load_json(RES / "gates.json")
    haiku = load_json(RES / "haiku_comparison.json")
    e3 = load_json(RES / "experiments/exp3_composite.json")
    e4 = load_json(RES / "experiments/exp4_nouls.json")
    e5 = load_json(RES / "experiments/exp5_calibration.json")
    e6 = load_json(RES / "experiments/exp6_span_choice.json")
    e7 = load_json(RES / "experiments/exp7_macro_relative.json")

    print("Generating figures…")
    fig_gate3(meetings, scores, gates)
    fig_gate1_2(gates, haiku)
    fig_gate4(gates)
    fig_gate7(meetings, scores, gates)
    fig_haiku_cost_latency(haiku)
    fig_exp3(e3)
    fig_exp4(e4)
    did_exp5 = fig_exp5(e5)
    fig_exp6(e6)
    fig_exp7(e7)

    g3 = gates["gates"]["3_action_ranking"]
    g4 = gates["gates"]["4_holds_vs_cuts"]
    g7 = gates["gates"]["7_fedlock_consistency"]
    inv = gates["inversion_tables"]
    corr = e3["correlations"]["vs_d_same"]

    captions = {
        "gate3_score_vs_dsame": (
            f"**Axes:** same-day funds-target change (`d_same`, pp) vs BT statement score (left) and "
            f"`score_jev` (right). **Sample:** scheduled meetings excluding crisis days; action days marked navy, holds gray. "
            f"**Headline:** on action days, BT ρ={g3['primary']['action_days']['rho']:.2f} "
            f"(STE {g3['primary']['action_days']['ste']:.2f}, n={g3['primary']['action_days']['n']}); "
            f"pooled scheduled BT ρ={g3['primary']['all_scheduled']['rho']:.2f} "
            f"(STE {g3['primary']['all_scheduled']['ste']:.2f}, n={g3['primary']['all_scheduled']['n']}). "
            f"**Read:** textual hawkishness tracks the sign and size of same-day policy moves when the Committee acts; "
            f"holds compress `d_same` to zero and cannot identify stance."
        ),
        "gate1_2_inversion_bars": (
            f"**Axes:** inversion rate (winner ≠ gold after both orders) ± binomial STE by stratum. "
            f"**n:** A={inv['extreme']['n']}, B={inv['shah']['n']}, C={inv['adjacent']['n']} (Jev and Haiku on the same pairs). "
            f"**Headline:** Stratum A inversion is 0 for both models (Gate 1 pass line 0.05); Stratum B is a harder sentence stress test "
            f"(Jev {inv['shah']['inversion_rate']:.2f}, Haiku {haiku['haiku_inversion']['shah']['inversion_rate']:.2f}). "
            f"**Read:** construct validity on easy document pairs is shared; residual error concentrates in Shah sentences."
        ),
        "gate4_holds_cuts_hikes": (
            f"**Axes:** mean BT score and `score_jev` ± STE by same-day action class (cuts / holds / hikes). "
            f"**n (BT):** cuts={g4['bt']['n_cuts']}, holds={g4['bt']['n_holds']}, hikes={g4['bt']['n_hikes']}; "
            f"**n (score_jev):** {g4['score_jev']['n_cuts']}/{g4['score_jev']['n_holds']}/{g4['score_jev']['n_hikes']}. "
            f"**Headline:** holds−cuts gap (BT)={g4['bt']['gap_holds_minus_cuts']:.2f} "
            f"(STE {g4['bt']['ste_gap_holds_minus_cuts']:.2f}); "
            f"`score_jev` gap={g4['score_jev']['gap_holds_minus_cuts']:.2f} "
            f"(STE {g4['score_jev']['ste_gap_holds_minus_cuts']:.2f}). "
            f"**Read:** when the target is unchanged, `d_same` is silent; text scores still place holds above cuts on average—evidence that "
            f"same-day rate changes are an incomplete label for textual hawkishness under holds."
        ),
        "gate7_fedlock_scatter": (
            f"**Axes:** published FedLock press-conference raw TrueSkill mean `m` vs this repository’s "
            f"`score_jev` on matched scheduled meetings. "
            f"**n:** {g7['score_jev_vs_m']['n']} matched (title-date preferred; else `d` offsets 0/+1/−1/+2). "
            f"**Headline:** Spearman ρ={g7['score_jev_vs_m']['rho']:.3f} "
            f"(s.e. {g7['score_jev_vs_m']['ste']:.3f}; 95% CI "
            f"[{g7['score_jev_vs_m']['ci_low']:.3f}, {g7['score_jev_vs_m']['ci_high']:.3f}]). "
            f"**Read:** two independent *text* scoring systems agree on meeting-day hawkishness. "
            f"Gate 7 external consistency, not a TrueSkill or macro-conditioned FedLock replication "
            f"(different corpus, judge, and aggregator; see `results/fedlock_fidelity.md`). "
            f"The separate TrueSkill replica is `results/fedlock_replica/FINDINGS.md`."
        ),
        "haiku_vs_jev_cost_latency": (
            f"**Axes:** listed Choice API cost (USD) and per-call latency p50 (ms) for Jev vs Claude Haiku 4.5 on the same 524 Choice calls. "
            f"**Headline:** Jev Choice ≈ ${haiku.get('totals',{}).get('jev_choice',{}).get('usd', haiku['jev_cost_choice_approx']['choice_usd']):.3f} "
            f"and p50 ≈ {haiku.get('totals',{}).get('jev_choice',{}).get('latency_ms_p50', haiku['jev_timing_choice']['p50']):.0f} ms vs "
            f"Haiku ≈ ${haiku.get('totals',{}).get('haiku',{}).get('usd', haiku['haiku_cost']['cost_usd']['total']):.3f} "
            f"and p50 ≈ {haiku.get('totals',{}).get('haiku',{}).get('latency_ms_p50', haiku['haiku_timing']['overall']['p50']):.0f} ms. "
            f"**Read:** winner agreement is nearly tied on Strata A/C; dollars and latency are separate axes favoring Jev on this protocol."
        ),
        "exp3_composite_vs_dsame": (
            f"**Axes:** equal-weight four-dimension composite Score vs `d_same`. "
            f"**n:** {corr['n']} scheduled main-analysis meetings. "
            f"**Headline:** Spearman ρ={corr['rho']:.3f} (STE {corr['ste']:.3f}). "
            f"**Read:** a structured absolute Score of communicated stance co-moves with same-day policy actions, especially on action days; "
            f"holds again pin `d_same` at zero."
        ),
        "exp3_ablation": (
            f"**Axes:** change in Spearman ρ vs `d_same` when dropping one composite dimension (leave-one-out). "
            f"**n:** {corr['n']}. Full composite ρ={corr['rho']:.3f}. "
            f"**Read:** negative Δρ means the dropped dimension carried association with the rate move; positive Δρ means the remaining three "
            f"fit `d_same` at least as well—useful for interpreting which atomic construct does the work under equal weights."
        ),
        "exp4_noul_by_era": (
            f"**Axes:** mean Noul probability ± STE by era for four non-exclusive labels "
            f"({', '.join(e4['noul_keys'])}). "
            f"**n:** per-era counts annotated under ticks. "
            f"**Read:** label mass shifts with the cycle—higher-for-longer during the hiking era; banking-stress mass around SVB—without forcing mutual exclusivity."
        ),
        "exp6_span_pgold": (
            f"**Axes:** histogram of p_gold on the gold span across Exp. 6 items. "
            f"**n:** {e6['inversion']['n']} items. "
            f"**Headline:** inversion={e6['inversion']['rate']:.2f} (STE {e6['inversion']['ste']:.2f}); "
            f"mean p_gold={e6['mean_p_gold']:.2f}. "
            f"**Read:** under this distractor design, span Choice is near chance—evidence that document-level signal does not automatically transfer to short-span selection."
        ),
        "exp7_macro_agreement": (
            f"**Axes:** inversion rates under absolute vs macro-conditioned instructions, and winner agreement between the two arms (± binomial STE). "
            f"**n:** {e7['agreement_abs_vs_macro_winners']['n']} Stratum A pairs. "
            f"**Headline:** both inversions=0; winner agreement=1.00. "
            f"**Read:** on rate-extreme gold pairs, providing macro context does not overturn the absolute hawkishness ordering—limited diagnostic, not a pure test of macro-conditional judgment."
        ),
    }
    if did_exp5:
        ece = e5["baseline"]["calibration"]["ece"]
        captions["exp5_reliability"] = (
            f"**Axes:** reliability diagram—bin mean p_gold vs empirical non-inversion frequency (baseline criterion). "
            f"**n:** {e5['baseline']['n_pairs']} Stratum A pairs; ECE={ece:.3f}. "
            f"**Read:** pairs are easy (p_gold≈1), so mass sits in the top bin; calibration is trivially good here and should not be over-generalized to hard pairs."
        )
    else:
        captions["exp5_reliability"] = (
            "**Skipped:** no non-empty calibration bins in `exp5_calibration.json`."
        )

    write_captions(captions)
    print("Done.")


if __name__ == "__main__":
    main()
