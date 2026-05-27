# CS514 Analysis Log

This file is the living record for the CS514 Network Science project. It summarizes what I did, why I did it, where the outputs live, what the current findings mean, and what still needs to be decided before the final report/poster.

Last updated: 2026-04-28

## 1. Current Research Question

Working question:

> Among engaged BoardGameGeek users, what behavioral communities emerge from game co-ownership, and how do those communities relate to official BGG metadata such as mechanics and categories?

Sharper current framing:

> BGG metadata describes what games are, while user collections reveal how games are behaviorally positioned in the hobby. I study whether co-ownership communities recover official taxonomy, and where they instead reveal taste subcultures, hobby-era effects, shared cultural touchpoints, or franchise collecting patterns.

Current thesis direction:

> BGG co-ownership has statistically significant broad structure. At finer resolutions, communities reveal interpretable behavioral patterns, but these patterns include more than taste alone: they also reflect hobby era, bridge games, and series/franchise collection behavior.

Current validated midline update:

> A targeted gamma/null sweep on the `alpha=0.025` backbone found a validated midline at `gamma=1.75`: 43 communities, largest community about 13.5% of games, median seed NMI about 0.758, and null-model z-score about 27.31. This setting is now the best candidate for the main statistically defensible community result.

## 2. Data Source And Game Universe

Source: BoardGameGeek.

Game data collected:

- Detailed data for the top 5,000 ranked games.
- Main file:
  - `data/processed/top_ranked_games_details/top_ranked_games_details_top5000_ranked_only/top_ranked_games_details.csv`
- Includes:
  - ranks
  - ratings
  - comments
  - mechanics
  - categories
  - weight
  - player counts
  - designers
  - publishers
  - ownership/wishlist/wanting signals

Network-analysis game universe:

- Fixed set of 2,500 selected games.
- These are the game nodes used in the main CS514 game-game networks.
- Metadata is used as node attributes and for interpretation, not as input to the behavioral graph construction.

## 3. Baseline Reliable User Dataset

Baseline run label:

- `reliable_users_batch1`

Main folder:

- `data/processed/reliable_users/reliable_users_batch1/`

Important files:

- `reliable_users.csv`
- `reliable_user_collection_edges.csv`
- `all_user_summaries.csv`
- `all_user_collection_edges.csv`
- `dataset_quality_report.txt`
- `taxonomy_coverage_report.txt`

Baseline construction summary:

1. Started from top-ranked/high-visibility seed games.
2. Discovered candidate users from activity around those games.
3. Fetched each candidate user's BGG collection.
4. Applied reliability filters.
5. Built user-game collection edges for selected games and broader collection behavior.

Baseline status after ratings backfill:

- reliable users: 5,175
- selected games: 2,500
- total user-game edges: 2,927,568
- selected top-2500 subgraph edges: 1,363,947
- edges with user_rating: 1,463,684
- selected bipartite density: about 10.54%
- every selected game has at least 59 users
- 2,467 / 2,500 selected games have at least 100 users

Baseline caveat:

> The baseline user pool was discovered from very highly ranked games, especially around the top-ranked game ecosystem. It is dense and useful, but biased toward mainstream/high-visibility engaged BGG users.

## 4. Ratings Backfill

Issue discovered:

- BGG collection XML needed `stats=1` to expose user ratings properly.

Fix:

- Collection fetching was updated to use `collection?stats=1`.
- Backfill script:
  - `scripts/backfill_user_ratings.py`

Practical conclusion:

> `collection?stats=1` is sufficient for ownership/status plus rating signals. Separate rated-only fetches are redundant for future pipelines.

## 5. Bias Diagnosis

Script used:

- `scripts/analyze_taxonomy_coverage.py`

Key diagnosis:

> The baseline issue was not just rank bias. It was behavioral mainstream bias.

Underrepresented areas included:

- Mechanics:
  - Measurement Movement
  - Chit-Pull System
  - Ratio / Combat Results Table
  - Minimap Resolution
  - Player Judge
  - Drawing
- Categories:
  - American Civil War
  - American Revolutionary War
  - World War I
  - Napoleonic
  - Trivia
  - Music
  - Memory
  - Electronic
  - Math
  - Pike and Shot

Interpretation:

> The original baseline had strong coverage of engaged BGG users, but weak coverage of some niche communities, especially historical wargame and party/trivia/music-style communities.

