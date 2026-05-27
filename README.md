# BoardGameGeek Co-Ownership Networks

This repository contains the code, processed outputs, notebooks, and report artifacts for a CS514 Network Science project on BoardGameGeek (BGG) ownership behavior.

Repository URL: <https://github.com/aihsangul/cs514-bgg_project>

The project studies a user-game ownership matrix of 5,504 active collectors and 2,500 ranked games. It combines a graph-based co-ownership pipeline with matrix decomposition in order to identify taste communities, shared-canon behavior, bridge games, and user archetypes.

## Main Finding

BGG ownership is organized in two layers. The first layer contains recognizable taste communities such as historical wargames, heavy euros, dungeon-crawl campaigns, Amerithrash and LCG games, social deduction, and medium worker-placement euros. The second layer is a shared canon made of recent-release cycles, universal-appeal bridge games, and franchise systems that cut across those taste communities.

## Repository Structure

```text
.
├── src/                         Core Python package used by scripts
├── scripts/                     Runnable data, network, NMF, profile, and figure scripts
├── notebooks/                   Narrative analysis notebooks
├── data/processed/              Selected processed outputs needed to inspect results
├── figures/                     Final report/poster figures
├── docs/                        Analysis log, meeting brief, and planning notes
├── report/                      Final LaTeX report source
├── requirements.txt             Python dependencies
└── .env.example                 Example environment file for API configuration
```

## Pipeline Overview

1. Data collection identifies candidate BGG users from game-level interactions and fetches their collections through the BGG API.
2. Reliable users are retained when collection fetches succeed, they have at least 50 collection items, and they overlap with at least 10 games in the selected 2,500-game universe.
3. A Newman user-normalized projection converts the user-game ownership matrix into a weighted game-game co-ownership network.
4. A Serrano-Boguna-Vespignani disparity filter extracts the statistically meaningful backbone.
5. Louvain community detection is run across alpha and gamma parameter settings, with stability checked by NMI and significance checked against degree-preserving null graphs.
6. The selected midline graph uses alpha = 0.025 and gamma = 1.75, producing 43 communities.
7. Communities are manually interpreted into nine structural types and 11 named taste dimensions.
8. NMF is applied directly to the ownership matrix as a matrix-side validation of the graph-side taxonomy.
9. User profiles are built from 11 named taste dimensions plus an "other" residual layer.
10. Final structural and user-level findings are summarized in CSV outputs, notebooks, and figures.

## Running Scripts

Most scripts assume they are run from the repository root. If imports fail, set `PYTHONPATH=src` before running scripts.

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python scripts/cs514_nmf_test_a.py
```

On macOS/Linux:

```bash
export PYTHONPATH=src
python scripts/cs514_nmf_test_a.py
```

## Key Results

- Final dataset: 5,504 active collectors by 2,500 games.
- Main graph: Newman projection plus disparity backbone at alpha = 0.025.
- Main community setting: Louvain gamma = 1.75.
- Main partition: 43 communities.
- Stability: median pairwise NMI = 0.758.
- Null-model significance: modularity z-score = 27.31.
- NMF validation: 8 of 11 taste dimensions recovered with cosine similarity at least 0.50.
- User finding: 62.9 percent of eligible users are dominated by the residual shared-canon layer rather than one named taste identity.

## Most Important Files

- `scripts/cs514_pipeline.py` gives the broad end-to-end CS514 pipeline.
- `scripts/cs514_parameter_sweep.py` runs the alpha and gamma community-detection sweep.
- `scripts/cs514_midline_gamma_null_sweep.py` runs the targeted null-model validation.
- `scripts/cs514_nmf_test_a.py` and `scripts/cs514_nmf_test_b.py` run the matrix-decomposition validation.
- `scripts/cs514_build_user_profiles.py` and `scripts/cs514_analyze_user_archetypes.py` create the user-profile and archetype results.
- `notebooks/cs514_parameter_refinement_walkthrough.ipynb` explains the parameter-selection process.
- `notebooks/cs514_nmf_test_a.ipynb` and `notebooks/cs514_nmf_test_b.ipynb` explain the matrix-decomposition results.
- `notebooks/cs514_user_archetype_analysis.ipynb` explains the user-level finding.
- `report/CS514_Report_FINAL_OVERLEAF.tex` contains the final report.

## Data Availability Note

The repository includes selected processed outputs used in the report and poster. It does not include every intermediate raw API response or cache file from the full working directory. Re-running the complete collection pipeline requires BGG API access and may produce a later snapshot of the BGG ecosystem.
