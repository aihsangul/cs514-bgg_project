"""
Results Figure: Community Condensation Network
43-node community graph, top-80 edges, colored by community type.
"""

import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# === PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'

TYPE_COLORS = {
    'taste_specialist':  '#F58A35',   # orange — core taste communities
    'temporal_canon':    '#212B36',   # charcoal — BGG golden age
    'temporal_artifact': '#8B5E3C',   # warm brown — new hotness
    'bridge_cluster':    '#4A90D9',   # blue — cross-community bridges
    'bridge_singleton':  '#E63946',   # red — universal-appeal outliers
    'franchise_series':  '#9B59B6',   # purple — franchise/series clusters
    'taste_cross_over':  '#F0A500',   # amber — taste crossover
    'shared_culture':    '#2E8B57',   # green — shared cultural layer
    'tiny_fragment':     '#C8C8C8',   # light gray — small fragments
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

# Short display labels for large communities
SHORT_LABELS = {
    'BGG Golden Age canon':                          'BGG\nCanon',
    'Recent releases / new-hotness cluster':         'New\nHotness',
    'Current heavy euro engine builders':            'Heavy\nEuros',
    'Amerithrash / miniatures / LCG':               'Amerithrash',
    'Party / family / social deduction':             'Party /\nFamily',
    'Dungeon crawl / cooperative campaign adventure':'Dungeon\nCrawl',
    'Medium worker-placement euros':                 'Worker\nPlacement',
    'Puzzle / nature tableau builders':              'Puzzle /\nNature',
    'Historical wargames + conflict strategy':       'Wargames',
    'Cooperative trick-taking + deduction':          'Coop /\nDeduction',
    'Terraforming Mars universal-appeal micro-cluster': 'TM',
    'Ark Nova universal-appeal micro-cluster':       'Ark\nNova',
}

# === LOAD DATA ===
base = Path('data/processed/cs514_network_analysis')
nodes_df = pd.read_csv(base / 'structural_analysis/community_condensation_nodes.csv')
edges_df = pd.read_csv(base / 'structural_analysis/community_condensation_edges.csv')

# Top 80 edges by weight
edges_df = edges_df.nlargest(80, 'weight')

# Only keep nodes that appear in at least one top-80 edge
active_nodes = set(edges_df['community_a']) | set(edges_df['community_b'])
nodes_df = nodes_df[nodes_df['community'].isin(active_nodes)].copy()

# === BUILD GRAPH ===
G = nx.Graph()
for _, row in nodes_df.iterrows():
    G.add_node(
        row['community'],
        label=str(row['label']) if pd.notna(row['label']) else '',
        community_type=row['community_type'],
        size=int(row['size'])
    )

for _, row in edges_df.iterrows():
    if row['community_a'] in G.nodes and row['community_b'] in G.nodes:
        G.add_edge(row['community_a'], row['community_b'], weight=float(row['weight']))

# Normalize edge weights for layout (log scale prevents hub collapse)
log_weights = {(u, v): np.log1p(d['weight']) for u, v, d in G.edges(data=True)}
nx.set_edge_attributes(G, {e: {'log_weight': w} for e, w in log_weights.items()})

# === LAYOUT ===
# Kamada-Kawai gives much better separation than spring for weighted graphs
pos = nx.kamada_kawai_layout(G, weight='log_weight')

# === NODE ATTRIBUTES ===
node_list   = list(G.nodes)
node_colors = [TYPE_COLORS.get(G.nodes[n]['community_type'], '#AAAAAA') for n in node_list]
node_sizes  = [max(60, G.nodes[n]['size'] * 5) for n in node_list]

# === EDGE ATTRIBUTES ===
edges_list   = list(G.edges)
edge_weights = [G[u][v]['weight'] for u, v in edges_list]
max_w = max(edge_weights)
edge_widths  = [0.2 + 3.5 * (w / max_w) for w in edge_weights]
edge_alphas  = [0.15 + 0.55 * (w / max_w) for w in edge_weights]

# === DRAW ===
fig, ax = plt.subplots(figsize=(10, 10), dpi=300)
fig.patch.set_facecolor(OFFWHITE)
ax.set_facecolor(OFFWHITE)

# Edges (manual draw for per-edge alpha)
for (u, v), lw, alpha in zip(edges_list, edge_widths, edge_alphas):
    x = [pos[u][0], pos[v][0]]
    y = [pos[u][1], pos[v][1]]
    ax.plot(x, y, color=CHARCOAL, linewidth=lw, alpha=alpha, zorder=1, solid_capstyle='round')

# Nodes
sc = nx.draw_networkx_nodes(
    G, pos, ax=ax,
    nodelist=node_list,
    node_color=node_colors,
    node_size=node_sizes,
    alpha=0.92,
    linewidths=0.5,
    edgecolors='white',
)
sc.set_zorder(2)

# Labels for communities with size >= 40
for n in node_list:
    nd = G.nodes[n]
    if nd['size'] >= 40:
        raw_label = nd['label']
        short = SHORT_LABELS.get(raw_label, raw_label.split('/')[0].strip()[:15])
        fontsize = 6.5 if nd['size'] >= 150 else 5.5
        ax.text(
            pos[n][0], pos[n][1], short,
            ha='center', va='center',
            fontsize=fontsize, fontweight='bold',
            color='white', zorder=3,
            linespacing=1.1
        )

# === LEGEND ===
# Only show types that actually appear
used_types = set(G.nodes[n]['community_type'] for n in G.nodes)
legend_patches = [
    mpatches.Patch(facecolor=TYPE_COLORS[t], label=TYPE_LABELS[t], edgecolor='white', linewidth=0.5)
    for t in TYPE_COLORS if t in used_types
]
legend = ax.legend(
    handles=legend_patches,
    loc='lower left',
    fontsize=7.5,
    framealpha=0.92,
    facecolor=OFFWHITE,
    edgecolor='#CCCCCC',
    title='Community type',
    title_fontsize=8.5,
    handlelength=1.2,
    handleheight=1.0,
)
legend.get_title().set_color(CHARCOAL)
legend.get_title().set_fontweight('bold')

ax.set_title(
    'Co-Ownership Community Condensation Graph',
    fontsize=13, fontweight='bold', color=CHARCOAL, pad=12
)
ax.text(0.5, -0.01,
        '43 communities · top-80 inter-community edges · node size = community size · edge weight = co-ownership strength',
        ha='center', va='top', transform=ax.transAxes,
        fontsize=7, color='#6B7280', style='italic')
ax.axis('off')

# === SAVE ===
out = Path('data/processed/cs514_network_analysis/figures/poster/figure_network.png')
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out}')
