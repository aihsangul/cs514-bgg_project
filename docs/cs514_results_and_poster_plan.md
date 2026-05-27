# CS514 Results And Poster Plan

Last updated: 2026-04-28

This document translates the CS514 network analysis into a report/poster-ready story. It follows the professor's poster guidance in `docs/Poster_Design_Guidelines.pdf`: use a clear grid, one dominant hero finding, sparse text, consistent colors, high contrast, and figures with captions.

## 1. Final Working Title

Behavioral Communities in BoardGameGeek: What Co-Ownership Reveals Beyond Metadata

Alternate shorter poster title:

BoardGameGeek Co-Ownership Reveals Taste, Era, And Bridge-Game Communities

## 2. Research Question

Main question:

> Among engaged BoardGameGeek users, what behavioral communities emerge from game co-ownership, and how do those communities relate to official BGG metadata such as mechanics and categories?

Sharper poster version:

> BGG metadata describes what games are. User collections reveal how games function in the hobby. Do co-ownership networks recover taste communities, or do they reveal different structures such as hobby eras, bridge games, franchise systems, and trend-following behavior?

## 3. One-Sentence Answer

Co-ownership reveals statistically validated game communities, but the strongest finding is that BGG behavior is not organized by taxonomy alone: games act as identity anchors, supplementary collection layers, universal bridge titles, franchise systems, and temporal "new-hotness" signals.

## 4. Hero Finding

Use this as the largest visual/text element on the poster:

> BGG co-ownership is structured, but not only by genre. Historical wargames and classic hobby canon games form identity communities, while recent releases, franchise systems, and universal hits cut across communities and dominate many users' collections.

Poster highlight box candidate:

- Validated midline graph: 2,500 games, 214,379 backbone edges, 43 communities.
- Community detection is stable: median seed NMI = 0.758.
- Structure is significant against the degree-preserving null model: z = 27.31.
- User profiles show only 10.2% clean specialists; most users are mixed, generalist, or dominated by bridge/recent/franchise games.

## 5. Data Story

Data source:

- BoardGameGeek game metadata and user collection data.

Game universe:

- Top-ranked game details collected for 5,000 ranked games.
- Network analysis uses a fixed top-2,500 game universe.

User data:

- Baseline reliable-user cohort:
  - 5,175 reliable users.
  - Discovered from high-visibility/top-ranked game activity.
  - Dense and useful, but biased toward mainstream engaged users.
- Diversity expansion cohort:
  - 478 strict reliable expansion users.
  - Seeded from underrepresented mechanics/categories and rank/wishlist contrasts.
  - Improved 28 / 30 target underrepresented tags by at least 20%.
- Merged analysis cohort:
  - 5,653 strict users.
  - Ownership incidence used for the main graph.

Important framing:

> This is not a neutral sample of all BGG users. It is a dense dataset of engaged BGG users, with targeted expansion to improve underrepresented communities.

## 6. Methods Summary

Network construction:

1. Start from a user-game bipartite ownership graph.
2. Project onto games using a Newman-style user-normalized projection.
3. Each user with `d` owned selected games contributes `1 / (d - 1)` to each induced game-game pair.
4. This limits the dominance of heavy collectors compared with raw co-ownership.
5. Apply a disparity backbone filter to remove weak dense-projection edges.
6. Detect game communities with Louvain across multiple seeds.
7. Validate with stability, metadata enrichment, and a degree-preserving null model.

Main validated setting:

- Signal: ownership.
- Projection: Newman user-normalized.
- Backbone: disparity filter, alpha = 0.025.
- Community resolution: gamma = 1.75.
- Seeds: 20.
- Null model: degree-preserving rewired graph with shuffled weights.

Why this setting:

- It is the highest-resolution tested setting that passes both gates:
  - stability gate: median pairwise NMI >= 0.70.
  - null-model gate: z-score > 2.

## 7. Validation Results

Targeted gamma sweep on the alpha = 0.025 backbone:

