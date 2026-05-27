"""Run NMF Test A for CS514 BGG matrix-decomposition validation.

Test A asks whether the 11 manually selected user-profile dimensions are
recoverable directly from the user-game ownership matrix when the matrix is
restricted to games inside those dimensions.

Outputs:
- NMF component top games
- NMF component vs manual dimension cosine similarity matrix
- Hungarian best-match table
- heatmap figure
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linear_sum_assignment
from sklearn.decomposition import NMF
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class Paths:
    root: Path
    matrix: Path
    games: Path
    users: Path
    communities: Path
    manual_mapping: Path
    output_dir: Path
    figure_dir: Path


def get_paths() -> Paths:
    root = Path(__file__).resolve().parents[1]
    analysis = root / "data" / "processed" / "cs514_network_analysis"
    return Paths(
        root=root,
        matrix=analysis / "incidence" / "merged_ownership.npz",
        games=analysis / "incidence" / "merged_ownership_games.csv",
        users=analysis / "incidence" / "merged_ownership_users.csv",
        communities=analysis
        / "communities"
        / "merged_ownership_newman_disparity_a0p025_r1p75_communities.csv",
        manual_mapping=analysis
        / "metadata"
        / "merged_ownership_newman_disparity_a0p025_r1p75_community_manual_mapping.csv",
        output_dir=analysis / "matrix_decomposition" / "nmf_test_a",
        figure_dir=analysis / "figures" / "matrix_decomposition",
    )


def normalize_yes_no(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def main() -> None:
    paths = get_paths()
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.figure_dir.mkdir(parents=True, exist_ok=True)

    matrix = sp.load_npz(paths.matrix).tocsr().astype(np.float64)
    games = pd.read_csv(paths.games)
    users = pd.read_csv(paths.users)
    communities = pd.read_csv(paths.communities)
    manual = pd.read_csv(paths.manual_mapping)

    if matrix.shape != (len(users), len(games)):
        raise ValueError(
            f"Matrix shape {matrix.shape} does not match users/games "
            f"({len(users)}, {len(games)})"
        )

    manual["include_norm"] = normalize_yes_no(manual["include_in_user_profiles"])
    included_manual = manual[manual["include_norm"] == "yes"].copy()
    included_manual = included_manual.sort_values(["community"]).reset_index(drop=True)
    included_communities = included_manual["community"].astype(int).tolist()

    game_meta = games.merge(
        communities[["bgg_id", "community"]],
        on="bgg_id",
        how="left",
        validate="one_to_one",
    ).merge(
        manual[
            [
                "community",
                "manual_label",
                "community_type",
                "include_in_user_profiles",
                "manual_meaningfulness",
            ]
        ],
        on="community",
        how="left",
    )

    included_games = game_meta[game_meta["community"].isin(included_communities)].copy()
    included_games = included_games.sort_values("col").reset_index(drop=True)
    included_cols = included_games["col"].to_numpy(dtype=int)
    restricted = matrix[:, included_cols].tocsr()

    row_counts = np.asarray(restricted.sum(axis=1)).ravel()
    active_user_mask = row_counts > 0
    restricted_active = restricted[active_user_mask]

    # Keep raw binary ownership as the primary test. This asks what the original
    # ownership matrix itself recovers, with no graph projection or metadata input.
    n_components = len(included_communities)
    nmf = NMF(
        n_components=n_components,
        init="nndsvda",
        solver="cd",
        beta_loss="frobenius",
        tol=1e-4,
        max_iter=800,
        random_state=514,
    )
    W = nmf.fit_transform(restricted_active)
    H = nmf.components_

    # Manual dimension matrix D: rows are selected manual communities, columns are
    # the restricted included-game universe.
    dimension_names = included_manual["manual_label"].fillna(
        "C" + included_manual["community"].astype(str)
    ).tolist()
    dimension_ids = included_manual["community"].astype(int).tolist()
    D = np.zeros((n_components, restricted.shape[1]), dtype=float)
    col_to_restricted_pos = {
        int(col): pos for pos, col in enumerate(included_games["col"].to_numpy(dtype=int))
    }
    for dim_idx, community in enumerate(dimension_ids):
        cols = included_games.loc[included_games["community"] == community, "col"].astype(int)
        positions = [col_to_restricted_pos[int(col)] for col in cols]
        D[dim_idx, positions] = 1.0

    # Similarity matrix: rows manual dimensions, columns NMF components.
    similarity = cosine_similarity(D, H)
    manual_rows, nmf_cols = linear_sum_assignment(-similarity)

    match_rows: list[dict[str, object]] = []
    for manual_idx, component_idx in zip(manual_rows, nmf_cols):
        match_rows.append(
            {
                "manual_community": dimension_ids[manual_idx],
                "manual_dimension": dimension_names[manual_idx],
                "nmf_component": int(component_idx),
                "cosine_similarity": float(similarity[manual_idx, component_idx]),
                "manual_dimension_size": int(D[manual_idx].sum()),
                "component_top_game": None,
            }
        )

    top_game_rows: list[dict[str, object]] = []
    for component_idx in range(n_components):
        weights = H[component_idx]
        top_positions = np.argsort(weights)[::-1][:30]
        for rank, pos in enumerate(top_positions, start=1):
            game = included_games.iloc[int(pos)]
            top_game_rows.append(
                {
                    "nmf_component": component_idx,
                    "component_game_rank": rank,
                    "component_weight": float(weights[pos]),
                    "bgg_id": int(game["bgg_id"]),
                    "name": game["name"],
                    "overall_rank": int(game["overall_rank"]),
                    "manual_community": int(game["community"]),
                    "manual_dimension": game["manual_label"],
                    "community_type": game["community_type"],
                }
            )

    top_games = pd.DataFrame(top_game_rows)
    match_table = pd.DataFrame(match_rows)
    top1 = top_games[top_games["component_game_rank"] == 1][
        ["nmf_component", "name"]
    ].rename(columns={"name": "component_top_game"})
    match_table = match_table.drop(columns=["component_top_game"]).merge(
        top1, on="nmf_component", how="left"
    )
    match_table = match_table.sort_values("manual_community").reset_index(drop=True)
    match_table["matching_method"] = "hungarian_max_cosine"

    similarity_df = pd.DataFrame(
        similarity,
        index=[f"C{cid}: {name}" for cid, name in zip(dimension_ids, dimension_names)],
        columns=[f"NMF {i}" for i in range(n_components)],
    )

    # Hungarian-ordered similarity matrix: manual rows are kept in the manual
    # dimension order, columns are reordered so the best one-to-one assignment
    # appears on the diagonal. This is the clearest output for interpretation.
    ordered_component_indices = [
        int(match_table.loc[match_table["manual_community"] == cid, "nmf_component"].iloc[0])
        for cid in dimension_ids
    ]
    ordered_similarity = similarity[:, ordered_component_indices]
    ordered_similarity_df = pd.DataFrame(
        ordered_similarity,
        index=[f"C{cid}: {name}" for cid, name in zip(dimension_ids, dimension_names)],
        columns=[f"NMF {idx}" for idx in ordered_component_indices],
    )

    # Component-to-dimension mass table: for each component, what share of its H
    # weight falls inside each manual dimension?
    component_mass = H @ D.T
    component_mass_share = component_mass / component_mass.sum(axis=1, keepdims=True)
    component_mass_df = pd.DataFrame(
        component_mass_share,
        index=[f"NMF {i}" for i in range(n_components)],
        columns=[f"C{cid}: {name}" for cid, name in zip(dimension_ids, dimension_names)],
    )

    diagnostics = pd.DataFrame(
        [
            {
                "matrix": "merged_ownership",
                "original_users": matrix.shape[0],
                "original_games": matrix.shape[1],
                "restricted_users_with_any_included_game": int(active_user_mask.sum()),
                "restricted_games": restricted.shape[1],
                "included_manual_dimensions": n_components,
                "restricted_nonzero_edges": int(restricted.nnz),
                "reconstruction_error": float(nmf.reconstruction_err_),
                "n_iter": int(nmf.n_iter_),
                "mean_matched_cosine": float(match_table["cosine_similarity"].mean()),
                "median_matched_cosine": float(match_table["cosine_similarity"].median()),
                "matches_ge_0p50": int((match_table["cosine_similarity"] >= 0.50).sum()),
                "matches_ge_0p40": int((match_table["cosine_similarity"] >= 0.40).sum()),
                "matches_ge_0p30": int((match_table["cosine_similarity"] >= 0.30).sum()),
            }
        ]
    )

    diagnostics.to_csv(paths.output_dir / "nmf_test_a_diagnostics.csv", index=False)
    match_table.to_csv(paths.output_dir / "nmf_test_a_best_matches.csv", index=False)
    match_table.to_csv(paths.output_dir / "nmf_test_a_hungarian_matches.csv", index=False)
    similarity_df.to_csv(paths.output_dir / "nmf_test_a_similarity_matrix.csv")
    ordered_similarity_df.to_csv(paths.output_dir / "nmf_test_a_similarity_matrix_hungarian_ordered.csv")
    component_mass_df.to_csv(paths.output_dir / "nmf_test_a_component_mass_share.csv")
    top_games.to_csv(paths.output_dir / "nmf_test_a_top_games_by_component.csv", index=False)
    included_games.to_csv(paths.output_dir / "nmf_test_a_included_games.csv", index=False)

    ordered_col_labels = [f"NMF {idx}" for idx in ordered_component_indices]

    fig, ax = plt.subplots(figsize=(12, 8))
    im = ax.imshow(ordered_similarity, cmap="Blues", vmin=0, vmax=max(0.6, ordered_similarity.max()))
    ax.set_xticks(np.arange(n_components))
    ax.set_xticklabels(ordered_col_labels, rotation=45, ha="right")
    ax.set_yticks(np.arange(n_components))
    ax.set_yticklabels([f"C{cid}: {name}" for cid, name in zip(dimension_ids, dimension_names)])
    ax.set_title("NMF Test A: Manual Taste Dimensions vs NMF Components")
    ax.set_xlabel("NMF components, ordered by best Hungarian match")
    ax.set_ylabel("Manual included profile dimensions")
    for i in range(n_components):
        for j in range(n_components):
            ax.text(j, i, f"{ordered_similarity[i, j]:.2f}", ha="center", va="center", fontsize=8)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Cosine similarity")
    fig.tight_layout()
    fig.savefig(paths.figure_dir / "nmf_test_a_similarity_heatmap.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    # Compact text summary for terminal users.
    print("NMF Test A complete")
    print(diagnostics.to_string(index=False))
    print()
    print(match_table[["manual_community", "manual_dimension", "nmf_component", "cosine_similarity", "component_top_game"]].to_string(index=False))
    print()
    print(f"Outputs written to: {paths.output_dir}")
    print(f"Figure written to: {paths.figure_dir / 'nmf_test_a_similarity_heatmap.png'}")


if __name__ == "__main__":
    main()