## 6. Diversity Expansion

Expansion script:

- `scripts/discover_additional_users_a.py`

Run label:

- `diversity_expansion_batch1`

Main folder:

- `data/processed/reliable_users/diversity_expansion_batch1/`

Method:

- Isolated from baseline.
- Resumable.
- Separate expansion cohort.
- Dual output:
  - strict reliable users
  - looser community users

Seed-game sources:

1. Taxonomy-deficit seeds.
2. Rank-stratified seeds.
3. Wishlist-ratio contrast seeds.

Candidate discovery sources:

- plays
- rating comments

User enrichment:

- one `collection?stats=1` fetch per user

Expansion results:

- successful expansion users: 499
- strict reliable expansion users: 478
- community-pool users: 486
- merged strict user count used in most current analysis: 5,653 users

Stop reason:

- `target_tags_meaningfully_improved`

Measured effect:

- 28 / 30 target underrepresented tags improved by at least 20%.
- Median relative gain across target tags: about 0.325.
- Underrepresented historical/wargame/party/trivia/music areas improved.

Academic framing:

> The final dataset is not a neutral sample of all BGG users. It is a dense, high-quality dataset of engaged BGG users, centered on the top-2500 game universe, with targeted expansion to improve coverage of previously underrepresented communities.

## 7. EDA Phase

Notebook:

- `notebooks/cs514_bgg_eda.ipynb`

EDA covered:

- collection size distributions
- baseline vs expansion user differences
- heavy-collector influence
- per-game coverage across all 2,500 games
- mechanics/category coverage
- cohort-specific tag coverage
- signal overlap between ownership, positive interest, and did-not-retain
- top-100 co-ownership examples
- rating coverage
- game popularity vs metadata

Important EDA findings:

- All 2,500 selected games are represented.
- Ownership projection is extremely dense before filtering.
- Expansion users are heavier/more active collectors than baseline users.
- Ownership and positive interest overlap strongly, but not perfectly.
- Did-not-retain is a distinct behavioral signal.
- Underrepresented tags improved after diversity expansion.

Sampling caveat:

> Expansion users differ from baseline users not only by sourcing, but also by user type. They are heavier and broader collectors on average. Any cohort/bias experiment must account for this confound.

## 8. Behavioral Signals

Current signal layers:

1. Ownership:
   - `own == 1`
   - primary graph signal
2. Positive interest:
   - `own OR wishlist OR want OR wanttoplay OR wanttobuy`
   - secondary/contrast signal
3. Did-not-retain:
   - `prevowned OR fortrade`
   - exploratory contrast signal

Interpretation:

- Ownership means current committed collection signal.
- Positive interest means current plus aspirational interest.
- Did-not-retain means acquired but not retained or marked for trade. It should not be called pure dislike, but it is a weaker or negative-retention signal.

## 9. Network Construction

Base graph:

- user-game bipartite graph

Main projection:

- game-game projection over the same 2,500 game nodes
- edge weight reflects shared user ownership/co-presence

Important interpretation:

> A co-ownership edge does not mean two games are objective substitutes or mechanically similar. It means they share audience/collection context.

Projection method:

- Newman-style user-normalized projection.
- Each user with degree `d` contributes `1 / (d - 1)` to each induced game-game pair.
- This reduces heavy-collector dominance relative to raw co-ownership.

Backbone filter:

- Serrano-Boguna-Vespignani disparity filter.
- Used to reduce the dense projection to locally significant weighted edges.

Tools:

- NetworkX for graph computation.
- Gephi exports for visualization.

Core code:

- `src/bgg_project/cs514/`
- `scripts/cs514_pipeline.py`
- `scripts/cs514_parameter_sweep.py`
- `scripts/cs514_detect_communities.py`
- `scripts/cs514_null_model.py`

## 10. Community Detection And Validation Metrics

Community method:

- Louvain community detection.
- Multiple random seeds per setting.

Stability metric:

- median pairwise NMI across Louvain seeds.
- Current stability gate:
  - NMI >= 0.70 is treated as acceptable.

Metadata interpretation:

- Metadata is not used to form communities.
- Mechanics/categories are used after community detection via:
  - hypergeometric community tag enrichment
  - binary tag modularity

Null model:

- Degree-preserving rewired graph with shuffled weights.
- Same community detection procedure is run on null graphs.
- Used to ask whether observed modularity is higher than expected under a randomized graph with similar degree constraints.

