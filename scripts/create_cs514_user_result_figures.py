"""Create user-focused result figures for the CS514 poster.

These figures are designed for the poster's main/bottom finding area:
- a wide hero figure for user archetypes and the other-dominant decomposition
- a user taste-dimension identity map
"""

from __future__ import annotations

from pathlib import Path
from textwrap import fill

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "data" / "processed" / "cs514_network_analysis"
USER_PROFILES = ANALYSIS / "user_profiles"
OUT_DIR = ROOT / "docs" / "cs514_poster_figures_orange"

ARCHETYPE_SUMMARY = USER_PROFILES / "merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_family_summary.csv"
OTHER_DECOMP = USER_PROFILES / "merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_other_dominant_decomposition.csv"
DIM_SUMMARY = USER_PROFILES / "merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_dimension_summary.csv"


BGG_ORANGE = "#FF5100"
BGG_RED = "#B42828"
BGG_PURPLE = "#3F3A60"
DARK = "#24223A"
GRAY = "#646464"
MUTED = "#8C8680"
WARM_BG = "#FAF6F1"
PANEL = "#FFFDF9"
LINE = "#DED6CF"
AMBER = "#F2A23A"
WHITE = "#FFFFFF"
BROWN = "#8B4E38"
SAND = "#C7B49F"
LIGHT_GRAY = "#D7D1CB"


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


def nice_dimension(name: str) -> str:
    labels = {
        "bgg_golden_age_canon": "Golden Age\ncanon",
        "current_heavy_euro_engine_builders": "Current\nheavy euro",
        "dungeon_crawl_cooperative_campaign_adventure": "Dungeon crawl /\ncampaign",
        "amerithrash_miniatures_lcg": "Amerithrash /\nLCG",
        "party_family_social_deduction": "Party /\nsocial",
        "puzzle_nature_tableau_builders": "Puzzle /\nnature",
        "historical_wargames_conflict_strategy": "Historical\nwargames",
        "medium_worker_placement_euros": "Medium\neuros",
        "cooperative_trick_taking_deduction": "Trick-taking /\ndeduction",
        "roll_and_write_number_dice_games": "Roll-and-write",
        "legacy_narrative_mystery": "Legacy /\nnarrative",
    }
    return labels.get(name, name.replace("_", " "))


