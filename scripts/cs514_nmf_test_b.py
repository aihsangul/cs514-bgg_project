"""Run NMF Test B full-matrix k-sweep for CS514 BGG project.

Test B asks what latent components appear when NMF is applied to the full
merged user-game ownership matrix, including all 2,500 games rather than only
the manually selected profile dimensions.

The script runs multiple k values and seeds, measures reconstruction error and
component stability, and exports top games plus component mass by community type.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

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
        output_dir=analysis / "matrix_decomposition" / "nmf_test_b",
        figure_dir=analysis / "figures" / "matrix_decomposition",
    )


def normalize_yes_no(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def safe_label(value: object, fallback: str) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return fallback
    return str(value)


def run_nmf(matrix: sp.csr_matrix, k: int, seed: int, max_iter: int) -> tuple[NMF, np.ndarray, np.ndarray]:
    model = NMF(
        n_components=k,
        init="nndsvdar",
        solver="cd",
        beta_loss="frobenius",
        tol=1e-4,
        max_iter=max_iter,
        random_state=seed,
    )
    W = model.fit_transform(matrix)
    H = model.components_
    return model, W, H


def matched_component_similarity(H_a: np.ndarray, H_b: np.ndarray) -> dict[str, float]:
    sim = cosine_similarity(H_a, H_b)
    rows, cols = linear_sum_assignment(-sim)
    matched = sim[rows, cols]
    return {
        "mean_matched_cosine": float(np.mean(matched)),
        "median_matched_cosine": float(np.median(matched)),
        "min_matched_cosine": float(np.min(matched)),
    }


def build_group_matrix(labels: Iterable[str]) -> tuple[np.ndarray, list[str]]:
    labels = [str(x) for x in labels]
    groups = sorted(set(labels))
    group_to_idx = {group: idx for idx, group in enumerate(groups)}
    D = np.zeros((len(groups), len(labels)), dtype=float)
    for col, group in enumerate(labels):
        D[group_to_idx[group], col] = 1.0
    return D, groups


def main() -> None:
    paths = get_paths()
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.figure_dir.mkdir(parents=True, exist_ok=True)

    k_values = [5, 8, 11, 15, 20, 25]
    seeds = [514, 515, 516]
    max_iter = 600

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
    game_meta["community_label"] = [
        safe_label(label, f"C{community}")
        for label, community in zip(game_meta["manual_label"], game_meta["community"])
    ]
    game_meta["community_type"] = game_meta["community_type"].fillna("unlabeled")
    game_meta["include_norm"] = normalize_yes_no(game_meta["include_in_user_profiles"])
    game_meta = game_meta.sort_values("col").reset_index(drop=True)

    type_matrix, type_names = build_group_matrix(game_meta["community_type"])
    community_matrix, community_names = build_group_matrix(
        [
            f"C{int(row.community)}: {row.community_label}"
            for row in game_meta.itertuples(index=False)
        ]
    )
    included_manual = manual[normalize_yes_no(manual["include_in_user_profiles"]) == "yes"].copy()
    included_manual = included_manual.sort_values("community").reset_index(drop=True)
    included_names = [
        f"C{int(row.community)}: {safe_label(row.manual_label, f'C{int(row.community)}')}"
        for row in included_manual.itertuples(index=False)
    ]
    included_matrix = np.zeros((len(included_manual), matrix.shape[1]), dtype=float)
    community_to_dim = {
        int(row.community): idx for idx, row in enumerate(included_manual.itertuples(index=False))
    }
    for game in game_meta.itertuples(index=False):
        community = int(game.community)
        if community in community_to_dim:
            included_matrix[community_to_dim[community], int(game.col)] = 1.0

    diagnostics_rows: list[dict[str, object]] = []
    stability_rows: list[dict[str, object]] = []
    top_game_rows: list[dict[str, object]] = []
    type_mass_rows: list[dict[str, object]] = []
    community_mass_rows: list[dict[str, object]] = []
    included_similarity_rows: list[dict[str, object]] = []
    H_by_k_seed: dict[tuple[int, int], np.ndarray] = {}

    for k in k_values:
        print(f"Running NMF k={k}...")
        for seed in seeds:
            model, _W, H = run_nmf(matrix, k=k, seed=seed, max_iter=max_iter)
            H_by_k_seed[(k, seed)] = H
            diagnostics_rows.append(
                {
                    "k": k,
                    "seed": seed,
                    "reconstruction_error": float(model.reconstruction_err_),
                    "n_iter": int(model.n_iter_),
                }
            )
            print(
                f"  seed={seed} error={model.reconstruction_err_:.3f} "
                f"iters={model.n_iter_}"
            )

        for seed_a, seed_b in combinations(seeds, 2):
            metrics = matched_component_similarity(H_by_k_seed[(k, seed_a)], H_by_k_seed[(k, seed_b)])
            stability_rows.append(
                {
                    "k": k,
                    "seed_a": seed_a,
                    "seed_b": seed_b,
                    **metrics,
                }
            )

    diagnostics = pd.DataFrame(diagnostics_rows)
    stability = pd.DataFrame(stability_rows)
    k_summary = diagnostics.groupby("k", as_index=False).agg(
        mean_reconstruction_error=("reconstruction_error", "mean"),
        std_reconstruction_error=("reconstruction_error", "std"),
        mean_n_iter=("n_iter", "mean"),
    ).merge(
        stability.groupby("k", as_index=False).agg(
            mean_seed_stability=("mean_matched_cosine", "mean"),
            std_seed_stability=("mean_matched_cosine", "std"),
            median_seed_stability=("median_matched_cosine", "median"),
            min_seed_stability=("min_matched_cosine", "min"),
        ),
        on="k",
        how="left",
    )
    k_summary["error_drop_from_previous"] = -k_summary["mean_reconstruction_error"].diff()
    k_summary["relative_error_drop_from_previous"] = (
        k_summary["error_drop_from_previous"] / k_summary["mean_reconstruction_error"].shift(1)
    )

    canonical_rows: list[dict[str, object]] = []
    for k in k_values:
        best_seed = int(
            diagnostics.loc[diagnostics["k"] == k]
            .sort_values(["reconstruction_error", "seed"])
            .iloc[0]["seed"]
        )
        canonical_rows.append({"k": k, "canonical_seed": best_seed})
        H = H_by_k_seed[(k, best_seed)]

        type_mass = H @ type_matrix.T
        type_share = type_mass / type_mass.sum(axis=1, keepdims=True)
        community_mass = H @ community_matrix.T
        community_share = community_mass / community_mass.sum(axis=1, keepdims=True)
        included_similarity = cosine_similarity(included_matrix, H)

        for component_idx in range(k):
            weights = H[component_idx]
            top_positions = np.argsort(weights)[::-1][:25]
            best_type_idx = int(np.argmax(type_share[component_idx]))
            best_comm_idx = int(np.argmax(community_share[component_idx]))
            best_dim_idx = int(np.argmax(included_similarity[:, component_idx]))

            type_mass_rows.append(
                {
                    "k": k,
                    "seed": best_seed,
                    "nmf_component": component_idx,
                    "best_community_type": type_names[best_type_idx],
                    "best_community_type_share": float(type_share[component_idx, best_type_idx]),
                    **{
                        f"type_share__{type_name}": float(type_share[component_idx, idx])
                        for idx, type_name in enumerate(type_names)
                    },
                }
            )
            community_mass_rows.append(
                {
                    "k": k,
                    "seed": best_seed,
                    "nmf_component": component_idx,
                    "best_community": community_names[best_comm_idx],
                    "best_community_share": float(community_share[component_idx, best_comm_idx]),
                }
            )
            included_similarity_rows.append(
                {
                    "k": k,
                    "seed": best_seed,
                    "nmf_component": component_idx,
                    "best_included_dimension": included_names[best_dim_idx],
                    "best_included_dimension_cosine": float(
                        included_similarity[best_dim_idx, component_idx]
                    ),
                    **{
                        f"cosine__{name}": float(included_similarity[idx, component_idx])
                        for idx, name in enumerate(included_names)
                    },
                }
            )
            for rank, pos in enumerate(top_positions, start=1):
                game = game_meta.iloc[int(pos)]
                top_game_rows.append(
                    {
                        "k": k,
                        "seed": best_seed,
                        "nmf_component": component_idx,
                        "component_game_rank": rank,
                        "component_weight": float(weights[pos]),
                        "bgg_id": int(game["bgg_id"]),
                        "name": game["name"],
                        "overall_rank": int(game["overall_rank"]),
                        "community": int(game["community"]),
                        "manual_label": game["manual_label"],
                        "community_type": game["community_type"],
                        "include_in_user_profiles": game["include_in_user_profiles"],
                    }
                )

    canonical = pd.DataFrame(canonical_rows)
    top_games = pd.DataFrame(top_game_rows)
    type_mass_df = pd.DataFrame(type_mass_rows)
    community_mass_df = pd.DataFrame(community_mass_rows)
    included_similarity_df = pd.DataFrame(included_similarity_rows)

    diagnostics.to_csv(paths.output_dir / "nmf_test_b_run_diagnostics.csv", index=False)
    stability.to_csv(paths.output_dir / "nmf_test_b_seed_stability.csv", index=False)
    k_summary.to_csv(paths.output_dir / "nmf_test_b_k_summary.csv", index=False)
    canonical.to_csv(paths.output_dir / "nmf_test_b_canonical_seeds.csv", index=False)
    top_games.to_csv(paths.output_dir / "nmf_test_b_top_games_by_component.csv", index=False)
    type_mass_df.to_csv(paths.output_dir / "nmf_test_b_component_type_mass_share.csv", index=False)
    community_mass_df.to_csv(paths.output_dir / "nmf_test_b_component_community_mass_share.csv", index=False)
    included_similarity_df.to_csv(
        paths.output_dir / "nmf_test_b_component_included_dimension_similarity.csv",
        index=False,
    )

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        k_summary["k"],
        k_summary["mean_reconstruction_error"],
        yerr=k_summary["std_reconstruction_error"].fillna(0),
        marker="o",
        color="#4C78A8",
    )
    ax.set_title("NMF Test B: Reconstruction Error by k")
    ax.set_xlabel("Number of NMF components (k)")
    ax.set_ylabel("Mean reconstruction error")
    fig.tight_layout()
    fig.savefig(paths.figure_dir / "nmf_test_b_reconstruction_error.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        k_summary["k"],
        k_summary["mean_seed_stability"],
        yerr=k_summary["std_seed_stability"].fillna(0),
        marker="o",
        color="#F58518",
    )
    ax.set_ylim(0, 1)
    ax.set_title("NMF Test B: Component Stability Across Seeds")
    ax.set_xlabel("Number of NMF components (k)")
    ax.set_ylabel("Mean Hungarian-matched cosine")
    fig.tight_layout()
    fig.savefig(paths.figure_dir / "nmf_test_b_seed_stability.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    print("NMF Test B complete")
    print(k_summary.to_string(index=False))
    print()
    print(f"Outputs written to: {paths.output_dir}")


if __name__ == "__main__":
    main()