## 11. Parameter Sweep Results

Main sweep output:

- `data/processed/cs514_network_analysis/diagnostics/parameter_sweep.csv`

20-seed confirmation output:

- `data/processed/cs514_network_analysis/diagnostics/parameter_sweep_confirm_20seeds.csv`

Macro setting:

- graph: `merged_ownership_newman_disparity_a0p001`
- alpha: 0.001
- resolution/gamma: 0.75
- result:
  - about 32 communities
  - practically dominated by a few large macro communities plus isolates
  - stable enough
  - statistically strong against null model

Fine setting:

- graph: `merged_ownership_newman_disparity_a0p025`
- alpha: 0.025
- resolution/gamma: 2.0
- result:
  - 57 communities
  - median seed NMI: 0.7668
  - semantically rich communities
  - failed modularity null model

Current open direction:

> Completed targeted midline sweep on alpha=0.025 with gamma in {0.75, 1.0, 1.25, 1.5, 1.75, 2.0}. The highest gamma satisfying both NMI >= 0.70 and z-score > 2 is gamma=1.75.

Midline sweep output:

- `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_midline_gamma_null_sweep.csv`
- `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_midline_gamma_null_replicates.csv`

Midline sweep summary:

| alpha | gamma | communities | largest community | median NMI | observed Q | null mean Q | z-score | interpretation |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.025 | 0.75 | 2 | 56.2% | 0.752 | 0.2843 | 0.2500 | inf | statistically strong but too coarse |
| 0.025 | 1.00 | 4 | 32.9% | 0.594 | 0.1761 | 0.0830 | 170.51 | null passes, stability fails |
| 0.025 | 1.25 | 15 | 25.2% | 0.680 | 0.1235 | 0.0748 | 135.18 | null passes, stability slightly fails |
| 0.025 | 1.50 | 32 | 16.6% | 0.703 | 0.0943 | 0.0708 | 69.22 | validated, moderate granularity |
| 0.025 | 1.75 | 43 | 13.5% | 0.758 | 0.0767 | 0.0679 | 27.31 | validated midline candidate |
| 0.025 | 2.00 | 57 | 12.3% | 0.767 | 0.0645 | 0.0656 | -3.46 | stable/descriptive, null fails |

Decision:

> Use `alpha=0.025, gamma=1.75` as the current validated midline community graph. Keep `alpha=0.001, gamma=0.75` as macro context and `alpha=0.025, gamma=2.0` as exploratory fine detail.

## 12. Null Model Results

Macro graph null model:

- graph: `merged_ownership_newman_disparity_a0p001`
- resolution: 0.75
- observed modularity: 0.3424
- null mean: 0.2677
- null std: 0.0036
- z-score: 20.80

Interpretation:

> The broad macro-level co-ownership structure is statistically stronger than expected under a degree-preserving null model.

Fine graph null model:

- graph: `merged_ownership_newman_disparity_a0p025`
- resolution: 2.0
- observed modularity: 0.0640
- null mean: 0.0654
- null std: 0.00023
- z-score: -6.43

Output files:

- `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_r2p0_null_modularity.csv`
- `data/processed/cs514_network_analysis/diagnostics/merged_ownership_newman_disparity_a0p025_r2p0_null_modularity_summary.json`

Interpretation:

> The fine graph is stable and semantically interpretable, but its modularity is not above the degree-preserving null. It should be used as a descriptive/exploratory segmentation, not as the main statistically validated community-structure claim.

Validated midline null model:

- graph: `merged_ownership_newman_disparity_a0p025`
- resolution: 1.75
- communities: 43
- largest community fraction: 13.5%
- median pairwise seed NMI: 0.758
- observed modularity: 0.0767
- null mean: 0.0679
- z-score: 27.31

Interpretation:

> This is the best current main-result setting. It is more granular than the macro graph, stable across seeds, and statistically above the degree-preserving null.

Important distinction:

- Statistical claim:
  - "This graph has more modular structure than expected by chance."
  - Requires positive null-model result.
- Descriptive finding:
  - "This partition consistently groups games into semantically interpretable clusters."
  - Supported by seed stability, enrichment, and game-level inspection, even if modularity null does not pass.

## 13. Fine Community Interpretation

Notebook:

- `notebooks/cs514_community_interpretation.ipynb`

Summary file:

- `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r2p0_community_interpretation_summary.csv`

