"""
Figure 1: Vertical pipeline diagram for the Methods panel.
Renders a two-path (graph + matrix) flowchart converging at cross-method validation.
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from pathlib import Path

# === LOCKED BGG PALETTE ===
ORANGE   = '#F58A35'
CHARCOAL = '#212B36'
OFFWHITE = '#F8F9FA'
SLATE    = '#6B7280'
TINT     = '#FFF1E0'   # very light orange for branch backgrounds

# === FIGURE ===
fig, ax = plt.subplots(figsize=(9, 16), dpi=300)
ax.set_xlim(0, 10)
ax.set_ylim(-2.5, 22)
ax.axis('off')
ax.set_aspect('equal')
fig.patch.set_facecolor(OFFWHITE)

# Branch column backgrounds (subtle tint)
ax.add_patch(Rectangle((0.2, 6.5), 4.6, 11.7,
                       facecolor=TINT, alpha=0.35, edgecolor='none'))
ax.add_patch(Rectangle((5.2, 6.5), 4.6, 11.7,
                       facecolor=TINT, alpha=0.35, edgecolor='none'))


# === HELPERS ===
def box(cx, cy, w, h, title, subtitle=None, color=ORANGE, tc='white'):
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.25",
        facecolor=color, edgecolor='none'
    ))
    if subtitle:
        ax.text(cx, cy + 0.25, title, ha='center', va='center',
                color=tc, fontsize=14, fontweight='bold')
        ax.text(cx, cy - 0.4, subtitle, ha='center', va='center',
                color=tc, fontsize=11.5, style='italic')
    else:
        ax.text(cx, cy, title, ha='center', va='center',
                color=tc, fontsize=14, fontweight='bold')


def arrow(x1, y1, x2, y2, color=CHARCOAL, lw=2.5):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle='->,head_width=5,head_length=7',
        color=color, linewidth=lw
    ))


# === COORDS ===
LEFT, RIGHT, CENTER = 2.5, 7.5, 5.0
W, H = 4.5, 1.45

# === INPUT ===
box(CENTER, 20.5, 7, 1.7,
    'USER-GAME OWNERSHIP MATRIX',
    '5,504 users × 2,500 games',
    color=CHARCOAL)

# Split arrows
arrow(CENTER - 1.8, 19.6, LEFT + 0.3, 18.85)
arrow(CENTER + 1.8, 19.6, RIGHT - 0.3, 18.85)

# Branch labels
ax.text(LEFT, 18.3, 'NETWORK PATH', ha='center', va='center',
        color=ORANGE, fontsize=15, fontweight='bold')
ax.text(RIGHT, 18.3, 'MATRIX PATH', ha='center', va='center',
        color=ORANGE, fontsize=15, fontweight='bold')

# === GRAPH PATH (5 steps) ===
graph_y = [16.5, 14.3, 12.1, 9.9, 7.7]
graph_steps = [
    ('Newman Projection',    'user-normalized 1/(d−1)'),
    ('Disparity Filter',     'α = 0.025'),
    ('Louvain Clustering',   'γ = 1.75'),
    ('43 Communities',       'NMI = 0.758 · z = +27.31'),
    ('11 Taste Dimensions',  'manual labeling'),
]
for i, (y, (t, s)) in enumerate(zip(graph_y, graph_steps)):
    color = CHARCOAL if i == 4 else ORANGE
    box(LEFT, y, W, H, t, s, color=color)
    if i < 4:
        arrow(LEFT, y - H / 2 - 0.05, LEFT, graph_y[i + 1] + H / 2 + 0.05)

# === MATRIX PATH (3 steps, wider spacing) ===
matrix_y = [16.5, 12.1, 7.7]
matrix_steps = [
    ('NMF Decomposition',     'on raw matrix'),
    ('k-Sweep + Stability',   'k ∈ {5, 8, 11, 15, 20, 25}'),
    ('Natural k ≈ 15',        'breakdown at k = 20'),
]
for i, (y, (t, s)) in enumerate(zip(matrix_y, matrix_steps)):
    color = CHARCOAL if i == 2 else ORANGE
    box(RIGHT, y, W, H, t, s, color=color)
    if i < 2:
        arrow(RIGHT, y - H / 2 - 0.05, RIGHT, matrix_y[i + 1] + H / 2 + 0.05)

# === CONVERGENCE ===
arrow(LEFT,  7.1, CENTER - 1.2, 5.05)
arrow(RIGHT, 7.1, CENTER + 1.2, 5.05)

box(CENTER, 4.2, 7.5, 1.7,
    'CROSS-METHOD VALIDATION',
    'cosine similarity, Hungarian matching',
    color=CHARCOAL)
arrow(CENTER, 3.35, CENTER, 2.55)

# === VALIDATION OUTCOME ===
box(CENTER, 1.7, 8, 1.7,
    '8 of 11 taste dimensions recovered',
    'median cosine = 0.674',
    color=ORANGE)

# === APPLICATION: User Profiling (final box) ===
arrow(CENTER, 0.85, CENTER, -0.3)

box(CENTER, -1.2, 8, 1.7,
    'User Taste Profiling',
    '5,125 users · 12-vector profiles',
    color=CHARCOAL)

# === SAVE ===
out_path = Path('data/processed/cs514_network_analysis/figures/poster/figure1_pipeline_diagram.png')
out_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out_path, dpi=300, bbox_inches='tight', facecolor=OFFWHITE)
plt.close()
print(f'Saved: {out_path}')
