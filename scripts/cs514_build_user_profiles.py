#!/usr/bin/env python3
"""Build user taste profiles from validated CS514 game communities."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_RUN_LABEL = "merged_ownership_newman_disparity_a0p025_r1p75"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unlabeled"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL)
    parser.add_argument("--incidence-label", default="merged_ownership")
    parser.add_argument(
        "--other-label",
        default="other",
        help="Catch-all profile dimension for excluded/review/tiny communities.",
    )
    return parser.parse_args()


def normalized_entropy(values: np.ndarray) -> np.ndarray:
    totals = values.sum(axis=1)
    out = np.zeros(values.shape[0], dtype=float)
    valid = totals > 0
    if not valid.any():
        return out
    probs = values[valid] / totals[valid, None]
    log_probs = np.zeros_like(probs)
    positive = probs > 0
    log_probs[positive] = np.log(probs[positive])
    entropy = -(probs * log_probs).sum(axis=1)
    max_entropy = np.log(values.shape[1]) if values.shape[1] > 1 else 1.0
    out[valid] = entropy / max_entropy if max_entropy else 0.0
    return out


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from bgg_project.cs514.incidence import load_incidence
    from bgg_project.cs514.paths import ProjectPaths, ensure_dirs

    paths = ProjectPaths.from_root(project_root)
    ensure_dirs(paths)
    profile_dir = paths.output_dir / "user_profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = paths.output_dir / "metadata" / f"{args.run_label}_community_manual_mapping.csv"
    communities_path = paths.output_dir / "communities" / f"{args.run_label}_communities.csv"
    matrix, user_index, game_index = load_incidence(paths.output_dir / "incidence" / args.incidence_label)

    mapping = pd.read_csv(mapping_path)
    communities = pd.read_csv(communities_path)
    community_to_row = mapping.set_index("community").to_dict(orient="index")
    game_to_community = dict(zip(communities["bgg_id"].astype(int), communities["community"].astype(int), strict=False))

    dimension_rows = []
    game_dimension_rows = []
    included_labels: dict[int, str] = {}
    included_slugs: dict[str, str] = {}

    for row in mapping.itertuples(index=False):
        if str(row.include_in_user_profiles).lower() == "yes":
            slug = slugify(row.manual_label)
            included_labels[int(row.community)] = row.manual_label
            included_slugs[row.manual_label] = slug
            dimension_rows.append(
                {
                    "dimension": slug,
                    "manual_label": row.manual_label,
                    "community": int(row.community),
                    "community_size": int(row.size),
                    "community_type": row.community_type,
                    "include_in_user_profiles": row.include_in_user_profiles,
                    "manual_meaningfulness": row.manual_meaningfulness,
                    "manual_notes": row.manual_notes,
                }
            )

    dimension_rows.append(
        {
            "dimension": args.other_label,
            "manual_label": "Other / excluded / review communities",
            "community": -1,
            "community_size": np.nan,
            "community_type": "other",
            "include_in_user_profiles": "yes",
            "manual_meaningfulness": "mixed",
            "manual_notes": "Catch-all for communities marked no/review/tiny/franchise/temporal artifact/bridge unless explicitly included.",
        }
    )

    ordered_dimensions = [row["dimension"] for row in dimension_rows]
    dim_to_idx = {dim: i for i, dim in enumerate(ordered_dimensions)}
    col_to_dim = np.empty(matrix.shape[1], dtype=object)

    community_sizes_by_dim = {dim: 0 for dim in ordered_dimensions}
    for game in game_index.itertuples(index=False):
        gid = int(game.bgg_id)
        community = game_to_community.get(gid)
        meta = community_to_row.get(community, {})
        if community in included_labels:
            dim = included_slugs[included_labels[community]]
        else:
            dim = args.other_label
        col_to_dim[int(game.col)] = dim
        community_sizes_by_dim[dim] += 1
        game_dimension_rows.append(
            {
                "bgg_id": gid,
                "name": game.name,
                "overall_rank": int(game.overall_rank),
                "community": community,
                "profile_dimension": dim,
                "manual_label": meta.get("manual_label", ""),
                "community_type": meta.get("community_type", ""),
                "include_in_user_profiles": meta.get("include_in_user_profiles", ""),
            }
        )

    counts = np.zeros((matrix.shape[0], len(ordered_dimensions)), dtype=np.float32)
    csc = matrix.tocsc()
    for col, dim in enumerate(col_to_dim):
        dim_idx = dim_to_idx[dim]
        start, end = csc.indptr[col], csc.indptr[col + 1]
        rows = csc.indices[start:end]
        if rows.size:
            counts[rows, dim_idx] += 1.0

    total_owned = counts.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        shares = np.divide(counts, total_owned[:, None], out=np.zeros_like(counts), where=total_owned[:, None] > 0)

    count_cols = [f"count__{dim}" for dim in ordered_dimensions]
    share_cols = [f"share__{dim}" for dim in ordered_dimensions]
    profiles = user_index.copy()
    profiles["total_selected_owned"] = total_owned.astype(int)
    profiles = pd.concat(
        [
            profiles,
            pd.DataFrame(counts.astype(int), columns=count_cols),
            pd.DataFrame(shares, columns=share_cols),
        ],
        axis=1,
    )

    share_values = shares
    dominant_idx = share_values.argmax(axis=1)
    profiles["dominant_dimension"] = [ordered_dimensions[i] for i in dominant_idx]
    profiles["dominant_share"] = share_values[np.arange(share_values.shape[0]), dominant_idx]
    profiles["included_share"] = 1.0 - profiles[f"share__{args.other_label}"]
    profiles["profile_entropy_norm"] = normalized_entropy(share_values)
    profiles["n_active_dimensions"] = (counts > 0).sum(axis=1).astype(int)

    dimension_summary = pd.DataFrame(dimension_rows)
    dimension_summary["n_games_assigned"] = dimension_summary["dimension"].map(community_sizes_by_dim).fillna(0).astype(int)
    dimension_summary["total_user_owned_edges"] = counts.sum(axis=0).astype(int)
    dimension_summary["mean_user_share"] = shares.mean(axis=0)
    dimension_summary["users_with_any"] = (counts > 0).sum(axis=0).astype(int)

    profile_path = profile_dir / f"{args.run_label}_{args.incidence_label}_user_profiles.csv"
    dimension_path = profile_dir / f"{args.run_label}_{args.incidence_label}_profile_dimensions.csv"
    game_map_path = profile_dir / f"{args.run_label}_{args.incidence_label}_game_profile_mapping.csv"
    profiles.to_csv(profile_path, index=False)
    dimension_summary.to_csv(dimension_path, index=False)
    pd.DataFrame(game_dimension_rows).to_csv(game_map_path, index=False)

    print(f"wrote {profile_path}")
    print(f"wrote {dimension_path}")
    print(f"wrote {game_map_path}")
    print("\nProfile dimensions:")
    print(dimension_summary[["dimension", "manual_label", "community_type", "n_games_assigned", "total_user_owned_edges", "mean_user_share", "users_with_any"]].to_string(index=False))
    print("\nDominant dimension counts:")
    print(profiles["dominant_dimension"].value_counts().to_string())


if __name__ == "__main__":
    main()
