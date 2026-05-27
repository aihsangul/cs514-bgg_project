"""
Main Findings hero figure for the poster Conclusion section.
Target box: 54.4 cm width x 12.65 cm height (21.4 in x 4.98 in) - wide short bar.

Contents (left -> right):
  - Title only: "Main Finding: Most Collectors Are Cross-Community"  (Arial bold 36 pt, top)
  - Archetype donut + compact legend
  - Visual arrow indicator linking other-dominant slice to the cards
  - 3 explanation cards horizontally: TEMPORAL / BRIDGE / FRANCHISE
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from pathlib import Path

# === FONT DEFAULTS ===
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']

TITLE_FONT = {'fontname': 'Arial', 'fontweight': 'bold'}
BODY_FONT  = {'fontname': 'Helvetica'}

# === BGG PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'

# Decomposition card colors (match other figures)
DECOMP_TEMPORAL = '#8B5E3C'
DECOMP_BRIDGE   = '#4A90D9'
DECOMP_FRAN     = '#9B59B6'

# Archetype data
ARCH_LABELS = ['Other-dominant', 'Generalist', 'Leaning', 'Specialist', 'Mixed']
ARCH_PCTS   = [62.85, 14.11, 12.37, 10.22, 0.45]
ARCH_COLORS = [CHARCOAL, '#4A90D9', '#F0A500', ORANGE, SLATE]

# === FIGURE (54.4 cm wide x 12.65 cm tall) ===
fig = plt.figure(figsize=(21.4, 4.98), dpi=300)
fig.patch.set_facecolor(OFFWHITE)

# ─────────────────────────────────────────────────────────────────────────
# TITLE (Arial bold 36pt) — single line, top
# ─────────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.90,
         'Main Finding: Most Collectors Are Cross-Community',
         fontsize=36, color=CHARCOAL,
         ha='center', va='center',
         **TITLE_FONT)

# Orange divider line under title
fig.add_artist(Rectangle((0.025, 0.785), 0.95, 0.008,
                         facecolor=ORANGE, edgecolor='none',
                         transform=fig.transFigure))

# ─────────────────────────────────────────────────────────────────────────
# DONUT (archetype distribution) — left side
# ─────────────────────────────────────────────────────────────────────────
ax_donut = fig.add_axes([0.025, 0.07, 0.14, 0.66])
ax_donut.set_aspect('equal')
ax_donut.axis('off')

wedges, _ = ax_donut.pie(
    ARCH_PCTS,
    colors=ARCH_COLORS,
    startangle=90,
    counterclock=False,
    wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2.5),
)

# Hero number in donut center
ax_donut.text(0, 0.13, '62.9%',
              ha='center', va='center',
              fontsize=26, fontweight='bold', color=CHARCOAL,
              **BODY_FONT)
ax_donut.text(0, -0.20, 'other-dominant\nusers',
              ha='center', va='center',
              fontsize=9.5, color=SLATE,
              linespacing=1.3,
              **BODY_FONT)

ax_donut.set_xlim(-1.3, 1.3)
ax_donut.set_ylim(-1.3, 1.3)

# ─────────────────────────────────────────────────────────────────────────
# ARCHETYPE LEGEND (right of donut)
# ─────────────────────────────────────────────────────────────────────────
ax_leg = fig.add_axes([0.165, 0.10, 0.115, 0.60])
ax_leg.set_xlim(0, 1)
ax_leg.set_ylim(0, 1)
ax_leg.axis('off')

leg_top = 0.92
leg_gap = 0.20
for i, (label, pct, color) in enumerate(zip(ARCH_LABELS, ARCH_PCTS, ARCH_COLORS)):
    y = leg_top - i * leg_gap
    # chip
    ax_leg.add_patch(Rectangle(
        (0.00, y - 0.05), 0.10, 0.10,
        facecolor=color, edgecolor='white', linewidth=1,
    ))
    # label
    ax_leg.text(0.15, y, label,
                fontsize=10.5, color=CHARCOAL,
                va='center', fontweight='bold',
                **BODY_FONT)
    # pct
    ax_leg.text(1.00, y, f'{pct:.1f}%',
                fontsize=10.5, color=SLATE,
                va='center', ha='right',
                **BODY_FONT)

# ─────────────────────────────────────────────────────────────────────────
# ARROW INDICATOR — from "other-dominant" slice rightward to the cards
# ─────────────────────────────────────────────────────────────────────────
ax_arrow = fig.add_axes([0.285, 0.30, 0.05, 0.22])
ax_arrow.set_xlim(0, 1)
ax_arrow.set_ylim(0, 1)
ax_arrow.axis('off')

arrow = FancyArrowPatch(
    (0.05, 0.5), (0.95, 0.5),
    arrowstyle='-|>,head_width=10,head_length=14',
    color=ORANGE, linewidth=4,
    mutation_scale=20,
)
ax_arrow.add_patch(arrow)

# ─────────────────────────────────────────────────────────────────────────
# THREE EXPLANATION CARDS (horizontal row, right side)
# ─────────────────────────────────────────────────────────────────────────
cards = [
    {
        'title': 'TEMPORAL',
        'pct':   '36.1%',
        'color': DECOMP_TEMPORAL,
        'sub':   'Recent releases & new-hotness',
        'body_lines': [
            'Games owned because of when they',
            'came out, not what they are.',
        ],
    },
    {
        'title': 'BRIDGE',
        'pct':   '27.8%',
        'color': DECOMP_BRIDGE,
        'sub':   'Cross-genre crowd-pleasers',
        'body_lines': [
            'Games that connect otherwise separate',
            'tastes — Azul, Carcassonne, Wingspan.',
        ],
    },
    {
        'title': 'FRANCHISE',
        'pct':   '17.8%',
        'color': DECOMP_FRAN,
        'sub':   'System loyalty',
        'body_lines': [
            'Series collectors — Pandemic family,',
            'Unmatched, Ticket to Ride, Catan.',
        ],
    },
]

# Card layout: x from 0.345 to 0.985, with 3 cards and 2 gaps
card_x_start = 0.345
card_x_end   = 0.985
card_gap     = 0.012
card_w       = (card_x_end - card_x_start - 2 * card_gap) / 3
card_y       = 0.07
card_h       = 0.66

for i, card in enumerate(cards):
    x = card_x_start + i * (card_w + card_gap)
    ax_card = fig.add_axes([x, card_y, card_w, card_h])
    ax_card.set_xlim(0, 1)
    ax_card.set_ylim(0, 1)
    ax_card.axis('off')

    # Card background
    ax_card.add_patch(FancyBboxPatch(
        (0.005, 0.01), 0.99, 0.98,
        boxstyle='round,pad=0.005,rounding_size=0.04',
        facecolor='white', edgecolor='#DDDDDD', linewidth=1.0,
    ))

    # Colored top stripe
    ax_card.add_patch(Rectangle(
        (0.005, 0.78), 0.99, 0.21,
        facecolor=card['color'], edgecolor='none',
    ))

    # Stripe content: title (left) + percentage (right)
    ax_card.text(0.035, 0.885, card['title'],
                 fontsize=15, fontweight='bold', color='white',
                 va='center', family='monospace')
    ax_card.text(0.965, 0.885, card['pct'],
                 fontsize=20, fontweight='bold', color='white',
                 va='center', ha='right',
                 **BODY_FONT)

    # Subtitle (under stripe) - the sub line is needed to label each card type
    ax_card.text(0.035, 0.62, card['sub'],
                 fontsize=12, fontweight='bold', color=CHARCOAL,
                 va='center',
                 **BODY_FONT)

    # Divider line under subtitle
    ax_card.add_patch(Rectangle((0.035, 0.50), 0.93, 0.005,
                                facecolor='#EEEEEE', edgecolor='none'))

    # Body lines
    body_top = 0.36
    body_gap = 0.16
    for j, line in enumerate(card['body_lines']):
        ax_card.text(0.035, body_top - j * body_gap, line,
                     fontsize=10.5, color=SLATE, va='center',
                     **BODY_FONT)

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure_main_finding_hero.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE, pad_inches=0.15)
plt.close()
print(f'Saved: {out}')