Manual-review helper:

- `scripts/cs514_add_manual_community_columns.py`

Manual columns added:

- `manual_label`
- `community_type`
- `include_in_user_profiles`
- `manual_meaningfulness`
- `manual_notes`

Currently identified meaningful communities:

- C7: BGG Golden Age canon
- C0: Historical wargames + economic strategy
- C2: Current heavy euro engine builders
- C8: Dungeon crawl / cooperative campaign adventure
- C9: Medium worker-placement euros
- C15: Amerithrash / miniatures / LCG
- C39: Social deduction and party games
- C5: Cooperative trick-taking + deduction
- C12: Puzzle / nature tableau builders
- C28: Legacy + narrative mystery
- C35: Print-and-play solo microgames
- C36: Family / children's games

Important interpretive findings:

1. Temporal/generational axis:
   - C7 appears to be a BGG Golden Age/historical canon cluster, not merely an abstract/auction cluster.
   - C13 appears to be a recent-release/new-hotness temporal artifact.

2. Coherence gradient:
   - Wargames are highly self-contained.
   - Golden Age canon and heavy euro clusters also show strong internal gravity.
   - Legacy, social deduction, trick-taking, and puzzle/nature clusters are more cross-community.

3. Bridge/shared-culture games:
   - Some popular games or small clusters appear to bridge across many audiences rather than belong to one taste group.

4. Franchise/series clusters:
   - C11 appears to be an Unmatched/skirmish series ownership cluster.
   - This is structurally coherent but not a broad taste identity.

## 14. Current Interpretation

The project should not be framed as "we ran Louvain and found communities."

Better framing:

> User collections reveal an audience-based taxonomy of BGG. Some communities align with metadata-defined genres, but others reveal hobby-era effects, bridge/shared-culture games, and franchise collecting patterns that official metadata alone does not capture.

Current strongest defensible claim:

> The co-ownership network has statistically significant broad structure. At finer resolution, stable and semantically coherent clusters reveal how board-game collecting behavior mixes taste, era, and collecting mode.

## 15. Current Limitations

- Dataset is an engaged-user sample, not a full BGG population sample.
- Baseline and expansion cohorts differ in both sourcing and user type.
- Co-ownership means audience overlap, not necessarily game similarity.
- Fine graph at alpha=0.025, gamma=2.0 is descriptive, not statistically significant by modularity null.
- Some communities are temporal artifacts or franchise clusters, not stable taste communities.
- Small communities require manual review before use in user profiling.

## 16. Next Steps

Immediate next implementation:

1. Interpret and label the validated midline graph:
   - graph: `merged_ownership_newman_disparity_a0p025`
   - gamma: 1.75
   - output label: `merged_ownership_newman_disparity_a0p025_r1p75`
   - compare labels with the finer `r2p0` interpretation.

Status update:

- Midline interpretation summary generated:
  - `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_interpretation_summary.csv`
- Compact manual mapping generated:
  - `data/processed/cs514_network_analysis/metadata/merged_ownership_newman_disparity_a0p025_r1p75_community_manual_mapping.csv`
- Interpretation notebook now defaults to the validated midline run:
  - `notebooks/cs514_community_interpretation.ipynb`
- Current manual mapping state:
  - 10 communities marked `include_in_user_profiles = yes`
  - 13 communities marked `include_in_user_profiles = no`
  - 20 communities left as `review`

Core labeled midline communities:

- C10: BGG Golden Age canon
- C9: Amerithrash / miniatures / LCG
- C12: Dungeon crawl / cooperative campaign adventure
- C19: Recent releases / new-hotness cluster
- C2: Current heavy euro engine builders
- C20: Historical wargames + conflict strategy
- C25: Party / family / social deduction
- C13: Puzzle / nature tableau builders
- C8: Medium worker-placement euros
- C35: Cooperative trick-taking + deduction
- C4: Legacy + narrative mystery
- C16: Unmatched / skirmish series cluster

2. Finish manual labels for remaining `review` communities in the interpretation summary.

Status update:

- Manual mapping revised after labeling review.
- C4 / Legacy + narrative mystery was promoted to `include_in_user_profiles = yes`.
- Previously unlabeled review communities now have labels/types where possible:
  - bridge_singleton examples: Terraforming Mars and Ark Nova micro-clusters
  - franchise/system examples: Unmatched, Pandemic, Ticket to Ride, Railroad Ink, Race for the Galaxy, KeyForge/Catan
  - bridge examples: Root/Eclipse area-control crossover, Splendor/Century gateway, Azul tile-placement, light gateway clusters