| gamma | communities | largest community | median NMI | observed Q | null mean Q | z-score | interpretation |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0.75 | 2 | 56.2% | 0.752 | 0.284 | 0.250 | inf | too coarse |
| 1.00 | 4 | 32.9% | 0.594 | 0.176 | 0.083 | 170.51 | unstable |
| 1.25 | 15 | 25.2% | 0.680 | 0.124 | 0.075 | 135.18 | slightly unstable |
| 1.50 | 32 | 16.6% | 0.703 | 0.094 | 0.071 | 69.22 | valid, coarser |
| 1.75 | 43 | 13.5% | 0.758 | 0.077 | 0.068 | 27.31 | main validated result |
| 2.00 | 57 | 12.3% | 0.767 | 0.064 | 0.066 | -3.46 | descriptive only |

Key interpretation:

> The validated midline is gamma = 1.75. The finer gamma = 2.0 partition is stable and interpretable, but its modularity is not significant against the null model, so it should be used only for descriptive examples.

## 8. Main Game-Community Findings

The validated midline communities reveal several roles that games play in collections.

Identity communities:

- Historical wargames + conflict strategy.
- BGG Golden Age canon.
- Amerithrash / miniatures / LCG.
- Dungeon crawl / cooperative campaign adventure.
- Current heavy euro engine builders.

Supplementary communities:

- Party / family / social deduction.
- Cooperative trick-taking + deduction.
- Puzzle / nature tableau builders.
- Roll-and-write / number dice games.
- Legacy / narrative mystery.

Cross-community structures:

- Recent releases / new-hotness cluster.
- Franchise and series clusters.
- Universal-appeal bridge singletons.
- Tiny fragments around very broadly owned games.

Important example:

> Brass: Birmingham, Ark Nova, and Terraforming Mars do not behave like narrow taste-community games. They land in bridge/tiny/universal clusters because they are owned across many collector types.

## 9. Main User-Archetype Findings

User profiles were built from the 11 accepted taste dimensions plus an `other` catch-all. Users with fewer than 15 selected owned games were filtered from archetype interpretation.

Eligible users:

- 5,125 / 5,504 active ownership users.

Broad archetype families:

| family | users | share of eligible users | interpretation |
|---|---:|---:|---|
| other-dominant | 3,221 | 62.8% | dominated by recent, bridge, franchise, or universal games |
| generalist | 723 | 14.1% | broad ownership across accepted dimensions |
| leaning | 634 | 12.4% | visible taste direction, not a pure specialist |
| specialist | 524 | 10.2% | strong concentration in one accepted dimension |
| mixed | 23 | 0.4% | ambiguous low-concentration profiles |

Core interpretation:

> Most engaged BGG users are not pure specialists. They are multi-dimensional collectors, broad generalists, or users whose collections are dominated by cross-community games.

## 10. What The Other Bucket Means

The `other` bucket is not a failure category. It has a clear structure:

| source of `other` ownership | share |
|---|---:|
| recent-release temporal artifact | 36.1% |
| bridge clusters | 27.8% |
| franchise / series clusters | 17.8% |
| taste-crossover review communities | 7.9% |
| tiny fragments | 7.2% |
| universal-appeal bridge singletons | 3.2% |

Interpretation:

> `other_dominant` users are not one tribe. They include trend followers, cross-genre collectors, and franchise/system collectors.

This is one of the strongest user-level findings.

## 11. Strongest Specific Finding

Historical wargamers are the cleanest specialist community:

- Lowest broad reach among major dimensions: 73.8% of eligible users own any game from the wargame dimension.
- 89 clean specialists.
- High specialist included-share: about 0.902.
- High specialist dominant-share: about 0.575.
- Deep niche games appear strongly among wargame users, not just highly ranked titles.

Poster phrasing:

> Historical wargames are not merely a metadata category. They are an identity community: fewer users enter it, but those who do concentrate heavily inside it.

## 12. Important Limitation

Heavy euro identity is conservatively measured.

Reason:

- Brass: Birmingham, Ark Nova, and Terraforming Mars are central to modern heavy euro taste, but the network places them in bridge/universal/tiny clusters because they are owned across many user types.
- Therefore, users whose heavy-euro identity is built around these games may appear as `other_dominant` rather than heavy-euro leaning/specialist.

Report phrasing:

