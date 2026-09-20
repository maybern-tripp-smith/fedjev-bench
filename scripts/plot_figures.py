#!/usr/bin/env python3
"""Publication figures for fedjev-bench (light paper style).

Reads only repository JSON/CSV. Experiments 3–4 have no artifacts and are
not plotted. Calibration / p(gold) / FedLock m-vs-ma panels use the main
Choice and Gate 7 series that are already in results/.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "figures"
DOCS = ROOT / "docs" / "figures"
CRISIS = {"2020-03-03", "2020-03-15"}
SVB = "2023-03-22"

CREAM = "#f7f5f0"
NAVY = "#1a365d"
RUST = "#9b2c2c"
TEAL = "#276749"
HOLD = "#718096"
INK = "#1a1a1a"
MUTED = "#4a5568"
EDGE = "#b8b2a6"
HAIKU = "#744210"


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "STIXGeneral", "Times New Roman", "Times"],
            "mathtext.fontset": "stix",
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "figure.facecolor": CREAM,
            "savefig.facecolor": CREAM,
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": EDGE,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "lines.linewidth": 1.1,
        }
    )


def load_json(path: Path):
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        dest = OUT / f"{stem}.{ext}"
        fig.savefig(dest, dpi=200, bbox_inches="tight", pad_inches=0.18)
        shutil.copy2(dest, DOCS / f"{stem}.{ext}")
    plt.close(fig)


def annotate_rho(ax, rho, ste, n, loc="lower right") -> None:
    txt = f"ρ = {rho:+.3f}\nSTE {ste:.3f} · n = {n}"
    va, ha = "bottom", "right"
    x, y = 0.97, 0.06
    if loc == "upper left":
        va, ha, x, y = "top", "left", 0.04, 0.96
    if loc == "lower left":
        va, ha, x, y = "bottom", "left", 0.04, 0.06
    ax.text(
        x,
        y,
        txt,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=8,
        color=MUTED,
        linespacing=1.35,
    )


def action_mask(d: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    return d > 0, d == 0, d < 0


def scatter_by_action(ax, x, y, d_same, dates, yerr=None) -> None:
    hike, hold, cut = action_mask(d_same)
    svb = dates.astype(str) == SVB
    groups = (
        (hold, "o", HOLD, "Hold"),
        (cut, "v", RUST, "Cut"),
        (hike, "^", NAVY, "Hike"),
    )
    for mask, marker, color, label in groups:
        if not mask.any():
            continue
        ax.scatter(
            x[mask],
            y[mask],
            marker=marker,
            s=36,
            c=color,
            edgecolors="white",
            linewidths=0.4,
            label=label,
            zorder=3,
        )
    if yerr is not None:
        ax.errorbar(
            x,
            y,
            yerr=yerr,
            fmt="none",
            ecolor=EDGE,
            elinewidth=0.7,
            capsize=0,
            zorder=2,
        )
    if svb.any():
        ax.scatter(
            x[svb],
            y[svb],
            s=90,
            facecolors="none",
            edgecolors=TEAL,
            linewidths=1.2,
            label="2023-03-22 (SVB flag)",
            zorder=4,
        )


def load_meetings() -> pd.DataFrame:
    pq = ROOT / "data/labels/meetings.parquet"
    if pq.exists():
        m = pd.read_parquet(pq)
    else:
        m = pd.read_csv(ROOT / "data/labels/meetings.csv")
    m["date"] = m["date"].astype(str)
    return m


def match_fedlock(meetings: pd.DataFrame) -> pd.DataFrame:
    fl = load_json(ROOT / "data/raw/fedlock/data.json")
    pcs_list = [s for s in fl["speeches"] if s["st"] == "press_conference"]
    pcs = {s["d"]: s for s in pcs_list}
    title_date_index: dict[str, list] = {}
    for s in pcs_list:
        mtitle = re.search(r"(20\d{2}-\d{2}-\d{2})", s.get("tt") or "")
        if mtitle:
            title_date_index.setdefault(mtitle.group(1), []).append(s)

    def parse_d(d: str) -> datetime:
        return datetime.strptime(d, "%Y-%m-%d")

    rows = []
    for d in meetings["date"].unique():
        d = str(d)
        chosen = None
        if d in title_date_index:
            chosen = title_date_index[d][0]
        else:
            for delta in (0, 1, -1, 2):
                cand = (parse_d(d) + timedelta(days=delta)).strftime("%Y-%m-%d")
                if cand in pcs:
                    chosen = pcs[cand]
                    break
        if chosen is None:
            continue
        rows.append(
            {
                "date": d,
                "fedlock_m": float(chosen["m"]),
                "fedlock_ma": float(chosen["ma"]),
                "fedlock_s": float(chosen["s"]),
            }
        )
    return pd.DataFrame(rows)


def main_slices(meetings: pd.DataFrame, scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = meetings.merge(scores, on="date", how="left")
    base = (m["is_scheduled"] == True) & (m["exclude_main"] == False) & ~m["date"].isin(CRISIS)
    bt = m.loc[base & m["score"].notna()].copy()
    jev = m.loc[base & m["score_jev"].notna()].copy()
    return bt, jev


def fig_score_vs_d_same(bt: pd.DataFrame, jev: pd.DataFrame, gates: dict) -> None:
    g3 = gates["gates"]["3_action_ranking"]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.55), sharex=True)
    ax = axes[0]
    scatter_by_action(ax, bt["d_same"], bt["score"], bt["d_same"], bt["date"])
    ax.axvline(0, color=EDGE, linewidth=0.8)
    ax.axhline(0, color=EDGE, linewidth=0.8)
    ax.set_xlabel(r"$d_{\mathrm{same}}$ (percentage points)")
    ax.set_ylabel("Bradley–Terry score")
    ax.set_title("BT vs same-day target change")
    rho = g3["primary"]["all_scheduled"]
    annotate_rho(ax, rho["rho"], rho["ste"], rho["n"], "upper left")
    ax.legend(loc="lower right", handletextpad=0.3, borderaxespad=0.2)

    ax = axes[1]
    scatter_by_action(ax, jev["d_same"], jev["score_jev"], jev["d_same"], jev["date"])
    ax.axvline(0, color=EDGE, linewidth=0.8)
    ax.set_xlabel(r"$d_{\mathrm{same}}$ (percentage points)")
    ax.set_ylabel(r"$\mathrm{score}_{jev}$")
    ax.set_title("Direct Score vs same-day target change")
    rho = g3["secondary_score_jev"]["all_scheduled"]
    annotate_rho(ax, rho["rho"], rho["ste"], rho["n"], "upper left")
    fig.tight_layout()
    save(fig, "score_vs_d_same")


def fig_gate3_rho(gates: dict) -> None:
    g3 = gates["gates"]["3_action_ranking"]["primary"]
    rows = [
        ("All scheduled", g3["all_scheduled"]),
        ("Action days", g3["action_days"]),
        ("Holds vs dissent net", g3["hold_vs_dissent_net"]),
        (r"Holds vs $d_{2y}$", g3["hold_vs_d_2y"]),
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    y = np.arange(len(rows))[::-1]
    for yi, (lab, blk) in zip(y, rows):
        lo, hi, rho = blk["ci_low"], blk["ci_high"], blk["rho"]
        ax.plot([lo, hi], [yi, yi], color=NAVY, linewidth=1.4, solid_capstyle="round")
        ax.plot(rho, yi, "o", color=NAVY, markersize=6)
        ax.text(1.02, yi, f"n={blk['n']}", transform=ax.get_yaxis_transform(), va="center", fontsize=8, color=MUTED)
    ax.axvline(0, color=EDGE, linewidth=0.8, label=None)
    ax.axvline(0.30, color=TEAL, linewidth=0.9, linestyle="--", label="Pass line +0.30")
    ax.axvline(0.46, color=RUST, linewidth=0.9, linestyle=":", label="jsort published +0.46")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Spearman ρ (bootstrap 95% CI)")
    ax.set_xlim(-0.75, 1.15)
    ax.set_title("Gate 3 — BT rank agreement")
    ax.legend(loc="lower right")
    fig.tight_layout()
    save(fig, "gate3_rho")


def fig_gate4_means(gates: dict) -> None:
    g4 = gates["gates"]["4_holds_vs_cuts"]
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.45))
    specs = (
        (axes[0], g4["bt"], "Bradley–Terry"),
        (axes[1], g4["score_jev"], r"$\mathrm{score}_{jev}$"),
    )
    order = [
        ("mean_cuts", "ste_cuts", "n_cuts", "Cuts", RUST),
        ("mean_holds", "ste_holds", "n_holds", "Holds", HOLD),
        ("mean_hikes", "ste_hikes", "n_hikes", "Hikes", NAVY),
    ]
    for ax, block, title in specs:
        xs = np.arange(3)
        means = [block[k] for k, _, _, _, _ in order]
        stes = [block[s] for _, s, _, _, _ in order]
        colors = [c for *_, c in order]
        ax.bar(xs, means, color=colors, width=0.62, edgecolor="white", linewidth=0.6)
        ax.errorbar(xs, means, yerr=stes, fmt="none", ecolor=INK, elinewidth=1.0, capsize=3)
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{lab}\nn={block[n]}" for *_, n, lab, _ in order])
        ax.axhline(0, color=EDGE, linewidth=0.8)
        ax.set_ylabel("Mean text score")
        ax.set_title(title)
        gap, gste = block["gap_holds_minus_cuts"], block["ste_gap_holds_minus_cuts"]
        ax.text(
            0.03,
            0.96,
            f"holds − cuts = {gap:+.3f}\nSTE {gste:.3f}",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
            color=MUTED,
        )
    fig.tight_layout()
    save(fig, "gate4_means")


def fig_gate5_d90(bt: pd.DataFrame, jev: pd.DataFrame, gates: dict) -> None:
    g5 = gates["gates"]["5_forward_path"]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.55), sharex=True)
    for ax, df, ycol, title, blk in (
        (axes[0], bt, "score", "BT vs $d_{90}$", g5["bt"]),
        (axes[1], jev, "score_jev", r"$\mathrm{score}_{jev}$ vs $d_{90}$", g5["score_jev"]),
    ):
        sub = df[df["d_90"].notna() & df[ycol].notna()]
        scatter_by_action(ax, sub["d_90"], sub[ycol], sub["d_same"], sub["date"])
        ax.axvline(0, color=EDGE, linewidth=0.8)
        if ycol == "score":
            ax.axhline(0, color=EDGE, linewidth=0.8)
        ax.set_xlabel(r"$d_{90}$ (pp, t to t+90)")
        ax.set_ylabel("BT score" if ycol == "score" else r"$\mathrm{score}_{jev}$")
        ax.set_title(title)
        annotate_rho(ax, blk["rho"], blk["ste"], blk["n"], "upper left")
    axes[0].legend(loc="lower right", handletextpad=0.3)
    fig.tight_layout()
    save(fig, "gate5_d90")


def fig_gate7(bt: pd.DataFrame, jev: pd.DataFrame, fl: pd.DataFrame, gates: dict) -> None:
    g7 = gates["gates"]["7_fedlock_consistency"]
    bt2 = bt.merge(fl, on="date", how="inner")
    jev2 = jev.merge(fl, on="date", how="inner")
    panels = (
        (bt2, "score", "fedlock_m", "BT vs raw $m$", g7["bt_vs_m"]),
        (bt2, "score", "fedlock_ma", "BT vs era-adj. $ma$", g7["bt_vs_ma"]),
        (jev2, "score_jev", "fedlock_m", r"$\mathrm{score}_{jev}$ vs raw $m$", g7["score_jev_vs_m"]),
        (jev2, "score_jev", "fedlock_ma", r"$\mathrm{score}_{jev}$ vs era-adj. $ma$", g7["score_jev_vs_ma"]),
    )
    fig, axes = plt.subplots(2, 2, figsize=(8.0, 7.0))
    for ax, (df, ycol, xcol, title, blk) in zip(axes.ravel(), panels):
        sub = df[df[xcol].notna() & df[ycol].notna()]
        scatter_by_action(ax, sub[xcol], sub[ycol], sub["d_same"], sub["date"])
        ax.set_xlabel("FedLock " + ("$m$" if xcol.endswith("_m") else "$ma$"))
        ax.set_ylabel("BT score" if ycol == "score" else r"$\mathrm{score}_{jev}$")
        ax.set_title(title)
        annotate_rho(ax, blk["rho"], blk["ste"], blk["n"], "upper left")
    axes[0, 1].legend(loc="lower right", handletextpad=0.3)
    fig.tight_layout()
    save(fig, "gate7_fedlock")


def fig_inversion(gates: dict, haiku: dict) -> None:
    inv = gates["inversion_tables"]
    order = [("extreme", "A extreme"), ("shah", "B Shah"), ("adjacent", "C adjacent")]
    x = np.arange(len(order))
    jev_p = [inv[k]["inversion_rate"] for k, _ in order]
    jev_e = [inv[k]["ste_inversion"] for k, _ in order]
    hk = haiku["haiku_inversion"]
    hk_p = [hk[k]["inversion_rate"] for k, _ in order]
    # binomial STE for Haiku
    hk_e = []
    for k, _ in order:
        p, n = hk[k]["inversion_rate"], hk[k]["n"]
        hk_e.append(float(np.sqrt(p * (1 - p) / n)))

    fig, ax = plt.subplots(figsize=(6.8, 3.5))
    w = 0.36
    ax.bar(x - w / 2, jev_p, w, color=NAVY, label="Jev 1.13.0", edgecolor="white")
    ax.bar(x + w / 2, hk_p, w, color=HAIKU, label="Haiku 4.5", edgecolor="white")
    ax.errorbar(x - w / 2, jev_p, yerr=jev_e, fmt="none", ecolor=INK, elinewidth=1.0, capsize=3)
    ax.errorbar(x + w / 2, hk_p, yerr=hk_e, fmt="none", ecolor=INK, elinewidth=1.0, capsize=3)
    for xi, p, e in ((x[0] - w / 2, jev_p[0], jev_e[0]), (x[0] + w / 2, hk_p[0], hk_e[0])):
        ax.plot(xi, p, "o", color=INK, markersize=3.5, zorder=4)
    ax.axhline(0.05, color=TEAL, linestyle="--", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{lab}\nn={inv[k]['n']}" for k, lab in order])
    ax.set_ylabel("Inversion rate")
    ax.set_ylim(0, 0.32)
    ax.set_title("Easy-pair and stress-test inversion")
    ax.legend(loc="upper right")
    ax.text(0.02, 0.05, "Gate 1 pass line 0.05", color=TEAL, fontsize=7.5, transform=ax.get_xaxis_transform())
    fig.tight_layout()
    save(fig, "inversion_rates")


def fig_accuracy_vs_chance(gates: dict) -> None:
    inv = gates["inversion_tables"]
    order = [("extreme", "A extreme"), ("shah", "B Shah"), ("adjacent", "C adjacent")]
    acc = [1.0 - inv[k]["inversion_rate"] for k, _ in order]
    ste = [inv[k]["ste_inversion"] for k, _ in order]
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    x = np.arange(len(order))
    ax.bar(x, acc, color=NAVY, width=0.55, edgecolor="white")
    ax.errorbar(x, acc, yerr=ste, fmt="none", ecolor=INK, elinewidth=1.0, capsize=3)
    ax.axhline(0.5, color=RUST, linestyle="--", linewidth=1.0)
    ax.set_ylim(0, 1.05)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{lab}\nn={inv[k]['n']}" for k, lab in order])
    ax.set_ylabel("Accuracy (1 − inversion)")
    ax.set_title("Choice accuracy versus chance")
    ax.text(2.15, 0.52, "chance = 0.5", color=RUST, fontsize=8, ha="right")
    fig.tight_layout()
    save(fig, "accuracy_vs_chance")


def fig_p_gold(judgments: list[dict]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(8.4, 2.95), sharey=True)
    mapping = (("extreme", "A extreme"), ("shah", "B Shah"), ("adjacent", "C adjacent"))
    bins = np.linspace(0, 1, 11)
    for ax, (src, lab) in zip(axes, mapping):
        vals = [j["p_gold"] for j in judgments if j["source"] == src and j.get("p_gold") is not None]
        ax.hist(vals, bins=bins, color=NAVY, edgecolor="white", linewidth=0.5)
        ax.axvline(0.5, color=RUST, linestyle="--", linewidth=0.9)
        ax.set_title(f"{lab} (n={len(vals)})")
        ax.set_xlabel(r"$p(\mathrm{gold})$")
        ax.set_xlim(0, 1)
    axes[0].set_ylabel("Pairs")
    fig.tight_layout()
    save(fig, "p_gold")


def fig_reliability(judgments: list[dict], gates: dict) -> None:
    """Confidence diagnostic: gold frequency is 1 by construction of the gold set.

    A classical reliability curve versus an independent outcome is not identified
    from pair_judgments (inversion is a function of the same p). ECE here is
    bin-weighted |1 − mean p(gold)| on Stratum B.
    """
    shah = [j for j in judgments if j["source"] == "shah" and j.get("p_gold") is not None]
    p = np.array([j["p_gold"] for j in shah], dtype=float)
    edges = np.linspace(0, 1, 11)
    xs, ns, ece = [], [], 0.0
    n = len(p)
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi if i < 9 else p <= hi)
        if m.sum() == 0:
            continue
        xs.append(float(p[m].mean()))
        ns.append(int(m.sum()))
        ece += (m.sum() / n) * abs(1.0 - xs[-1])
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.6))
    ax = axes[0]
    ax.plot([0, 1], [0, 1], color=EDGE, linestyle="--", linewidth=1.0, label="Identity")
    ax.scatter(xs, np.ones(len(xs)), s=18 + 2.2 * np.sqrt(ns), c=NAVY, zorder=3, label="Bin (size ∝ √n)")
    for x, nn in zip(xs, ns):
        ax.text(x, 1.035, str(nn), ha="center", fontsize=7, color=MUTED)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.12)
    ax.set_xlabel(r"Mean $p(\mathrm{gold})$")
    ax.set_ylabel("Gold-set frequency")
    ax.set_title("Stratum B confidence (gold = 1)")
    ax.text(0.04, 0.12, f"ECE = {ece:.3f} · n = {n}", transform=ax.transAxes, fontsize=8, color=MUTED)
    ax.legend(loc="center right")

    ax = axes[1]
    inv = gates["inversion_tables"]
    order = [("extreme", "A"), ("shah", "B"), ("adjacent", "C")]
    x = np.arange(len(order))
    brier = [inv[k]["mean_brier"] for k, _ in order]
    ste = [inv[k]["ste_brier"] for k, _ in order]
    ax.bar(x, brier, color=NAVY, width=0.55, edgecolor="white")
    ax.errorbar(x, brier, yerr=ste, fmt="none", ecolor=INK, elinewidth=1.0, capsize=3)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{lab}\nn={inv[k]['n']}" for k, lab in order])
    ax.set_ylabel("Mean Brier")
    ax.set_title("Brier score by stratum")
    fig.tight_layout()
    save(fig, "reliability")


def fig_cost_latency(haiku: dict, cost: dict, timing: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4))
    labels = ["Jev 1.13.0", "Haiku 4.5"]
    usd = [haiku["totals"]["jev_choice"]["usd"], haiku["totals"]["haiku"]["usd"]]
    lat = [haiku["totals"]["jev_choice"]["latency_ms_mean"], haiku["totals"]["haiku"]["latency_ms_mean"]]
    colors = [NAVY, HAIKU]
    ax = axes[0]
    ax.bar(labels, usd, color=colors, width=0.55, edgecolor="white")
    ax.set_ylabel("Choice cost (USD)")
    ax.set_title("Listed Choice cost (524 calls)")
    for i, v in enumerate(usd):
        ax.text(i, v + 0.015, f"${v:.3f}", ha="center", fontsize=8, color=MUTED)
    ax.set_ylim(0, max(usd) * 1.22)
    ax = axes[1]
    ax.bar(labels, lat, color=colors, width=0.55, edgecolor="white")
    ax.set_ylabel("Mean per-call latency (ms)")
    ax.set_title("Choice latency")
    for i, v in enumerate(lat):
        ax.text(i, v + 12, f"{v:.0f} ms", ha="center", fontsize=8, color=MUTED)
    ax.set_ylim(0, max(lat) * 1.22)
    fig.tight_layout()
    save(fig, "haiku_vs_jev")


def fig_timeline(jev: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 3.35))
    d = jev.copy()
    d["dt"] = pd.to_datetime(d["date"])
    hike, hold, cut = action_mask(d["d_same"])
    for mask, marker, color, label in (
        (hold, "o", HOLD, "Hold"),
        (cut, "v", RUST, "Cut"),
        (hike, "^", NAVY, "Hike"),
    ):
        ax.scatter(d.loc[mask, "dt"], d.loc[mask, "score_jev"], marker=marker, s=28, c=color, label=label, zorder=3)
    svb = d["date"] == SVB
    if svb.any():
        ax.scatter(
            d.loc[svb, "dt"],
            d.loc[svb, "score_jev"],
            s=80,
            facecolors="none",
            edgecolors=TEAL,
            linewidths=1.2,
            label="2023-03-22 (SVB flag)",
            zorder=4,
        )
    ax.set_ylabel(r"$\mathrm{score}_{jev}$")
    ax.set_xlabel("Meeting date")
    ax.set_title("Direct Score on scheduled openings")
    ax.legend(loc="upper left", ncol=2, frameon=False)
    fig.tight_layout()
    save(fig, "score_timeline")


def fig_gate7_m_vs_ma(jev: pd.DataFrame, fl: pd.DataFrame, gates: dict) -> None:
    """Absolute vs era-adjusted FedLock (Gate 7 contrast; Exp 7 not separately run)."""
    g7 = gates["gates"]["7_fedlock_consistency"]
    jev2 = jev.merge(fl, on="date", how="inner")
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.55))
    for ax, xcol, title, blk in (
        (axes[0], "fedlock_m", r"Absolute FedLock $m$", g7["score_jev_vs_m"]),
        (axes[1], "fedlock_ma", r"Era-adjusted FedLock $ma$", g7["score_jev_vs_ma"]),
    ):
        sub = jev2[jev2[xcol].notna()]
        scatter_by_action(ax, sub[xcol], sub["score_jev"], sub["d_same"], sub["date"])
        ax.set_xlabel("FedLock score")
        ax.set_ylabel(r"$\mathrm{score}_{jev}$")
        ax.set_title(title)
        annotate_rho(ax, blk["rho"], blk["ste"], blk["n"], "upper left")
    axes[1].legend(loc="lower right", handletextpad=0.3)
    fig.tight_layout()
    save(fig, "gate7_absolute_vs_macro")


def main() -> None:
    style()
    gates = load_json(ROOT / "results/gates.json")
    haiku = load_json(ROOT / "results/haiku_comparison.json")
    cost = load_json(ROOT / "results/cost.json")
    timing = load_json(ROOT / "results/timing.json")
    scores = pd.read_csv(ROOT / "results/statement_scores.csv")
    scores["date"] = scores["date"].astype(str)
    meetings = load_meetings()
    bt, jev = main_slices(meetings, scores)
    fl = match_fedlock(meetings)
    judgments = load_jsonl(ROOT / "results/pair_judgments.jsonl")

    fig_timeline(jev)
    fig_score_vs_d_same(bt, jev, gates)
    fig_gate3_rho(gates)
    fig_inversion(gates, haiku)
    fig_accuracy_vs_chance(gates)
    fig_p_gold(judgments)
    fig_reliability(judgments, gates)
    fig_gate4_means(gates)
    fig_gate5_d90(bt, jev, gates)
    fig_gate7(bt, jev, fl, gates)
    fig_gate7_m_vs_ma(jev, fl, gates)
    fig_cost_latency(haiku, cost, timing)
    print(f"wrote figures to {OUT} and {DOCS}")
    print(f"BT n={len(bt)} score_jev n={len(jev)} fedlock matched jev={len(jev.merge(fl, on='date'))}")


if __name__ == "__main__":
    main()