- Current mapping counts:
  - yes: 11 communities
  - no: 20 communities
  - review: 12 communities

3. Build user taste profiles from the validated midline mapping.

Status update:

- Ownership-based user profile table generated:
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_user_profiles.csv`
- Profile dimension summary generated:
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_profile_dimensions.csv`
- Game-to-profile-dimension mapping generated:
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_game_profile_mapping.csv`

Profile policy:

> Communities marked `include_in_user_profiles = yes` become separate profile dimensions. All excluded/review/tiny/franchise/temporal-artifact/bridge communities are collapsed into an `other` dimension.

Profile dimensions currently included:

- BGG Golden Age canon
- Amerithrash / miniatures / LCG
- Dungeon crawl / cooperative campaign adventure
- Current heavy euro engine builders
- Historical wargames + conflict strategy
- Party / family / social deduction
- Puzzle / nature tableau builders
- Medium worker-placement euros
- Cooperative trick-taking + deduction
- Roll-and-write / number dice games
- Legacy + narrative mystery
- Other / excluded / review communities

Initial user profile diagnostics:

- users profiled: 5,504 active merged-ownership users
- average selected owned games per profiled user: 116.26
- mean included-share: 0.714
- mean profile entropy: 0.713
- mean dominant-dimension share: 0.368
- dominant dimension is often `other`, which is expected because it intentionally absorbs franchise clusters, recent-release artifacts, bridge micro-clusters, and remaining review/tiny communities.

4. Create a cleaned community mapping for user profiles:
   - include meaningful taste communities
   - include or flag temporal canon
   - exclude recent-release artifact
   - exclude franchise/series clusters where appropriate
   - collapse tiny/noisy fragments into `other`

5. Build user taste profile table:
   - rows: users
   - columns: cleaned community labels/types
   - values: share/count of owned selected games in each community

6. Analyze user archetypes:
   - specialist users
   - generalists
   - wargame specialists
   - euro specialists
   - campaign/adventure users
   - party/social users
   - Golden Age canon collectors

Status update:

- User archetype script added:
  - `scripts/cs514_analyze_user_archetypes.py`
- The script uses the validated midline profile table and filters users with fewer than 15 selected owned games before assigning interpretable archetypes.
- Generated outputs:
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_user_archetypes.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_summary.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_family_summary.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_dimension_summary.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_archetype_top_games.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_other_dominant_decomposition.csv`
  - `data/processed/cs514_network_analysis/user_profiles/merged_ownership_newman_disparity_a0p025_r1p75_merged_ownership_other_dominant_users.csv`

Initial archetype results:

- 5,125 / 5,504 active ownership users pass the minimum selected-owned filter.
- Broad archetype families among eligible users:
  - other-dominant: 3,221 users
  - generalist: 723 users
  - leaning toward a taste dimension: 634 users
  - specialist: 524 users
  - mixed: 23 users
- The large other-dominant class is expected because the `other` bucket intentionally absorbs universal-appeal games, bridge clusters, recent-release artifacts, franchise/series clusters, and unresolved tiny communities.
- Among other-dominant users' `other` ownership edges, the largest sources are recent-release/temporal artifact games, bridge clusters, and franchise/series clusters. This supports treating `other` as a heterogeneous diagnostic bucket rather than a taste archetype.

Next implementation step:

- Build a short visualization/inspection notebook for archetypes:
  - family counts
  - dimension dominance
  - specialist vs generalist examples
  - top games per archetype
  - decomposition of the `other` bucket
  - candidate figures for the final poster.

Status update:

- User archetype inspection notebook created:
  - `notebooks/cs514_user_archetype_analysis.ipynb`
- Notebook sections:
  - load and validate archetype/profile outputs
  - archetype family count chart
  - taste-dimension reach and dominance
  - specialist / leaning / mixed users by dimension
  - profile entropy vs dominant-share scatter
  - included-share distribution
  - `other` bucket decomposition
  - top games by archetype
  - representative archetype comparison tables
  - export-ready poster tables
- Smoke test passed by executing all notebook code cells with a non-interactive plotting backend.
- Figures are saved to:
  - `data/processed/cs514_network_analysis/figures/`

4. Translate results into a poster/report plan based on the professor's poster guidelines.

