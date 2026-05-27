"""
Results Figure: Catalog Share by Community Type
Horizontal bar showing the catalog weight of each of the 9 community types.
Reveals that most of the catalog lives in a handful of large taste-coherent
communities, while most of the communities themselves are small bridges and
fragments.
"""

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
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

# === LOAD & AGGREGATE ===
base = Path('data/processed/cs514_network_analysis')
df = pd.read_csv(base / 'structural_analysis/community_condensation_nodes.csv')

agg = (
    df.groupby('community_type')
      .agg(n_games=('size', 'sum'),
           n_communities=('community', 'count'))
      .reset_index()
      .sort_values('n_games', ascending=True)   # ascending so largest is on top in barh
)

total_games        = int(agg['n_games'].sum())
total_communities  = int(agg['n_communities'].sum())

# === FIGURE ===
fig, ax = plt.subplots(figsize=(10, 5.8), dpi=300)
fig.patch.set_facecolor(OFFWHITE)
ax.set_facecolor(OFFWHITE)

y_pos    = range(len(agg))
n_games  = agg['n_games'].values
n_comms  = agg['n_communities'].values
labels   = [TYPE_LABELS[t] for t in agg['community_type']]
colors   = [TYPE_COLORS[t] for t in agg['community_type']]

bars = ax.barh(
    y_pos, n_games,
    height=0.65,
    color=colors,
    edgecolor='white', linewidth=1.4,
)

# === ANNOTATIONS ===
xmax = float(n_games.max())
for i, (bar, games, comms) in enumerate(zip(bars, n_games, n_comms)):
    x_end = bar.get_width()
    y_c   = bar.get_y() + bar.get_height() / 2

    pct = 100.0 * games / total_games

    # Primary value: game count + percentage
    ax.text(x_end + xmax * 0.012, y_c,
            f'{games:,}  ({pct:.1f}%)',
            fontsize=9.5, color=CHARCOAL, fontweight='bold',
            va='center', ha='left')

    # Secondary: number of communities, smaller
    comm_label = f'{comms} community' if comms == 1 else f'{comms} communities'
    ax.text(x_end + xmax * 0.012, y_c - 0.32,
            comm_label,
            fontsize=7.5, color=SLATE, va='center', ha='left',
            style='italic')

# === AXES ===
ax.set_yticks(list(y_pos))
ax.set_yticklabels(labels, fontsize=10, color=CHARCOAL)
ax.set_xlabel('Number of games in catalog', fontsize=10, color=SLATE, labelpad=8)
ax.set_xlim(0, xmax * 1.32)
ax.tick_params(axis='x', labelsize=8.5, colors=SLATE)
ax.tick_params(axis='y', length=0)
ax.spines[['top', 'right']].set_visible(False)
ax.spines['bottom'].set_color('#DDDDDD')
ax.spines['left'].set_color('#DDDDDD')
ax.xaxis.grid(True, color='#DDDDDD', linestyle='--', linewidth=0.6, alpha=0.65)
ax.set_axisbelow(True)

# === TITLE ===
fig.suptitle('Catalog Share by Community Type',
             fontsize=14, fontweight='bold', color=CHARCOAL,
             x=0.06, y=0.97, ha='left')
fig.text(0.06, 0.925,
         f'{total_games:,} games across {total_communities} communities  ·  '
         f'how the catalog distributes across the 9 structural types',
         ha='left', fontsize=9, color=SLATE, style='italic')

# === INSIGHT CALLOUT ===
# Two large types vs the long tail
core_types = {'taste_specialist', 'temporal_canon', 'temporal_artifact'}
core_games = int(agg.loc[agg['community_type'].isin(core_types), 'n_games'].sum())
core_comms = int(agg.loc[agg['community_type'].isin(core_types), 'n_communities'].sum())
core_pct   = 100.0 * core_games / total_games

tail_types = {'bridge_cluster', 'bridge_singleton', 'franchise_series', 'tiny_fragment'}
tail_games = int(agg.loc[agg['community_type'].isin(tail_types), 'n_games'].sum())
tail_comms = int(agg.loc[agg['community_type'].isin(tail_types), 'n_communities'].sum())
tail_pct   = 100.0 * tail_games / total_games

callout_text = (
    f'{core_comms} large taste-coherent communities hold {core_pct:.0f}% of the catalog  ·  '
    f'{tail_comms} small bridge & franchise communities hold just {tail_pct:.0f}%'
)
fig.text(0.5, 0.025, callout_text,
         ha='center', fontsize=8.5, color=CHARCOAL,
         fontweight='bold', style='italic')

plt.tight_layout(rect=[0, 0.05, 1, 0.91])

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure_catalog_share.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
