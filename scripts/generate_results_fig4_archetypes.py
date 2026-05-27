"""
Results Figure 4: User Archetype Distribution
Left: donut chart — 5 archetype families.
Right: horizontal bar — other-dominant decomposition by community type.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# === PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'

# === DATA (from archetype_family_summary.csv, eligible users only) ===
# pct_eligible_users column
ARCHETYPE_LABELS = ['Other-dominant', 'Generalist', 'Leaning', 'Specialist', 'Mixed']
ARCHETYPE_PCTS   = [62.85, 14.11, 12.37, 10.22, 0.45]
ARCHETYPE_COLORS = [CHARCOAL, '#4A90D9', '#F0A500', ORANGE, SLATE]

# Other-dominant decomposition by community_type (from other_dominant_decomposition.csv)
DECOMP_LABELS = [
    'Temporal artifact',
    'Bridge cluster',
    'Franchise / series',
    'Taste cross-over',
    'Tiny fragment',
    'Bridge singleton',
]
DECOMP_PCTS   = [36.1, 27.8, 17.8, 7.9, 7.2, 3.2]
DECOMP_COLORS = [
    '#8B5E3C',   # temporal artifact — warm brown
    '#4A90D9',   # bridge cluster — blue
    '#9B59B6',   # franchise — purple
    '#F0A500',   # taste cross-over — amber
    '#C8C8C8',   # tiny fragment — gray
    '#E63946',   # bridge singleton — red
]

# === FIGURE ===
fig, (ax_donut, ax_bar) = plt.subplots(1, 2, figsize=(12, 5.5), dpi=300)
fig.patch.set_facecolor(OFFWHITE)

# ── DONUT ──────────────────────────────────────────────────────────────────
wedge_props = dict(width=0.42, edgecolor='white', linewidth=2)
wedges, _ = ax_donut.pie(
    ARCHETYPE_PCTS,
    colors=ARCHETYPE_COLORS,
    startangle=90,
    counterclock=False,
    wedgeprops=wedge_props,
)

# Centre annotation
ax_donut.text(0, 0.08, '5,125', ha='center', va='center',
              fontsize=19, fontweight='bold', color=CHARCOAL)
ax_donut.text(0, -0.22, 'eligible\nusers', ha='center', va='center',
              fontsize=9, color=SLATE, linespacing=1.3)

# Callout labels for large slices
for wedge, pct, label in zip(wedges, ARCHETYPE_PCTS, ARCHETYPE_LABELS):
    if pct < 1.5:
        continue
    angle = (wedge.theta1 + wedge.theta2) / 2
    rad   = np.deg2rad(angle)

    # Large slice: push label further left to avoid right-edge clip
    r_label = 1.05 if pct > 30 else 0.90
    x = r_label * np.cos(rad)
    y = r_label * np.sin(rad)

    r_tip = 0.62
    x_tip = r_tip * np.cos(rad)
    y_tip = r_tip * np.sin(rad)

    # Horizontal alignment: keep large left-side label from going off left edge
    ha = 'right' if x < -0.1 else ('left' if x > 0.1 else 'center')

    ax_donut.annotate(
        f'{pct:.1f}%\n{label}',
        xy=(x_tip, y_tip), xytext=(x, y),
        ha=ha, va='center', fontsize=8,
        color=CHARCOAL, fontweight='bold',
        linespacing=1.2,
        arrowprops=dict(arrowstyle='-', color='#AAAAAA', lw=0.8)
    )

# Give horizontal room for labels on both sides
ax_donut.set_xlim(-1.7, 1.7)

ax_donut.set_title('User Archetype Distribution\n(eligible users, n = 5,125)',
                   fontsize=11, fontweight='bold', color=CHARCOAL, pad=8)

# ── DECOMPOSITION BAR ──────────────────────────────────────────────────────
ax_bar.set_facecolor(OFFWHITE)

y_pos   = np.arange(len(DECOMP_LABELS))
bar_h   = 0.55

bars = ax_bar.barh(
    y_pos, DECOMP_PCTS,
    height=bar_h,
    color=DECOMP_COLORS,
    edgecolor='white', linewidth=1.2
)

# Value labels on bars
for bar, pct in zip(bars, DECOMP_PCTS):
    x_pos = bar.get_width()
    ax_bar.text(x_pos + 0.5, bar.get_y() + bar.get_height() / 2,
                f'{pct:.1f}%',
                va='center', ha='left', fontsize=9, color=CHARCOAL, fontweight='bold')

ax_bar.set_yticks(y_pos)
ax_bar.set_yticklabels(DECOMP_LABELS, fontsize=9.5, color=CHARCOAL)
ax_bar.set_xlabel('Share of "other" ownership edges (%)', fontsize=9, color=SLATE)
ax_bar.set_xlim(0, 45)
ax_bar.set_title(
    'What Drives "Other-Dominant" Users?\n(decomposition by community type)',
    fontsize=11, fontweight='bold', color=CHARCOAL, pad=8
)
ax_bar.tick_params(axis='x', labelsize=8, colors=SLATE)
ax_bar.tick_params(axis='y', length=0)
ax_bar.spines[['top', 'right', 'bottom']].set_visible(False)
ax_bar.spines['left'].set_color('#DDDDDD')
ax_bar.xaxis.grid(True, color='#DDDDDD', linestyle='--', linewidth=0.6, alpha=0.7)
ax_bar.set_axisbelow(True)

# Highlight temporal artifact bar with annotation
ax_bar.annotate(
    'Shared canon\n& new releases\ndrive 64%',
    xy=(36.1, 5), xytext=(36.1, 3.6),
    fontsize=7.5, color='#8B5E3C', ha='center',
    arrowprops=dict(arrowstyle='->', color='#8B5E3C', lw=1.2)
)

plt.tight_layout(pad=2.0)

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure4_archetypes.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
