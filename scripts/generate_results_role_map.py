"""
Results Figure: Community Role Map
Scatter of 43 communities by internal cohesion vs external reach.
X = internal_weight_share (taste self-containment)
Y = community_strength (external reach, log scale)
Size = community size
Color = community type
Reveals four structural roles: canon, specialist, bridge, fragment.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Rectangle
from pathlib import Path

# === PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'

TYPE_COLORS = {
    'taste_specialist':  '#F58A35',
    'temporal_canon':    '#212B36',
    'temporal_artifact': '#8B5E3C',
    'bridge_cluster':    '#4A90D9',
    'bridge_singleton':  '#E63946',
    'franchise_series':  '#9B59B6',
    'taste_cross_over':  '#F0A500',
    'shared_culture':    '#2E8B57',
    'tiny_fragment':     '#C8C8C8',
}

TYPE_LABELS = {
    'taste_specialist':  'Taste specialist',
    'temporal_canon':    'Temporal canon',
    'temporal_artifact': 'Temporal artifact',
    'bridge_cluster':    'Bridge cluster',
    'bridge_singleton':  'Bridge singleton',
    'franchise_series':  'Franchise / series',
    'taste_cross_over':  'Taste cross-over',
    'shared_culture':    'Shared culture',
    'tiny_fragment':     'Tiny fragment',
}

# Short callout labels for the major communities
SHORT = {
    10: 'BGG Canon',
    19: 'New Hotness',
    2:  'Heavy Euros',
    9:  'Amerithrash',
    25: 'Party / Family',
    12: 'Dungeon Crawl',
    8:  'Worker Placement',
    13: 'Puzzle / Nature',
    35: 'Coop / Deduction',
    20: 'Wargames',
    4:  'Legacy',
    0:  'TM',
    24: 'Ark Nova',
    7:  "Brass:B",
}

# === LOAD ===
base = Path('data/processed/cs514_network_analysis')
df = pd.read_csv(base / 'structural_analysis/community_condensation_nodes.csv')

# === FIGURE ===
fig = plt.figure(figsize=(10, 8.5), dpi=300)
gs  = fig.add_gridspec(1, 1, left=0.09, right=0.97, top=0.90, bottom=0.10)
ax  = fig.add_subplot(gs[0, 0])
fig.patch.set_facecolor(OFFWHITE)
ax.set_facecolor(OFFWHITE)

# === QUADRANT CUTS (use natural break ~ medians of meaningful subset) ===
x_cut = 0.05
y_cut = 5000.0

# === DRAW QUADRANT BACKGROUNDS ===
x_min, x_max = -0.005, 0.22
y_min, y_max = 1000.0, 22000.0
ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
ax.set_yscale('log')

# Quadrant tint (very subtle)
ax.axvspan(x_cut, x_max, ymin=0.5, ymax=1.0, color='#FFF1E0', alpha=0.45, zorder=0)  # top-right
ax.axhline(y_cut, color='#CCCCCC', linewidth=0.8, linestyle='--', zorder=1)
ax.axvline(x_cut, color='#CCCCCC', linewidth=0.8, linestyle='--', zorder=1)

# === QUADRANT LABELS ===
quad_label_props = dict(fontsize=10, fontweight='bold', alpha=0.85, ha='center', va='center')

ax.text(0.13, 6300, 'CANON & SPECIALIST IDENTITY',
        color=CHARCOAL, **quad_label_props)
ax.text(0.13, 5750, 'self-contained taste, broad reach',
        fontsize=7.5, color=SLATE, ha='center', va='center', style='italic')

ax.text(0.022, 14000, 'CROSS-GENRE BRIDGE',
        color='#2E8B57', **quad_label_props)
ax.text(0.022, 13000, 'weak self-cohesion, broad reach',
        fontsize=7.5, color=SLATE, ha='center', va='center', style='italic')

ax.text(0.022, 1400, 'FRANCHISE & FRAGMENT',
        color='#9B59B6', **quad_label_props)
ax.text(0.022, 1280, 'small, peripheral clusters',
        fontsize=7.5, color=SLATE, ha='center', va='center', style='italic')

ax.text(0.13, 1400, 'INSULAR NICHE',
        color=SLATE, **quad_label_props)
ax.text(0.13, 1280, '(rare — empty quadrant)',
        fontsize=7.5, color=SLATE, ha='center', va='center', style='italic')

# === SCATTER POINTS ===
for _, row in df.iterrows():
    ctype = row['community_type']
    color = TYPE_COLORS.get(ctype, '#888888')
    size  = max(70, row['size'] * 5)
    ax.scatter(
        row['internal_weight_share'],
        row['community_strength'],
        s=size,
        c=color,
        edgecolor='white',
        linewidth=1.2,
        alpha=0.88,
        zorder=3,
    )

# === LABEL MAJOR COMMUNITIES ===
# Offsets to avoid overlap (community id -> (dx, dy_factor))
offsets = {
    10: (0.005, 1.06),
    19: (0.005, 1.05),
    2:  (0.005, 1.05),
    9:  (-0.005, 1.05),
    25: (-0.005, 1.05),
    12: (0.005, 0.94),
    8:  (-0.005, 1.06),
    13: (0.005, 0.94),
    35: (0.005, 1.05),
    20: (0.005, 0.94),
    4:  (0.004, 1.05),
    0:  (0.0015, 1.05),
    24: (0.0015, 0.95),
    7:  (0.0015, 1.05),
}

for _, row in df.iterrows():
    cid = row['community']
    if cid not in SHORT:
        continue
    dx, dy_mul = offsets.get(cid, (0.005, 1.0))
    ha = 'left' if dx > 0 else 'right'
    ax.text(
        row['internal_weight_share'] + dx,
        row['community_strength'] * dy_mul,
        SHORT[cid],
        fontsize=7.5, fontweight='bold',
        color=CHARCOAL, ha=ha, va='center',
        zorder=4,
    )

# === AXES ===
ax.set_xlabel('Internal weight share  (taste self-containment →)',
              fontsize=10.5, color=CHARCOAL, labelpad=8)
ax.set_ylabel('Community strength  (external reach, log scale →)',
              fontsize=10.5, color=CHARCOAL, labelpad=8)
ax.tick_params(axis='both', labelsize=8.5, colors=SLATE)
for spine in ax.spines.values():
    spine.set_color('#CCCCCC')
ax.grid(True, which='major', alpha=0.25, linewidth=0.5)
ax.set_axisbelow(True)

# === TITLE ===
fig.suptitle('Community Role Map',
             fontsize=15, fontweight='bold', color=CHARCOAL,
             x=0.53, y=0.96)
fig.text(0.53, 0.925,
         '43 communities positioned by internal cohesion vs external reach  ·  '
         'point size = community size',
         ha='center', fontsize=9, color=SLATE, style='italic')

# === COMMUNITY-TYPE VOCABULARY LEGEND (inside INSULAR NICHE quadrant) ===
# Place legend in upper portion of bottom-right quadrant, above the
# "INSULAR NICHE" label text. Uses ax-relative coordinates.
legend_order = [
    'temporal_canon',
    'taste_specialist',
    'temporal_artifact',
    'taste_cross_over',
    'shared_culture',
    'bridge_cluster',
    'bridge_singleton',
    'franchise_series',
    'tiny_fragment',
]

# Background pane behind legend.
# Placed in the upper half of the bottom-right (INSULAR NICHE) quadrant,
# leaving the quadrant label intact below it.
legend_box = FancyBboxPatch(
    (0.51, 0.22), 0.48, 0.27,
    boxstyle='round,pad=0.005,rounding_size=0.01',
    facecolor='white', edgecolor='#DDDDDD',
    linewidth=0.8, alpha=0.94,
    transform=ax.transAxes, zorder=4,
)
ax.add_patch(legend_box)

# Legend header
ax.text(0.53, 0.455, 'Community Types',
        fontsize=10, fontweight='bold', color=CHARCOAL,
        transform=ax.transAxes, zorder=5)

# Two-column layout: 5 + 4 items
col1 = legend_order[:5]
col2 = legend_order[5:]

chip_w = 0.022
chip_h = 0.028
row_gap = 0.038
col1_x = 0.53
col2_x = 0.755
top_y  = 0.395

for i, t in enumerate(col1):
    y = top_y - i * row_gap
    ax.add_patch(Rectangle(
        (col1_x, y), chip_w, chip_h,
        facecolor=TYPE_COLORS[t], edgecolor='white', linewidth=0.8,
        transform=ax.transAxes, zorder=5,
    ))
    ax.text(col1_x + chip_w + 0.008, y + chip_h / 2,
            TYPE_LABELS[t],
            fontsize=8, color=CHARCOAL, va='center',
            transform=ax.transAxes, zorder=5)

for i, t in enumerate(col2):
    y = top_y - i * row_gap
    ax.add_patch(Rectangle(
        (col2_x, y), chip_w, chip_h,
        facecolor=TYPE_COLORS[t], edgecolor='white', linewidth=0.8,
        transform=ax.transAxes, zorder=5,
    ))
    ax.text(col2_x + chip_w + 0.008, y + chip_h / 2,
            TYPE_LABELS[t],
            fontsize=8, color=CHARCOAL, va='center',
            transform=ax.transAxes, zorder=5)

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure_role_map.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
