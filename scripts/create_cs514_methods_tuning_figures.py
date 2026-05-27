"""Create poster-ready tuning figures for CS514 methods.

Outputs:
- network alpha x gamma sweep heatmap
- NMF k-sweep reconstruction/stability plot
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "data" / "processed" / "cs514_network_analysis"
DIAGNOSTICS = ANALYSIS / "diagnostics"
MATRIX = ANALYSIS / "matrix_decomposition" / "nmf_test_b"
OUT_DIR = ROOT / "docs" / "cs514_poster_figures_orange"

PARAM_SWEEP = DIAGNOSTICS / "parameter_sweep.csv"
GAMMA_NULL_SWEEP = DIAGNOSTICS / "merged_ownership_newman_disparity_a0p025_midline_gamma_null_sweep.csv"
NMF_K_SUMMARY = MATRIX / "nmf_test_b_k_summary.csv"


BGG_ORANGE = "#FF5100"
BGG_RED = "#B42828"
BGG_PURPLE = "#3F3A60"
DARK = "#24223A"
GRAY = "#646464"
MUTED = "#8C8680"
WARM_BG = "#FAF6F1"
LINE = "#DED6CF"
WHITE = "#FFFFFF"


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "figure.facecolor": WHITE,
            "axes.facecolor": WHITE,
            "font.family": ["Arial", "DejaVu Sans"],
            "axes.edgecolor": LINE,
            "axes.labelcolor": DARK,
            "xtick.color": GRAY,
            "ytick.color": GRAY,
            "text.color": DARK,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save(fig: plt.Figure, stem: str) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"{stem}.png"
    pdf = OUT_DIR / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def fmt_alpha(alpha: float) -> str:
    return f"{alpha:g}"


def fmt_gamma(gamma: float) -> str:
    return f"{gamma:g}"


def network_sweep_heatmap() -> tuple[Path, Path]:
    configure_style()
    sweep = pd.read_csv(PARAM_SWEEP)
    null = pd.read_csv(GAMMA_NULL_SWEEP)

    selected_alpha = 0.025
    selected_gamma = 1.75
    null_for_grid = null.assign(alpha=selected_alpha, resolution=null["gamma"])[
        ["alpha", "resolution", "median_pairwise_nmi", "n_communities"]
    ]
    sweep_for_grid = sweep[~np.isclose(sweep["alpha"], selected_alpha)][
        ["alpha", "resolution", "median_pairwise_nmi", "n_communities"]
    ]
    grid_data = pd.concat([sweep_for_grid, null_for_grid], ignore_index=True)

    alphas = sorted(grid_data["alpha"].unique())
    gammas = sorted(grid_data["resolution"].unique())
    nmi = grid_data.pivot(index="alpha", columns="resolution", values="median_pairwise_nmi").loc[alphas, gammas]
    communities = grid_data.pivot(index="alpha", columns="resolution", values="n_communities").loc[alphas, gammas]
    selected = null[np.isclose(null["gamma"], selected_gamma)].iloc[0]

    cmap = mpl.colors.LinearSegmentedColormap.from_list(
        "bgg_orange_heat",
        ["#FFFDF9", "#FFE2D2", "#FFB380", BGG_ORANGE, BGG_RED, DARK],
    )

    fig = plt.figure(figsize=(9.6, 6.8), dpi=300)
    ax = fig.add_axes([0.145, 0.195, 0.710, 0.610])
    cmap = cmap.copy()
    cmap.set_bad(color="#F2EEE9")
    im = ax.imshow(np.ma.masked_invalid(nmi.to_numpy(float)), vmin=0.50, vmax=1.00, cmap=cmap, aspect="auto")

    ax.set_xticks(np.arange(len(gammas)))
    ax.set_xticklabels([fmt_gamma(g) for g in gammas], fontsize=10)
    ax.set_yticks(np.arange(len(alphas)))
    ax.set_yticklabels([fmt_alpha(a) for a in alphas], fontsize=10)
    ax.set_xlabel("Louvain resolution gamma", fontsize=12, fontweight="bold", labelpad=10)
    ax.set_ylabel("Disparity filter alpha", fontsize=12, fontweight="bold", labelpad=10)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for i, alpha in enumerate(alphas):
        for j, gamma in enumerate(gammas):
            val = nmi.loc[alpha, gamma]
            if pd.isna(val):
                ax.text(j, i, "not run", ha="center", va="center", fontsize=7.0, color="#A59C94")
                continue
            n_comm = int(communities.loc[alpha, gamma])
            color = WHITE if val >= 0.76 else DARK
            ax.text(j, i - 0.10, f"{val:.2f}", ha="center", va="center", fontsize=9.2, fontweight="bold", color=color)
            ax.text(j, i + 0.18, f"{n_comm} comm.", ha="center", va="center", fontsize=7.3, color=color)

    i_sel = alphas.index(selected_alpha)
    j_sel = gammas.index(selected_gamma)
    ax.add_patch(Rectangle((j_sel - 0.5, i_sel - 0.5), 1, 1, fill=False, edgecolor=BGG_PURPLE, linewidth=4.0))
    ax.scatter([j_sel + 0.37], [i_sel - 0.37], marker="*", s=230, color=BGG_PURPLE, edgecolor=WHITE, linewidth=0.9, zorder=3)

    fig.text(0.055, 0.955, "Network path tuning", fontsize=24, fontweight="bold", color=DARK, va="top")
    fig.text(0.055, 0.905, "Joint sweep of backbone strictness and Louvain resolution; cells show stability and granularity.", fontsize=11.5, color=GRAY, va="top")
    fig.text(
        0.055,
        0.855,
        f"Selected midline: alpha = {selected_alpha:g}, gamma = {selected_gamma:g} | "
        f"NMI = {selected['median_pairwise_nmi']:.3f} | z = {selected['z_score']:+.2f} | "
        f"{int(selected['observed_n_communities'])} communities",
        fontsize=10.7,
        color=BGG_RED,
        fontweight="bold",
        va="top",
    )

    cax = fig.add_axes([0.875, 0.270, 0.020, 0.430])
    cb = fig.colorbar(im, cax=cax)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, length=0, colors=GRAY)
    cb.set_label("Median pairwise NMI", fontsize=9, color=GRAY, labelpad=10)

    fig.text(
        0.055,
        0.060,
        "Figure. Network parameters were selected from a joint alpha x gamma sweep. The selected cell balances stability, granularity, and null-model significance.",
        fontsize=9.0,
        color=MUTED,
    )
    return save(fig, "figure_methods_network_parameter_sweep_orange")


def nmf_k_sweep() -> tuple[Path, Path]:
    configure_style()
    nmf = pd.read_csv(NMF_K_SUMMARY)
    x = nmf["k"].to_numpy()
    err = nmf["mean_reconstruction_error"].to_numpy()
    stability = nmf["min_seed_stability"].to_numpy()

    fig = plt.figure(figsize=(9.6, 6.8), dpi=300)
    ax1 = fig.add_axes([0.130, 0.195, 0.730, 0.610])
    ax2 = ax1.twinx()

    ax1.plot(x, err, color=BGG_ORANGE, linewidth=3.2, marker="o", markersize=8, label="Reconstruction error")
    ax2.plot(x, stability, color=BGG_PURPLE, linewidth=3.0, marker="s", markersize=7, label="Minimum seed stability")

    ax1.axvline(15, color=BGG_RED, linewidth=2.2, linestyle="--", alpha=0.95)
    ax1.text(15.35, err.min() + 0.62 * (err.max() - err.min()), "useful k ≈ 15", fontsize=11, fontweight="bold", color=BGG_RED)

    ax1.set_xlabel("Number of NMF components (k)", fontsize=12, fontweight="bold", labelpad=10)
    ax1.set_ylabel("Mean reconstruction error", fontsize=12, fontweight="bold", color=BGG_ORANGE, labelpad=10)
    ax2.set_ylabel("Minimum seed stability", fontsize=12, fontweight="bold", color=BGG_PURPLE, labelpad=12)
    ax1.set_xticks(x)
    ax1.tick_params(axis="y", colors=BGG_ORANGE)
    ax2.tick_params(axis="y", colors=BGG_PURPLE)
    ax1.grid(axis="y", color=LINE, linewidth=0.9, alpha=0.65)
    ax1.set_axisbelow(True)
    ax2.set_ylim(-0.02, 1.05)

    for spine in ["top", "right"]:
        ax1.spines[spine].set_visible(False)
    ax2.spines["top"].set_visible(False)
    ax1.spines["left"].set_color(LINE)
    ax1.spines["bottom"].set_color(LINE)
    ax2.spines["right"].set_color(LINE)

    for xi, yi in zip(x, err, strict=False):
        ax1.text(xi, yi + 0.95, f"{yi:.1f}", fontsize=8.3, ha="center", color=BGG_ORANGE, fontweight="bold")
    for xi, yi in zip(x, stability, strict=False):
        label = "1.00" if yi > 0.995 else f"{yi:.2f}"
        ax2.text(xi, yi - 0.075 if yi > 0.20 else yi + 0.055, label, fontsize=8.3, ha="center", color=BGG_PURPLE, fontweight="bold")

    fig.text(0.055, 0.955, "Matrix path tuning", fontsize=24, fontweight="bold", color=DARK, va="top")
    fig.text(0.055, 0.905, "NMF k-sweep: reconstruction improves gradually, but component stability breaks after k = 15.", fontsize=11.5, color=GRAY, va="top")

    ax1.text(
        0.045,
        0.195,
        "Interpretation\n"
        "k = 15 is the last\n"
        "fully stable setting.\n\n"
        "At k = 20 and 25,\n"
        "some components\n"
        "become seed-sensitive.",
        transform=ax1.transAxes,
        fontsize=10.2,
        color=DARK,
        linespacing=1.18,
        bbox={"boxstyle": "round,pad=0.45,rounding_size=0.03", "facecolor": WARM_BG, "edgecolor": LINE, "linewidth": 1.2},
    )

    handles = [
        plt.Line2D([0], [0], color=BGG_ORANGE, marker="o", linewidth=3, label="Reconstruction error"),
        plt.Line2D([0], [0], color=BGG_PURPLE, marker="s", linewidth=3, label="Seed stability"),
    ]
    ax1.legend(handles=handles, loc="upper right", frameon=False, fontsize=10)

    fig.text(
        0.055,
        0.060,
        "Figure. NMF was tuned by comparing reconstruction error against seed-to-seed component stability. The stable latent structure is useful up to k around 15.",
        fontsize=9.0,
        color=MUTED,
    )
    return save(fig, "figure_methods_nmf_k_sweep_orange")


def main() -> None:
    outputs = []
    outputs.extend(network_sweep_heatmap())
    outputs.extend(nmf_k_sweep())
    for path in outputs:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
