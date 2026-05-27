# Script Catalog

The scripts are kept flat in this folder so that their project-root path assumptions remain valid. They are categorized below by analytical stage.

## 1. Data Collection and Reliability Filtering

- `discover_candidate_users.py` discovers candidate usernames from game-level interaction sources.
- `collect_rank_range_users.py` collects users from ranked-game ranges.
- `collect_reliable_users.py` fetches user collections and applies reliability filtering.
- `collect_single_user_collection.py` fetches one user's collection for debugging and validation.
- `collect_taxonomy.py` collects BGG taxonomy metadata.
- `collect_top_ranked_games_details.py` collects details for top-ranked games.
- `collect_top_taxonomy_games.py` supports taxonomy-targeted seed selection.
- `discover_additional_users_a.py` and `discover_additional_users_b.py` implement the diversity-expansion sweep.
- `analyze_reliable_users_dataset.py` summarizes the reliable-user dataset.
- `analyze_taxonomy_coverage.py` checks underrepresented mechanics and categories.

## 2. Network Construction and Parameter Selection

- `cs514_build_incidence.py` builds user-game incidence matrices.
- `cs514_build_backbones.py` applies projection and backbone filtering.
- `cs514_detect_communities.py` runs community detection.
- `cs514_parameter_sweep.py` performs the alpha and gamma sweep.
- `cs514_midline_gamma_null_sweep.py` runs null-model validation for the midline graph.
- `cs514_null_model.py` computes degree-preserving null-model modularity.
- `cs514_pipeline.py` provides the broad end-to-end workflow.
- `cs514_make_cohort_subsamples.py` creates matched and random subsamples for cohort sensitivity checks.

## 3. Community Interpretation and Gephi Export

- `cs514_build_community_interpretation_summary.py` creates community summaries for manual labeling.
- `cs514_add_manual_community_columns.py` adds interpreted labels, community types, and user-profile inclusion flags.
- `export_cs514_community_gexf.py` exports Gephi-ready graph files.

## 4. Matrix Decomposition

- `cs514_nmf_test_a.py` tests whether the 11 hand-labeled taste dimensions are recovered by NMF inside the taste-community scope.
- `cs514_nmf_test_b.py` runs a full-matrix NMF k-sweep to estimate broader latent dimensionality.

## 5. User Profiles and Archetypes

- `cs514_build_user_profiles.py` builds 12-dimensional user profiles from 11 taste dimensions plus the residual layer.
- `cs514_analyze_user_archetypes.py` classifies users and decomposes the other-dominant group.

## 6. Figures and Presentation Outputs

- `generate_pipeline_diagram.py` creates the pipeline diagram.
- `create_cs514_methods_tuning_figures.py` creates network and NMF tuning figures.
- `generate_results_role_map.py` creates the community role map.
- `generate_results_catalog_share.py` creates the catalog-share chart.
- `generate_main_finding_hero.py` creates the main user-level finding figure.
- `create_cs514_user_result_figures.py` creates supporting user-profile figures.
- `generate_results_network.py` creates network-style results graphics.
- `generate_results_fig4_archetypes.py`, `generate_results_fig5_bridge_table.py`, and `generate_results_profile_cards.py` create poster/report support visuals.