> The heavy-euro profile score should be interpreted as a conservative estimate because several canonical heavy euros behave as universal bridge games in the co-ownership network.

## 13. Poster Layout

Use a 3-column grid, following the guideline PDF.

Title bar:

- Full width.
- High contrast.
- Title around 72 pt.
- Subtitle with dataset size and method.

Column 1: Motivation and Methods

- Research question.
- Dataset summary.
- Bias correction / diversity expansion.
- Bipartite-to-game projection diagram.
- Methods mini-flow:
  - user-game ownership
  - Newman projection
  - disparity backbone
  - Louvain communities
  - null/stability validation

Column 2: Main Game-Community Result

- Hero highlight box at top.
- Alpha/gamma validation table or compact validation strip.
- Midline community summary figure/table.
- Optional Gephi/network visualization if readable.
- Main text: identity vs supplementary vs bridge/temporal communities.

Column 3: User Archetypes and Conclusion

- User archetype family bar chart.
- `other` decomposition chart.
- Wargame specialist mini-case.
- Limitations.
- Conclusion and references.

## 14. Recommended Figures

Required poster figures:

1. Pipeline diagram:
   - BGG data -> reliable users -> diversity expansion -> user-game graph -> game-game backbone -> communities -> user profiles.

2. Validation strip:
   - gamma sweep table with gamma = 1.75 highlighted.

3. Main community table:
   - community label, size, median year, representative games, interpretation type.

4. Archetype family chart:
   - from `data/processed/cs514_network_analysis/figures/user_archetype_family_counts.png`.

5. Other decomposition chart:
   - from `data/processed/cs514_network_analysis/figures/other_dominant_by_community_type.png`.

Good optional figures:

6. Taste dimension reach vs dominance:
   - from `data/processed/cs514_network_analysis/figures/user_taste_dimension_reach_dominance.png`.

7. Entropy vs dominant-share scatter:
   - from `data/processed/cs514_network_analysis/figures/user_profile_entropy_vs_dominant_share.png`.

8. Coherence gradient:
   - internal weight share by community, if we polish this figure.

## 15. Color And Typography Plan

Use the professor's "Academic Navy & Teal" palette:

- Primary/title: deep navy `#212B36`.
- Accent: teal `#2E86AB`.
- Background: ice blue `#E8F4FD` or white.
- Highlight: coral `#E63946`, used sparingly.
- Panel background: very light neutral.

Typography:

- One sans-serif family throughout, preferably Inter, Helvetica, Arial, or similar.
- Optional monospace only for equations/parameter values.
- Keep font hierarchy simple:
  - title
  - section headings
  - body/captions

## 16. Poster Text Blocks

Motivation:

> BoardGameGeek provides curated metadata for games, but user collections reveal how games are behaviorally positioned by hobbyists. We construct a game-game co-ownership network to compare official taxonomy with revealed collection behavior.

Methods:

> We project a user-game ownership graph onto games using a Newman user-normalized projection, filter the dense projection with a disparity backbone, and detect communities with multi-seed Louvain. We validate the selected resolution using seed stability, metadata enrichment, and a degree-preserving null model.

Main result:

> The validated midline graph contains 43 stable communities and is strongly significant relative to the null model. Communities recover recognizable tastes, but also expose hobby-era effects, universal bridge games, franchise clusters, and temporal trend-following.

User result:

> User profiles show that pure specialists are a minority. Most engaged BGG users are multi-dimensional collectors or are dominated by cross-community games such as recent releases, franchise systems, and universal hits.

Conclusion:

> BGG co-ownership is not just a map of game genres. It is a map of how games function in collections: as identity anchors, supplementary layers, shared cultural touchpoints, and trend signals.

## 17. Final Checklist Before Building Poster

- Pick final title.
- Decide whether to show a network visualization or keep the poster figure/table driven.
- Generate or polish the community summary table.
- Create one clean pipeline diagram.
- Export all figures at high resolution.
- Keep one hero finding visually dominant.
- Limit poster body text aggressively.
- Make sure every figure has a one-sentence caption.
- Use no more than 4 colors.
- Test the poster in grayscale for contrast.