def figure_user_hero() -> tuple[Path, Path]:
    configure_style()
    archetypes = pd.read_csv(ARCHETYPE_SUMMARY)
    archetypes = archetypes[archetypes["archetype_family"] != "insufficient_selected_owned"].copy()
    order = ["other_dominant", "generalist", "leaning", "specialist", "mixed"]
    archetypes["archetype_family"] = pd.Categorical(archetypes["archetype_family"], order, ordered=True)
    archetypes = archetypes.sort_values("archetype_family")
    archetypes["pct"] = archetypes["pct_eligible_users"] * 100

    decomp = pd.read_csv(OTHER_DECOMP)
    decomp = decomp[decomp["group"] == "community_type"].copy()
    dorder = ["temporal_artifact", "bridge_cluster", "franchise_series", "taste_cross_over", "tiny_fragment", "bridge_singleton"]
    decomp["value"] = pd.Categorical(decomp["value"], dorder, ordered=True)
    decomp = decomp.sort_values("value")
    decomp["pct"] = decomp["share_of_other_owned_edges"] * 100

    fig = plt.figure(figsize=(15.8, 4.15), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.text(0.035, 0.940, "Main user finding: most collectors are cross-community", fontsize=21.5, fontweight="bold", color=DARK, va="top")
    ax.text(0.035, 0.855, "The largest user group is structured by temporal, bridge, and franchise behavior rather than one taste identity.", fontsize=11.5, color=GRAY, va="top")
    ax.add_line(plt.Line2D([0.035, 0.965], [0.800, 0.800], color=BGG_ORANGE, linewidth=2.0))

    ax_donut = fig.add_axes([0.050, 0.150, 0.300, 0.590])
    ax_donut.set_aspect("equal")
    donut_colors = [BGG_ORANGE, SAND, BGG_PURPLE, BROWN, LIGHT_GRAY]
    ax_donut.pie(
        archetypes["pct"],
        startangle=90,
        counterclock=False,
        colors=donut_colors,
        explode=[0.035, 0, 0, 0, 0],
        wedgeprops={"width": 0.30, "edgecolor": WHITE, "linewidth": 2.1},
    )
    other_pct = float(archetypes.loc[archetypes["archetype_family"] == "other_dominant", "pct"].iloc[0])
    ax_donut.text(0, 0.06, f"{other_pct:.1f}%", fontsize=38, fontweight="bold", ha="center", va="center", color=DARK)
    ax_donut.text(0, -0.205, "other-dominant\nusers", fontsize=12.0, ha="center", va="center", color=GRAY, linespacing=1.1)
    ax_donut.axis("off")

    ax_leg = fig.add_axes([0.340, 0.455, 0.185, 0.250])
    ax_leg.axis("off")
    pretty = {
        "other_dominant": "Other-dominant",
        "generalist": "Generalist",
        "leaning": "Leaning",
        "specialist": "Specialist",
        "mixed": "Mixed",
    }
    for i, row in enumerate(archetypes.itertuples(index=False)):
        y = 0.87 - i * 0.18
        ax_leg.add_patch(Rectangle((0.02, y - 0.045), 0.055, 0.055, facecolor=donut_colors[i], edgecolor="none"))
        ax_leg.text(0.095, y - 0.018, f"{pretty[str(row.archetype_family)]}: {row.pct:.1f}%", fontsize=10.4, color=DARK, va="center")

    ax_bar = fig.add_axes([0.530, 0.205, 0.405, 0.160])
    ax_bar.set_xlim(0, 100)
    ax_bar.set_ylim(0, 1)
    ax_bar.axis("off")
    names = {
        "temporal_artifact": "Temporal\n36.1%",
        "bridge_cluster": "Bridge\n27.8%",
        "franchise_series": "Franchise\n17.8%",
        "taste_cross_over": "Cross-over\n7.9%",
        "tiny_fragment": "Tiny\n7.2%",
        "bridge_singleton": "Singleton\n3.2%",
    }
    colors = {
        "temporal_artifact": AMBER,
        "bridge_cluster": BGG_ORANGE,
        "franchise_series": BROWN,
        "taste_cross_over": SAND,
        "tiny_fragment": LIGHT_GRAY,
        "bridge_singleton": "#9B948C",
    }
    left = 0.0
    for row in decomp.itertuples(index=False):
        value = str(row.value)
        pct = float(row.pct)
        ax_bar.barh(0.52, pct, left=left, height=0.56, color=colors[value], edgecolor=WHITE, linewidth=1.0)
        text_color = WHITE if value in {"bridge_cluster", "franchise_series"} else DARK
        if pct >= 7.0:
            ax_bar.text(left + pct / 2, 0.52, names[value], fontsize=9.7, fontweight="bold", color=text_color, ha="center", va="center", linespacing=1.02)
        else:
            ax_bar.text(left + pct / 2, 0.12, names[value].replace("\n", " "), fontsize=8.3, color=GRAY, ha="center", va="top")
        left += pct

    ax.text(0.530, 0.398, "What is inside other-dominant ownership?", fontsize=14.0, fontweight="bold", color=DARK, va="bottom")

    cards = [
        ("Temporal", "recent releases owned across many tastes"),
        ("Bridge", "cross-genre games that connect audiences"),
        ("Franchise", "system loyalty: Pandemic, Unmatched, TTR"),
    ]
    for i, (title, body) in enumerate(cards):
        x = 0.535 + i * 0.140
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.490),
                0.115,
                0.185,
                boxstyle="round,pad=0.012,rounding_size=0.015",
                facecolor=WARM_BG,
                edgecolor=LINE,
                linewidth=1.0,
            )
        )
        ax.text(x + 0.012, 0.642, title, fontsize=10.5, fontweight="bold", color=BGG_ORANGE, va="top")
        ax.text(x + 0.012, 0.585, fill(body, 19), fontsize=8.2, color=GRAY, va="top", linespacing=1.02)

    ax.text(
        0.035,
        0.040,
        "Figure. User archetypes show that the dominant residual group is structured: most collectors span taste communities through recent releases, bridge titles, and franchise systems.",
        fontsize=8.8,
        color=MUTED,
    )
    return save(fig, "figure_user_main_finding_archetype_decomposition_orange")


