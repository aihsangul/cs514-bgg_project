"""
Results Figure 5: Bridge Game Table
Top-10 games by bridge score, showing BGG rank, bridge role, and community type.
Bridge singletons highlighted in accent red.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from pathlib import Path

# === PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'
RED      = '#E63946'
BLUE     = '#4A90D9'
TINT     = '#FFF1E0'

# === DATA (top-10 from bridge_score_table.csv) ===
# name, bgr_rank, bridge_score, community_type, bridge_role_short
GAMES = [
    ('7 Wonders Duel',      24,   0.9998, 'tiny_fragment',    'Universal bridge'),
    ('Terraforming Mars',    9,   0.9993, 'bridge_singleton', 'Universal bridge'),
    ('Azul',                96,   0.9987, 'bridge_cluster',   'Universal bridge'),
    ('Carcassonne',        239,   0.9974, 'bridge_cluster',   'Universal bridge'),
    ('Codenames',          161,   0.9971, 'franchise_series', 'Cross-community hub'),
    ('Catan',              615,   0.9971, 'franchise_series', 'Cross-community hub'),
    ('Wingspan',            38,   0.9969, 'franchise_series', 'Cross-community hub'),
    ('Ark Nova',             2,   0.9962, 'bridge_singleton', 'Universal bridge'),
    ('Pandemic',           170,   0.9962, 'franchise_series', 'Cross-community hub'),
    ('Brass: Birmingham',    1,   0.9958, 'tiny_fragment',    'Universal bridge'),
]

# Community type short display
TYPE_DISPLAY = {
    'bridge_singleton': ('Bridge singleton', RED),
    'bridge_cluster':   ('Bridge cluster',   BLUE),
    'franchise_series': ('Franchise / series', '#9B59B6'),
    'tiny_fragment':    ('Tiny fragment',    SLATE),
}

# === FIGURE ===
fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
fig.patch.set_facecolor(OFFWHITE)
ax.set_facecolor(OFFWHITE)
ax.axis('off')

# Table geometry
n_rows = len(GAMES)
n_cols = 4
col_labels = ['Game', 'BGG Rank', 'Bridge Score', 'Community Type']
col_widths  = [0.34, 0.13, 0.16, 0.30]   # fractions of figure width
col_x       = [0.01, 0.37, 0.52, 0.70]   # left edge x in axes coords
row_h       = 0.082
header_y    = 0.86
first_row_y = header_y - row_h

# ── TITLE ──────────────────────────────────────────────────────────────────
ax.text(0.5, 0.99,
        'Top Games by Cross-Community Bridge Score',
        ha='center', va='top', transform=ax.transAxes,
        fontsize=12, fontweight='bold', color=CHARCOAL)
ax.text(0.5, 0.92,
        'Bridge score ≈ share of edges crossing community boundaries  ·  bridge singletons anchor no taste community',
        ha='center', va='top', transform=ax.transAxes,
        fontsize=7.5, color=SLATE, style='italic')

# ── HEADER ROW ─────────────────────────────────────────────────────────────
header_bg = FancyBboxPatch(
    (0.0, header_y - row_h * 0.85), 1.0, row_h * 0.85,
    boxstyle='round,pad=0.005', transform=ax.transAxes,
    facecolor=CHARCOAL, edgecolor='none', zorder=2
)
ax.add_patch(header_bg)
for label, x in zip(col_labels, col_x):
    ax.text(x + 0.01, header_y - row_h * 0.42,
            label, ha='left', va='center',
            transform=ax.transAxes,
            fontsize=9, fontweight='bold', color='white', zorder=3)

# ── DATA ROWS ──────────────────────────────────────────────────────────────
for i, (name, rank, score, ctype, role) in enumerate(GAMES):
    y_top = first_row_y - i * row_h
    is_singleton = (ctype == 'bridge_singleton')

    # Row background
    bg_color = '#FFF0F0' if is_singleton else (OFFWHITE if i % 2 == 0 else '#F0F4FA')
    row_bg = FancyBboxPatch(
        (0.0, y_top - row_h * 0.92), 1.0, row_h * 0.92,
        boxstyle='round,pad=0.003', transform=ax.transAxes,
        facecolor=bg_color, edgecolor='none', zorder=1
    )
    ax.add_patch(row_bg)

    text_color = RED if is_singleton else CHARCOAL
    y_center   = y_top - row_h * 0.46

    # Game name (bold if singleton)
    ax.text(col_x[0] + 0.01, y_center, name,
            ha='left', va='center', transform=ax.transAxes,
            fontsize=8.5, color=text_color,
            fontweight='bold' if is_singleton else 'normal')

    # BGG Rank — highlight #1 and #2
    rank_color = ORANGE if rank <= 2 else text_color
    rank_fw    = 'bold' if rank <= 2 else 'normal'
    ax.text(col_x[1] + 0.01, y_center, f'#{rank}',
            ha='left', va='center', transform=ax.transAxes,
            fontsize=8.5, color=rank_color, fontweight=rank_fw)

    # Bridge score — bar-style
    bar_x   = col_x[2] + 0.005
    bar_max = 0.13
    bar_w   = bar_max * score
    bar_rect = FancyBboxPatch(
        (bar_x, y_center - 0.018), bar_w, 0.036,
        boxstyle='round,pad=0.002', transform=ax.transAxes,
        facecolor=RED if is_singleton else ORANGE, alpha=0.75, edgecolor='none', zorder=2
    )
    ax.add_patch(bar_rect)
    ax.text(bar_x + bar_w + 0.005, y_center, f'{score:.4f}',
            ha='left', va='center', transform=ax.transAxes,
            fontsize=7.5, color=text_color)

    # Community type pill
    disp_label, pill_color = TYPE_DISPLAY.get(ctype, (ctype, SLATE))
    pill_x = col_x[3] + 0.005
    pill = FancyBboxPatch(
        (pill_x, y_center - 0.02), 0.22, 0.04,
        boxstyle='round,pad=0.005', transform=ax.transAxes,
        facecolor=pill_color, alpha=0.18, edgecolor=pill_color, linewidth=0.8, zorder=2
    )
    ax.add_patch(pill)
    ax.text(pill_x + 0.11, y_center, disp_label,
            ha='center', va='center', transform=ax.transAxes,
            fontsize=7.5, color=pill_color, fontweight='bold')

# ── LEGEND ─────────────────────────────────────────────────────────────────
legend_y = 0.02
ax.text(0.01, legend_y,
        '★  Bridge singletons (red) = highest-ranked games that anchor no taste community — they are the shared canon.',
        ha='left', va='bottom', transform=ax.transAxes,
        fontsize=7.5, color=RED, style='italic')

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure5_bridge_table.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