Status update:

- Poster design guideline PDF inspected:
  - `docs/Poster_Design_Guidelines.pdf`
- Main requirements extracted:
  - 3 or 4 column grid
  - one visually dominant hero finding
  - generous white space and consistent gutters
  - limited color palette
  - high contrast text
  - figure captions and axis labels
  - conclusion column with summary/references/QR code
- Results and poster plan created:
  - `docs/cs514_results_and_poster_plan.md`
- This memo locks:
  - final working title options
  - research question
  - one-sentence answer
  - hero finding
  - validation table
  - main game-community claims
  - user-archetype claims
  - limitations
  - poster layout
  - recommended figures
  - final text blocks

5. Prepare professor meeting brief.

Status update:

- One-to-one progress discussion guide created:
  - `docs/cs514_professor_meeting_brief.md`
- This document summarizes:
  - the one-minute project pitch
  - data collection and diversity expansion story
  - network construction and validation story
  - main findings to emphasize
  - what not to overclaim
  - feedback questions to ask the professor
  - recommended 15-minute and 30-minute meeting flows
  - possible next steps depending on professor feedback

6. Create data-collection walkthrough notebook.

Status update:

- Descriptive data-collection notebook created:
  - `notebooks/cs514_data_collection_walkthrough.ipynb`
- Purpose:
  - explain BGG API/XML endpoints used
  - show real raw XML examples from saved repo artifacts
  - clarify candidate-user discovery from rating comments and play logs
  - clarify that reliable-user filtering happens after full collection fetches
  - document the `collection?stats=1` rating revelation
  - summarize baseline reliable-user construction
  - summarize taxonomy bias diagnosis
  - summarize diversity expansion seed selection, filters, and improvement results
- Smoke test:
  - all notebook code cells executed successfully.

7. Create parameter-refinement walkthrough notebook.

Status update:

- Parameter-refinement notebook created:
  - `notebooks/cs514_parameter_refinement_walkthrough.ipynb`
- Purpose:
  - explain alpha as disparity-backbone strictness
  - explain gamma as Louvain resolution
  - show the initial alpha/gamma sweep table
  - show NMI and community-count heatmaps
  - show 20-seed confirmation results
  - show targeted `alpha = 0.025` gamma/null-model sweep
  - document why `alpha = 0.025`, `gamma = 1.75` became the main validated setting
- Generated figures:
  - `data/processed/cs514_network_analysis/figures/parameter_refinement/initial_alpha_gamma_sweep_heatmaps.png`
  - `data/processed/cs514_network_analysis/figures/parameter_refinement/midline_gamma_sweep_validation.png`
  - `data/processed/cs514_network_analysis/figures/parameter_refinement/observed_vs_null_community_counts.png`
- Smoke test:
  - all notebook code cells executed successfully.

## 17. Candidate Poster Figures

Possible figures:

1. Data pipeline diagram:
   - BGG games -> baseline users -> taxonomy diagnosis -> diversity expansion -> final graph.

2. Bipartite-to-game projection diagram:
   - user-game graph -> Newman projection -> disparity backbone -> communities.

3. Parameter sweep table:
   - alpha/gamma vs communities, NMI, z-score.

4. Macro graph visualization:
   - statistically significant broad structure.

5. Fine/midline community interpretation table:
   - community labels, size, enriched tags, representative games.

6. Coherence gradient:
   - internal weight share by community.

7. Temporal axis:
   - median publication year by community.

8. User archetype chart:
   - once user profiles are built.

## 18. Candidate Report Structure

1. Introduction and research question.
2. Data collection and expansion strategy.
3. EDA and sampling caveats.
4. Network construction.
5. Backbone filtering and community detection.
6. Validation:
   - stability
   - metadata enrichment
   - null models
7. Results:
   - macro structure
   - midline/fine communities
   - temporal/generational axis
   - coherence gradient
   - bridge/franchise findings
8. Limitations.
9. Conclusion.

## 19. Missing Network-Science Analyses Notebook

Status update:

- Notebook created:
  - `notebooks/cs514_missing_network_analyses.ipynb`
- Validated graph used:
  - `alpha = 0.025`
  - `gamma = 1.75`
  - 2,500 nodes
  - 214,379 backbone edges
  - 43 communities