def figure_dimension_identity_map() -> tuple[Path, Path]:
    configure_style()
    data = pd.read_csv(DIM_SUMMARY).copy()
    data = data[~data["dimension"].isin(["other"])].copy()
    data["reach_pct"] = data["pct_users_with_any"] * 100
    data["identity_strength_pct"] = np.where(data["users_with_any"] > 0, data["users_with_40pct_or_more"] / data["users_with_any"] * 100, 0)
    data["dominant_taste_users"] = data["dominant_taste_users"].astype(float)

    fig = plt.figure(figsize=(10.2, 6.6), dpi=300)
    ax = fig.add_axes([0.115, 0.155, 0.790, 0.665])
    ax.set_facecolor(WHITE)
    ax.grid(color=LINE, linewidth=0.9, alpha=0.65)
    ax.set_axisbelow(True)

    # Quadrant guides.
    ax.axvline(80, color=LINE, linewidth=1.4, linestyle="--")
    ax.axhline(1.5, color=LINE, linewidth=1.4, linestyle="--")
    ax.text(61, 5.45, "niche identity", fontsize=9.3, fontweight="bold", color=BGG_RED)
    ax.text(85.3, 5.45, "broad identity", fontsize=9.3, fontweight="bold", color=BGG_PURPLE)
    ax.text(84.3, 0.30, "supplementary layer", fontsize=9.3, fontweight="bold", color=GRAY)

    colors = []
    for row in data.itertuples(index=False):
        if "wargames" in row.dimension:
            colors.append(BGG_RED)
        elif row.identity_strength_pct >= 2.0:
            colors.append(BGG_PURPLE)
        elif row.reach_pct >= 80:
            colors.append(SAND)
        else:
            colors.append(BGG_ORANGE)

    sizes = 90 + np.sqrt(data["dominant_taste_users"].to_numpy()) * 55
    ax.scatter(
        data["reach_pct"],
        data["identity_strength_pct"],
        s=sizes,
        c=colors,
        alpha=0.90,
        edgecolor=WHITE,
        linewidth=1.4,
        zorder=3,
    )
    label_offsets = {
        "bgg_golden_age_canon": (0.65, 0.10),
        "current_heavy_euro_engine_builders": (0.65, 0.12),
        "dungeon_crawl_cooperative_campaign_adventure": (-3.3, -0.32),
        "amerithrash_miniatures_lcg": (0.65, 0.16),
        "party_family_social_deduction": (0.65, -0.16),
        "historical_wargames_conflict_strategy": (-8.3, 0.18),
        "roll_and_write_number_dice_games": (-5.3, -0.18),
        "legacy_narrative_mystery": (0.65, -0.18),
    }
    label_dimensions = set(label_offsets)
    for row in data.itertuples(index=False):
        if str(row.dimension) not in label_dimensions:
            continue
        x = float(row.reach_pct)
        y = float(row.identity_strength_pct)
        label = nice_dimension(str(row.dimension))
        dx, dy = label_offsets.get(str(row.dimension), (0.65, 0.10))
        if y < 0.25:
            fs = 7.2
        else:
            fs = 8.0
        ax.text(x + dx, y + dy, label, fontsize=fs, color=DARK, fontweight="bold", linespacing=0.90)

    ax.set_xlim(55, 94)
    ax.set_ylim(-0.45, 6.45)
    ax.set_xlabel("Reach: users owning at least one game in dimension (%)", fontsize=11.5, fontweight="bold", labelpad=10)
    ax.set_ylabel("Identity strength: users with >=40% of collection in dimension (%)", fontsize=11.5, fontweight="bold", labelpad=10)
    ax.tick_params(labelsize=9.5)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)

    fig.text(0.045, 0.955, "User taste dimensions differ by reach and identity strength", fontsize=21.0, fontweight="bold", color=DARK, va="top")
    fig.text(0.045, 0.900, "Some dimensions define specialist collectors; others are broad supplementary layers across many collections.", fontsize=11.2, color=GRAY, va="top")
    fig.text(
        0.055,
        0.070,
        "Figure. Wargames have lower reach but high identity strength; party, puzzle, roll-and-write, and legacy games behave more like supplementary layers.",
        fontsize=8.7,
        color=MUTED,
    )
    return save(fig, "figure_user_dimension_identity_map_orange")


def main() -> None:
    outputs = []
    outputs.extend(figure_user_hero())
    outputs.extend(figure_dimension_identity_map())
    for path in outputs:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
