# Artifact Manifest

This manifest explains what was intentionally included in the repository export and why each part matters.

## Code

| Location | Purpose |
| --- | --- |
| `config/` | Example-safe settings and logging configuration needed by collection scripts. |
| `src/bgg_project/` | Reusable Python package for BGG collection, CS514 graph construction, projection, metadata handling, null models, and IO helpers. |
| `scripts/` | Runnable stage scripts for data collection, incidence building, backbone extraction, community detection, NMF validation, user profiling, structural analysis, and figure generation. |

## Notebooks

| Notebook | Purpose |
| --- | --- |
| `notebooks/cs514_data_collection_walkthrough.ipynb` | Describes API responses and user-collection collection logic. |
| `notebooks/cs514_parameter_refinement_walkthrough.ipynb` | Documents alpha and gamma tuning. |
| `notebooks/cs514_community_interpretation.ipynb` | Interprets the 43 communities and manual labels. |
| `notebooks/cs514_structural_network_analyses.ipynb` | Covers centrality, topology, metadata alignment, and condensation graph analyses. |
| `notebooks/cs514_user_archetype_analysis.ipynb` | Explains user profiles, archetypes, and the other-dominant decomposition. |
| `notebooks/cs514_nmf_test_a.ipynb` | Interprets the within-scope NMF recovery test. |
| `notebooks/cs514_nmf_test_b.ipynb` | Interprets the full-matrix NMF k-sweep. |

## Processed Data

| Location | Purpose |
| --- | --- |
| `data/processed/cs514_network_analysis/incidence/` | Main merged ownership matrix and user/game metadata needed by analysis scripts. |
| `data/processed/cs514_network_analysis/backbones/` | Final alpha = 0.025 disparity backbone. |
| `data/processed/cs514_network_analysis/communities/` | Final gamma = 1.75 community assignment and run summary. |
| `data/processed/cs514_network_analysis/diagnostics/` | Parameter sweep, 20-seed confirmation, null-model sweep, and incidence/backbone diagnostics. |
| `data/processed/cs514_network_analysis/metadata/` | Final community labels, manual mapping, interpretation summaries, and tag enrichment outputs. |
| `data/processed/cs514_network_analysis/matrix_decomposition/` | NMF Test A and Test B diagnostics, matches, stability outputs, and component top games. |
| `data/processed/cs514_network_analysis/structural_analysis/` | Centrality, topology, condensation graph, core-periphery, and metadata-alignment outputs. |
| `data/processed/cs514_network_analysis/user_profiles/` | User profiles, archetype labels, dimension summaries, and other-dominant decomposition outputs. |
| `data/processed/cs514_network_analysis/gephi/` | Gephi-ready GEXF exports for the final game graph and community-level condensation graph. |

## Figures and Report

| Location | Purpose |
| --- | --- |
| `figures/` | Final report and poster figures. |
| `report/CS514_Report_FINAL_OVERLEAF.tex` | Final two-column LaTeX report source. |
| `docs/cs514_analysis_log.md` | Chronological record of decisions, methods, and findings. |
| `docs/cs514_meeting_brief.md` | Professor-facing progress brief and finding synthesis. |

## Deliberately Excluded

- Raw API caches and temporary responses.
- Full upstream collection-run directories from the larger working project.
- Python bytecode and notebook checkpoints.
- Old poster draft scripts and PowerPoint draft iterations.
- Virtual environments and local IDE settings.
- Exploratory outputs not used in the final report or poster.
