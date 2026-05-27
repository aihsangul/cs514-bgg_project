# Suggested Run Order

The processed outputs used by the report are already included, so a reviewer can inspect the final results without rerunning the full workflow. A clean re-run from scratch should follow this order, but the data-collection stages require live BGG access and regenerate omitted raw/intermediate snapshots.

## 1. Environment

```bash
pip install -r requirements.txt
```

If BGG API access or tokens are needed, copy `.env.example` to `.env` and fill in the required values.

Most scripts should be run from the repository root. Set `PYTHONPATH=src` if the `bgg_project` package is not found.

## 2. Data Collection

These steps query BGG, may take time, and produce a time-specific snapshot. They are included for transparency, but this curated submission does not include all raw API responses from the original working directory.

```bash
python scripts/collect_taxonomy.py
python scripts/collect_top_ranked_games_details.py
python scripts/discover_candidate_users.py
python scripts/collect_reliable_users.py
python scripts/discover_additional_users_a.py
python scripts/discover_additional_users_b.py
```

## 3. Network Pipeline

The included `data/processed/cs514_network_analysis/` directory already contains the final incidence matrix, backbone, communities, diagnostics, NMF outputs, structural analysis outputs, and user-profile outputs used in the report. To rebuild these outputs from scratch, the upstream reliable-user collection directories and ranked-game details must exist under `data/processed/`.

```bash
python scripts/cs514_build_incidence.py
python scripts/cs514_build_backbones.py --alphas 0.025
python scripts/cs514_parameter_sweep.py
python scripts/cs514_detect_communities.py
python scripts/cs514_midline_gamma_null_sweep.py
```

The selected setting is alpha = 0.025 and gamma = 1.75.

## 4. Community Interpretation

```bash
python scripts/cs514_build_community_interpretation_summary.py
python scripts/cs514_add_manual_community_columns.py
python scripts/export_cs514_community_gexf.py
```

## 5. Matrix Decomposition

```bash
python scripts/cs514_nmf_test_a.py
python scripts/cs514_nmf_test_b.py
```

## 6. User Profiles

```bash
python scripts/cs514_build_user_profiles.py
python scripts/cs514_analyze_user_archetypes.py
```

## 7. Figures

```bash
python scripts/generate_pipeline_diagram.py
python scripts/create_cs514_methods_tuning_figures.py
python scripts/generate_results_role_map.py
python scripts/generate_results_catalog_share.py
python scripts/generate_main_finding_hero.py
```

Several figure scripts write first to `data/processed/cs514_network_analysis/figures/poster/` or `docs/cs514_poster_figures_orange/`. The final report copies are stored in the top-level `figures/` directory.

## Notes

Some data-collection scripts depend on API availability and BGG rate limits. The included processed outputs are the authoritative snapshot used for the report.