- Purpose:
  - formalize bridge-game claims using centrality rather than only manual labels
  - characterize the topology of the validated backbone
  - build a community-level condensation graph
  - estimate metadata alignment at the edge level using multi-label Jaccard lift
  - identify core vs. periphery games inside each community
- Outputs:
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/network_topology_summary.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/centrality_scores.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/top_betweenness_games.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/top_degree_games.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/top_strength_games.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/community_condensation_nodes.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/community_condensation_edges.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/metadata_edge_similarity_summary.csv`
  - `data/processed/cs514_network_analysis/diagnostics/missing_network_analyses/community_core_periphery_scores.csv`
- Figures:
  - `data/processed/cs514_network_analysis/figures/missing_network_analyses/degree_distribution.png`
  - `data/processed/cs514_network_analysis/figures/missing_network_analyses/centrality_top_betweenness.png`
  - `data/processed/cs514_network_analysis/figures/missing_network_analyses/rank_vs_betweenness.png`
  - `data/processed/cs514_network_analysis/figures/missing_network_analyses/community_condensation_graph.png`
  - `data/processed/cs514_network_analysis/figures/missing_network_analyses/internal_weight_share_by_community.png`
- Smoke test:
  - all notebook code cells executed successfully with the project virtual environment.
  - Jupyter `nbconvert` attempted to use a global Python kernel without `numpy`, so the code was validated directly through `.venv`.
- Initial diagnostics:
  - the validated backbone is connected with no isolates.
  - average degree is 171.5 and median degree is 94.
  - average unweighted clustering is 0.783, much higher than the same-density random expectation of 0.069.
  - observed co-ownership edges have higher metadata similarity than random game pairs:
    - mechanic Jaccard lift: 1.40x
    - category Jaccard lift: 1.67x
  - top approximate betweenness examples include broad bridge/crossover games such as `7 Wonders Duel`, `Azul`, `Carcassonne`, `Terraforming Mars`, `Codenames`, `Wingspan`, `Pandemic`, `Brass: Birmingham`, and `Ark Nova`.

## 20. Poster-Ready Network Findings Notebook

Status update:

- Notebook created:
  - `notebooks/cs514_poster_ready_network_findings.ipynb`
- Purpose:
  - convert structural diagnostics into compact report/poster tables
  - create a formal bridge-score table
  - summarize strongest community-community adjacencies
  - summarize core and boundary games for major communities
  - collect a one-page evidence table for the final report/poster
- Outputs:
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/bridge_score_table.csv`
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/top_community_adjacencies.csv`
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/community_exposure_table.csv`
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/community_core_boundary_summary.csv`
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/community_core_boundary_long.csv`
  - `data/processed/cs514_network_analysis/diagnostics/poster_ready_network_findings/poster_evidence_table.csv`
- Figures:
  - `data/processed/cs514_network_analysis/figures/poster_ready_network_findings/top_bridge_score_games.png`
  - `data/processed/cs514_network_analysis/figures/poster_ready_network_findings/top_community_adjacencies.png`
- Bridge-score definition:
  - `0.45 * betweenness_percentile + 0.35 * external_strength_percentile + 0.20 * external_strength_share_percentile`
- Initial bridge-score examples:
  - `7 Wonders Duel`
  - `Terraforming Mars`
  - `Azul`
  - `Carcassonne`
  - `Codenames`
  - `Catan`
  - `Wingspan`
  - `Ark Nova`
  - `Pandemic`
  - `Brass: Birmingham`
- Strongest community-community adjacency:
  - `Medium worker-placement euros` <-> `BGG Golden Age canon`
- Smoke test:
  - all notebook code cells executed successfully with the project virtual environment.

## 21. NMF Test A: Within-Scope Taste-Dimension Validation

Status update:

- Script created:
  - `scripts/cs514_nmf_test_a.py`
- Summary notebook created:
  - `notebooks/cs514_nmf_test_a.ipynb`
- Purpose:
  - test whether the 11 manually selected user-profile dimensions are recoverable directly from the user-game ownership matrix
  - avoid graph projection, disparity filtering, Louvain, and metadata input for this validation step
  - restrict the matrix to games whose communities have `include_in_user_profiles = yes`
- Input:
  - `data/processed/cs514_network_analysis/incidence/merged_ownership.npz`
  - shape: 5,504 users x 2,500 games
  - restricted shape: 5,482 active users x 1,912 included-dimension games
