#!/usr/bin/env python3
"""Overview figures for the multi-axis Pages note.

Reads only frozen artifacts under results/multiaxis/ (CSV/JSON).
Does not call Jev, does not rewrite score JSON, does not touch gold pairs.

Writes PNG to results/multiaxis/figures/ and copies to docs/figures/.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "multiaxis"
FIG = RES / "figures"
DOCFIG = ROOT / "docs" / "figures"

BG = "#f7f5f0"
INK = "#1a1a1a"
MUTED = "#4a5568"
GRID = "#d4cfc4"
NAVY = "#1a365d"
BRICK = "#9b2c2c"
BLUE = "#2b6cb0"
GREEN = "#276749"
TERR = "#c05621"

SHORT = {
    "ax1_inflation_hawkish": "1 inflation",
    "ax2_emp_vs_infl": "2 emp. weight",
    "ax3_lookthrough": "3 look-through",
    "ax4_forward_path": "4 forward path",
    "ax5_qt_eager": "5 QT eager",
    "ax6_fci_restrictive": "6 FCI",
    "ax7_infl_vs_labor_risk": "7 infl. vs labor",
}

AXIS_ORDER = list(SHORT.keys())


def style() -> None:
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
        }
    )


def save(fig: mpl.figure.Figure, stem: str) -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    DOCFIG.mkdir(parents=True, exist_ok=True)
    dest = FIG / f"{stem}.png"
    fig.savefig(dest, bbox_inches="tight", facecolor=BG, edgecolor="none")
    shutil.copy2(dest, DOCFIG / dest.name)
    plt.close(fig)
    return dest


def load_corr(design: str) -> pd.DataFrame:
    df = pd.read_csv(RES / f"corr_{design}.csv", index_col=0)
    return df.loc[AXIS_ORDER, AXIS_ORDER]


def load_loadings(design: str) -> pd.DataFrame:
    df = pd.read_csv(RES / f"loadings_{design}.csv", index_col=0)
    return df.loc[AXIS_ORDER]


def load_ranked(axis: str, design: str) -> pd.DataFrame:
    return pd.read_csv(RES / "ranked" / f"{axis}__{design}.csv")


def load_gates() -> dict:
    return json.loads((RES / "gates.json").read_text())


def plot_heatmap(design: str) -> Path:
    corr = load_corr(design)
    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    im = ax.imshow(corr.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
    labels = [SHORT[c] for c in corr.columns]
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=40, ha="right")
    ax.set_yticklabels(labels)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = float(corr.iat[i, j])
            ax.text(
                j,
                i,
                f"{val:+.2f}",
                ha="center",
                va="center",
                fontsize=8,
                color=INK if abs(val) < 0.55 else "#ffffff",
            )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Spearman rank correlation")
    n = 95
    ax.set_title(f"Rank correlation across axes ({design}; n={n} openings)")
    fig.tight_layout()
    return save(fig, f"corr_heatmap_{design}")


def plot_pca_scatter(design: str) -> Path:
    load = load_loadings(design)
    summary = json.loads((RES / "analysis_summary.json").read_text())
    ve = summary["factor"][design]["var_explained"]
    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    colors = [NAVY, BRICK, BLUE, TERR, GREEN, MUTED, "#553c9a"]
    for i, name in enumerate(AXIS_ORDER):
        x = float(load.loc[name, "PC1"])
        y = float(load.loc[name, "PC2"])
        ax.scatter(
            [x],
            [y],
            s=70,
            color=colors[i],
            zorder=3,
            label=SHORT[name],
        )
        ax.annotate(
            str(i + 1),
            (x, y),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=8,
            color=INK,
        )
    ax.axhline(0, color=GRID, lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_xlabel(f"First principal component loading ({ve[0]*100:.1f}% of variance)")
    ax.set_ylabel(f"Second principal component loading ({ve[1]*100:.1f}% of variance)")
    ax.set_title(f"Axis loadings in the first two factors ({design}; n=95)")
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        frameon=True,
        fancybox=False,
        edgecolor=GRID,
        fontsize=8,
    )
    fig.tight_layout()
    return save(fig, f"pca_pc1_pc2_{design}")


def plot_timeseries_ax1_ax4() -> Path:
    a1 = load_ranked("ax1_inflation_hawkish", "text").sort_values("date")
    a4 = load_ranked("ax4_forward_path", "text").sort_values("date")
    a1["date"] = pd.to_datetime(a1["date"])
    a4["date"] = pd.to_datetime(a4["date"])
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.plot(a1["date"], a1["percentile"], color=NAVY, lw=1.4, label="Axis 1: more hawkish about inflation")
    ax.plot(
        a4["date"],
        a4["percentile"],
        color=TERR,
        lw=1.4,
        label="Axis 4: more explicit about the likely future path of policy",
    )
    marks = [
        ("2020-09-16", "2020-09-16 hold", (-8, 8), "right"),
        ("2022-11-02", "2022-11-02 hike", (8, 8), "left"),
    ]
    for d, lab, offset, ha in marks:
        dt = pd.Timestamp(d)
        r1 = a1.loc[a1["date"] == dt, "percentile"]
        r4 = a4.loc[a4["date"] == dt, "percentile"]
        if len(r1):
            ax.scatter([dt], [float(r1.iloc[0])], color=NAVY, s=36, zorder=4)
        if len(r4):
            ax.scatter([dt], [float(r4.iloc[0])], color=TERR, s=36, zorder=4)
        ax.axvline(dt, color=GRID, lw=0.8, ls="--")
        y = 104 if d.startswith("2020") else 96
        ax.annotate(
            lab,
            (dt, y),
            textcoords="offset points",
            xytext=offset,
            fontsize=7.5,
            color=MUTED,
            ha=ha,
        )
    ax.set_ylim(0, 112)
    ax.set_ylabel("Percentile rank of raw TrueSkill mean")
    ax.set_xlabel("Meeting date")
    ax.set_title("Percentile ranks over time, text-only (n=95)")
    ax.legend(loc="lower left", frameon=True, fancybox=False, edgecolor=GRID)
    fig.tight_layout()
    return save(fig, "timeseries_ax1_vs_ax4_text")


def plot_gates_forest() -> Path:
    gates = load_gates()["by_tag"]
    rows = []
    for axis in AXIS_ORDER:
        for design, color in (("text", NAVY), ("conditional", BLUE)):
            tag = f"{axis}__{design}"
            g = gates[tag]["d_same_action"]
            rows.append(
                {
                    "axis": SHORT[axis],
                    "design": design,
                    "rho": g["rho"],
                    "se": g["se"],
                    "n": g["n"],
                    "color": color,
                    "pass": gates[tag]["gate_d_same_pass"],
                }
            )
    fig, ax = plt.subplots(figsize=(8.4, 6.4))
    y = np.arange(len(AXIS_ORDER))
    for i, axis in enumerate(AXIS_ORDER):
        text = next(r for r in rows if r["axis"] == SHORT[axis] and r["design"] == "text")
        cond = next(r for r in rows if r["axis"] == SHORT[axis] and r["design"] == "conditional")
        ax.errorbar(
            text["rho"],
            i - 0.14,
            xerr=text["se"],
            fmt="o",
            color=NAVY,
            capsize=3,
            ms=6,
        )
        ax.errorbar(
            cond["rho"],
            i + 0.14,
            xerr=cond["se"],
            fmt="s",
            color=BLUE,
            capsize=3,
            ms=5.5,
        )
    ax.axvline(0.30, color=BRICK, ls="--", lw=1, label="M1 pass line ρ = +0.30")
    ax.axvline(0, color=GRID, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([SHORT[a] for a in AXIS_ORDER])
    ax.set_xlabel("Spearman rank correlation with same-day funds-target change (action days)")
    ax.set_title("Action-day construct check vs d_same (n=30; error bars = bootstrap s.e.)")
    ax.plot([], [], "o", color=NAVY, label="Text-only")
    ax.plot([], [], "s", color=BLUE, label="Macro-conditional")
    ax.legend(loc="lower right", frameon=True, fancybox=False, edgecolor=GRID)
    ax.set_xlim(-1.05, 1.05)
    fig.tight_layout()
    return save(fig, "gates_spearman_dsame")


def plot_text_vs_conditional_ax1() -> Path:
    t = load_ranked("ax1_inflation_hawkish", "text")
    c = load_ranked("ax1_inflation_hawkish", "conditional")
    m = t.merge(c, on="doc_id", suffixes=("_text", "_cond"))
    fig, ax = plt.subplots(figsize=(6.6, 6.2))
    colors = {"hike": BRICK, "cut": BLUE, "hold": MUTED}
    for action, grp in m.groupby("action_text"):
        ax.scatter(
            grp["mu_text"],
            grp["mu_cond"],
            s=28,
            color=colors.get(action, INK),
            label=action,
            alpha=0.85,
        )
    highlight = m[m["doc_id"] == "stmt-2022-11-02"]
    if len(highlight):
        ax.scatter(
            highlight["mu_text"],
            highlight["mu_cond"],
            s=70,
            facecolors="none",
            edgecolors=INK,
            linewidths=1.4,
            zorder=4,
        )
        ax.annotate(
            "2022-11-02",
            (float(highlight["mu_text"].iloc[0]), float(highlight["mu_cond"].iloc[0])),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=8,
        )
    lo = min(m["mu_text"].min(), m["mu_cond"].min()) - 1
    hi = max(m["mu_text"].max(), m["mu_cond"].max()) + 1
    ax.plot([lo, hi], [lo, hi], color=GRID, lw=1, ls="--")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Text-only TrueSkill mean (axis 1)")
    ax.set_ylabel("Macro-conditional TrueSkill mean (axis 1)")
    ax.set_title("Text-only vs conditional ranks, axis 1 (n=95)")
    ax.legend(title="Same-day action", frameon=True, fancybox=False, edgecolor=GRID)
    fig.tight_layout()
    return save(fig, "scatter_text_vs_conditional_ax1")


def plot_example_meeting() -> Path:
    ids = ["stmt-2022-11-02", "stmt-2020-09-16"]
    labels = ["2022-11-02\nPowell hike +0.75 pp", "2020-09-16\nPowell hold 0"]
    series = [
        ("ax1_inflation_hawkish", "text", "Axis 1 inflation (text)"),
        ("ax4_forward_path", "text", "Axis 4 forward path (text)"),
    ]
    vals = []
    for axis, design, _ in series:
        df = load_ranked(axis, design).set_index("doc_id")
        vals.append([float(df.loc[i, "percentile"]) for i in ids])
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    x = np.arange(len(ids))
    w = 0.36
    ax.bar(x - w / 2, vals[0], w, color=NAVY, label="Axis 1: more hawkish about inflation")
    ax.bar(
        x + w / 2,
        vals[1],
        w,
        color=TERR,
        label="Axis 4: more explicit about the likely future path of policy",
    )
    for i, row in enumerate(vals):
        for j, v in enumerate(row):
            xpos = x[j] + (-w / 2 if i == 0 else w / 2)
            ax.text(xpos, v + 1.5, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Percentile rank of raw TrueSkill mean (n=95)")
    ax.set_title("Same two openings, two criteria (text-only ranks)")
    ax.legend(loc="upper right", frameon=True, fancybox=False, edgecolor=GRID)
    fig.tight_layout()
    return save(fig, "example_nov2022_vs_sep2020")


def main() -> int:
    style()
    written = [
        plot_heatmap("text"),
        plot_heatmap("conditional"),
        plot_pca_scatter("text"),
        plot_pca_scatter("conditional"),
        plot_timeseries_ax1_ax4(),
        plot_gates_forest(),
        plot_text_vs_conditional_ax1(),
        plot_example_meeting(),
    ]
    for p in written:
        print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
