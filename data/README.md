# Processed Data Included

This folder contains selected processed outputs used for the final report and poster. It is intentionally not a full raw-data dump.

## Included

- `processed/cs514_network_analysis/incidence/merged_ownership.*` contains the main user-game ownership matrix and row/column metadata.
- `processed/cs514_network_analysis/backbones/merged_ownership_newman_disparity_a0p025_edges.csv` contains the final alpha = 0.025 backbone.
- `processed/cs514_network_analysis/communities/` contains the gamma = 1.75 final community assignment and run diagnostics.
- `processed/cs514_network_analysis/diagnostics/` contains parameter-sweep and null-model outputs.
- `processed/cs514_network_analysis/metadata/` contains community labels, interpretation summaries, and enrichment outputs for the final setting.
- `processed/cs514_network_analysis/matrix_decomposition/` contains NMF Test A and Test B outputs.
- `processed/cs514_network_analysis/structural_analysis/` contains centrality, topology, metadata-alignment, condensation-graph, and core-periphery summaries.
- `processed/cs514_network_analysis/user_profiles/` contains user-profile, archetype, and residual-decomposition outputs.
- `processed/cs514_network_analysis/gephi/` contains Gephi-ready GEXF exports for the final graph and community condensation graph.

## Not Included

Raw BGG API responses, temporary caches, pycache files, notebook checkpoints, and full intermediate graphs from exploratory runs are omitted to keep the repository readable and reasonably sized.

