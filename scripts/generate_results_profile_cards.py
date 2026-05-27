"""
Results Figure: Community Profile Cards (2x2 grid)
4 representative communities, each showing:
- name + type pill
- size, internal share, median year
- top 3 games (with BGG rank)
- strongest mechanic enrichment
- one-sentence structural role
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from pathlib import Path

# === PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'
TINT     = '#FFF1E0'

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

TYPE_LABEL = {
    'taste_specialist':  'Taste specialist',
    'temporal_canon':    'Temporal canon',
    'temporal_artifact': 'Temporal artifact',
    'bridge_cluster':    'Bridge cluster',
    'bridge_singleton':  'Bridge singleton',
    'franchise_series':  'Franchise / series',
    'taste_cross_over':  'Taste cross-over',
}

# === DATA ===
CARDS = [
    {
        'title':       'BGG Golden Age Canon',
        'type':        'temporal_canon',
        'size':        338,
        'internal':    19.5,
        'median_year': 2004,
        'top_games':   [('Puerto Rico', 55), ('Agricola', 64), ('Power Grid', 74)],
        'top_mech':    ('Enclosure', '3.8x'),
        'top_cat':     ('Abstract Strategy', '3.0x'),
        'role':        'Cross-era anchor — pre-2010 games owned by collectors of every taste.',
    },
    {
        'title':       'Current Heavy Euros',
        'type':        'taste_specialist',
        'size':        207,
        'internal':    17.9,
        'median_year': 2022,
        'top_games':   [('Gaia Project', 13), ('SETI', 16), ('A Feast for Odin', 27)],
        'top_mech':    ('Worker Placement: Diff. Types', '5.3x'),
        'top_cat':     ('Industry / Manufacturing', '5.0x'),
        'role':        'Modern weight-3+ heart of the hobby — engine-builder taste community.',
    },
    {
        'title':       'Historical Wargames',
        'type':        'taste_specialist',
        'size':        198,
        'internal':    19.0,
        'median_year': 2012,
        'top_games':   [('War of the Ring (2e)', 8), ('Twilight Struggle', 14), ('Brass: Lancashire', 23)],
        'top_mech':    ('Ratio / Combat Results Table', '11.8x'),
        'top_cat':     ('Modern Warfare', '9.8x'),
        'role':        'Insular specialist identity — strongest metadata enrichment of any community.',
    },
    {
        'title':       'Dungeon Crawl / Campaign',
        'type':        'taste_specialist',
        'size':        231,
        'internal':    13.7,
        'median_year': 2021,
        'top_games':   [('Gloomhaven', 4), ('Spirit Island', 11), ('Gloomhaven: Jaws of the Lion', 12)],
        'top_mech':    ('Scenario / Campaign Game', '5.1x'),
        'top_cat':     ('Adventure', '4.4x'),
        'role':        'Long-arc cooperative campaigns — the cooperative thematic specialist cluster.',
    },
]

# === FIGURE ===
fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), dpi=300)
fig.patch.set_facecolor(OFFWHITE)
fig.suptitle('Community Profiles: Four Representative Anchor Communities',
             fontsize=14, fontweight='bold', color=CHARCOAL, y=0.965)
fig.text(0.5, 0.93,
         'Each card shows community size, taste self-containment, top games, and strongest metadata signal',
         ha='center', fontsize=8.5, color=SLATE, style='italic')

axes = axes.flatten()

# === DRAW EACH CARD ===
def draw_card(ax, card):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    ax.set_facecolor(OFFWHITE)

    # Card outer rectangle
    card_bg = FancyBboxPatch(
        (0.02, 0.02), 0.96, 0.96,
        boxstyle='round,pad=0.01,rounding_size=0.025',
        facecolor='white',
        edgecolor='#DDDDDD',
        linewidth=1.0,
        transform=ax.transAxes,
        zorder=1,
    )
    ax.add_patch(card_bg)

    ctype     = card['type']
    type_clr  = TYPE_COLORS[ctype]
    type_text = TYPE_LABEL[ctype]

    # Header bar (colored band)
    header = FancyBboxPatch(
        (0.02, 0.80), 0.96, 0.18,
        boxstyle='round,pad=0.005,rounding_size=0.025',
        facecolor=type_clr,
        edgecolor='none',
        transform=ax.transAxes,
        zorder=2,
    )
    ax.add_patch(header)

    # Title (community name)
    ax.text(0.06, 0.92, card['title'],
            fontsize=14, fontweight='bold', color='white',
            transform=ax.transAxes, va='center')

    # Type pill (sub-header)
    ax.text(0.06, 0.84, type_text.upper(),
            fontsize=8, color='white', fontweight='bold',
            transform=ax.transAxes, va='center', alpha=0.85,
            family='monospace')

    # Stat row: size | internal share | median year
    stat_y = 0.71
    stat_label_y = 0.65
    stats = [
        (f"{card['size']}",          'games',           0.18),
        (f"{card['internal']:.1f}%", 'internal share',  0.50),
        (f"{card['median_year']}",   'median year',     0.82),
    ]
    for value, label, x in stats:
        ax.text(x, stat_y, value,
                fontsize=18, fontweight='bold', color=CHARCOAL,
                transform=ax.transAxes, ha='center', va='center')
        ax.text(x, stat_label_y, label,
                fontsize=8, color=SLATE,
                transform=ax.transAxes, ha='center', va='center')

    # Stat row dividers
    ax.plot([0.34, 0.34], [stat_label_y - 0.02, stat_y + 0.04],
            color='#EEEEEE', linewidth=1, transform=ax.transAxes, zorder=3)
    ax.plot([0.66, 0.66], [stat_label_y - 0.02, stat_y + 0.04],
            color='#EEEEEE', linewidth=1, transform=ax.transAxes, zorder=3)

    # Section: Top games
    ax.text(0.06, 0.56, 'TOP GAMES',
            fontsize=8, fontweight='bold', color=SLATE,
            transform=ax.transAxes, family='monospace')
    for i, (game, rank) in enumerate(card['top_games']):
        y = 0.50 - i * 0.055
        ax.text(0.06, y, game,
                fontsize=10, color=CHARCOAL, fontweight='bold',
                transform=ax.transAxes, va='center')
        # Rank pill on the right
        rank_clr = ORANGE if rank <= 25 else CHARCOAL
        ax.text(0.94, y, f'#{rank}',
                fontsize=9, color=rank_clr,
                fontweight='bold',
                transform=ax.transAxes, ha='right', va='center')

    # Section: Strongest signal
    ax.text(0.06, 0.30, 'STRONGEST SIGNAL',
            fontsize=8, fontweight='bold', color=SLATE,
            transform=ax.transAxes, family='monospace')
    mech_name, mech_fold = card['top_mech']
    cat_name,  cat_fold  = card['top_cat']
    ax.text(0.06, 0.24, f'{cat_name}',
            fontsize=9.5, color=CHARCOAL,
            transform=ax.transAxes, va='center')
    ax.text(0.94, 0.24, cat_fold,
            fontsize=9.5, color=ORANGE, fontweight='bold',
            transform=ax.transAxes, ha='right', va='center')
    ax.text(0.06, 0.185, f'{mech_name}',
            fontsize=9.5, color=CHARCOAL,
            transform=ax.transAxes, va='center')
    ax.text(0.94, 0.185, mech_fold,
            fontsize=9.5, color=ORANGE, fontweight='bold',
            transform=ax.transAxes, ha='right', va='center')

    # Role description (footer)
    ax.add_patch(Rectangle((0.02, 0.04), 0.96, 0.10,
                           facecolor=TINT, alpha=0.6,
                           edgecolor='none',
                           transform=ax.transAxes, zorder=2))
    ax.text(0.5, 0.09, card['role'],
            fontsize=8.5, color=CHARCOAL,
            transform=ax.transAxes, ha='center', va='center',
            style='italic', wrap=True)


for ax, card in zip(axes, CARDS):
    draw_card(ax, card)

plt.tight_layout(rect=[0, 0, 1, 0.92], h_pad=2.0, w_pad=2.0)

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure_profile_cards.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