- Method:
  - Non-negative Matrix Factorization with `k = 11`
  - `init = nndsvda`
  - `solver = cd`
  - `beta_loss = frobenius`
  - compare NMF components to manual dimensions using cosine similarity
  - use Hungarian matching for the best one-to-one alignment
- Outputs:
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_a/nmf_test_a_diagnostics.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_a/nmf_test_a_best_matches.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_a/nmf_test_a_similarity_matrix.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_a/nmf_test_a_component_mass_share.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_a/nmf_test_a_top_games_by_component.csv`
  - `data/processed/cs514_network_analysis/figures/matrix_decomposition/nmf_test_a_similarity_heatmap.png`
- Initial result:
  - 8 / 11 manual dimensions matched an NMF component at cosine similarity >= 0.50
  - 9 / 11 matched at cosine similarity >= 0.40
  - mean matched cosine: 0.559
  - median matched cosine: 0.674
- Strongly recovered dimensions:
  - `BGG Golden Age canon`
  - `Current heavy euro engine builders`
  - `Historical wargames + conflict strategy`
  - `Amerithrash / miniatures / LCG`
  - `Medium worker-placement euros`
  - `Dungeon crawl / cooperative campaign adventure`
  - `Puzzle / nature tableau builders`
  - `Party / family / social deduction`
- Weak standalone recovery:
  - `Legacy + narrative mystery`
  - `Roll-and-write / number dice games`
- Preliminary interpretation:
  - the large/stable profile dimensions are substantially recoverable directly from the raw ownership matrix
  - smaller or more supplementary dimensions may not behave as independent matrix factors, supporting the earlier interpretation that they function as cross-community additions rather than core identities

## 22. NMF Test B: Full-Matrix k-Sweep

Status update:

- Script created:
  - `scripts/cs514_nmf_test_b.py`
- Summary notebook created:
  - `notebooks/cs514_nmf_test_b.ipynb`
- Purpose:
  - apply NMF to the full merged ownership matrix, including all 2,500 games
  - test whether the matrix naturally prefers the 11 profile dimensions or also recovers bridge, franchise, temporal, and missing niche structures
- Input:
  - `data/processed/cs514_network_analysis/incidence/merged_ownership.npz`
  - shape: 5,504 users x 2,500 games
- Method:
  - NMF k-sweep for `k = {5, 8, 11, 15, 20, 25}`
  - three seeds per k: `514`, `515`, `516`
  - component stability computed by Hungarian matching between seeds using cosine similarity
  - components summarized by top games, dominant Louvain community, dominant manual community type, and similarity to the 11 included profile dimensions
- Outputs:
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_k_summary.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_seed_stability.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_top_games_by_component.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_component_type_mass_share.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_component_community_mass_share.csv`
  - `data/processed/cs514_network_analysis/matrix_decomposition/nmf_test_b/nmf_test_b_component_included_dimension_similarity.csv`
  - `data/processed/cs514_network_analysis/figures/matrix_decomposition/nmf_test_b_reconstruction_error.png`
  - `data/processed/cs514_network_analysis/figures/matrix_decomposition/nmf_test_b_seed_stability.png`
- Initial result:
  - reconstruction error decreases gradually as k increases; there is no sharp elbow at exactly k = 11
  - k = 5, 8, 11, and 15 are perfectly stable across tested seeds
  - k = 20 and k = 25 still reduce reconstruction error, but introduce unstable small components
  - k = 15 is the most useful descriptive setting: richer than k = 11 while remaining fully stable
- k = 15 component interpretation:
  - major Louvain/profile structures are recovered:
    - BGG Golden Age canon
    - current heavy euros
    - historical wargames
    - dungeon crawl/cooperative campaign
    - Amerithrash/LCG
    - medium worker-placement euros
    - puzzle/nature/tableau
    - party/social deduction
  - the full matrix also recovers structures outside the 11 profile dimensions:
    - recent releases / new-hotness
    - gateway and universal bridge games
    - Unmatched/franchise ownership
    - Knizia / auction / classic abstract games
    - heavy economic / Splotter / 18xx-style games
- Interpretation:
  - Test B supports the core Louvain taxonomy but shows that the 11 profile dimensions are not exhaustive
  - the hand-labeled 11 dimensions are best understood as a practical user-profile layer, not as the complete latent structure of BGG ownership
  - the extra NMF components strengthen the claim that behavioral ownership contains structures not captured by metadata alone or by the selected taste-profile dimensions
