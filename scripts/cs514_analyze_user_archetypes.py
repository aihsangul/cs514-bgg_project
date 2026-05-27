#!/usr/bin/env python3
"""Analyze user archetypes from CS514 community-based taste profiles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_RUN_LABEL = "merged_ownership_newman_disparity_a0p025_r1p75"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL)
    parser.add_argument("--incidence-label", default="merged_ownership")
    parser.add_argument("--min-selected-owned", type=int, default=15)
    parser.add_argument("--specialist-threshold", type=float, default=0.40)
    parser.add_argument("--leaning-threshold", type=float, default=0.25)
    parser.add_argument("--generalist-entropy", type=float, default=0.75)
    parser.add_argument("--generalist-max-dominant", type=float, default=0.35)
    parser.add_argument("--low-coverage-threshold", type=float, default=0.50)
    parser.add_argument("--top-games-per-archetype", type=int, default=20)
    parser.add_argument("--min-archetype-users-for-games", type=int, default=10)
    return parser.parse_args()


def clean_negative_zero(series: pd.Series, decimals: int = 6) -> pd.Series:
    rounded = series.round(decimals)
    return rounded.mask(rounded.abs() < 10 ** (-decimals), 0.0)


def classify_user(row: pd.Series, args: argparse.Namespace) -> str:
    if not bool(row["eligible_for_archetype"]):
        return "insufficient_selected_owned"

    dominant = str(row["dominant_dimension"])
    if dominant == "other":
        if float(row["included_share"]) < args.low_coverage_threshold:
            return "other_dominant_low_coverage"
        return "other_dominant_mixed"

    dominant_share = float(row["dominant_share"])
    entropy = float(row["profile_entropy_norm"])
    if dominant_share >= args.specialist_threshold:
        return f"specialist__{dominant}"
    if entropy >= args.generalist_entropy and dominant_share < args.generalist_max_dominant:
        return "generalist"
    if dominant_share >= args.leaning_threshold:
        return f"leaning__{dominant}"
    return f"mixed__{dominant}"


def archetype_family(archetype: str) -> str:
    if archetype == "insufficient_selected_owned":
        return "insufficient_selected_owned"
    if archetype.startswith("other_dominant"):
        return "other_dominant"
    if archetype == "generalist":
        return "generalist"
    if archetype.startswith("specialist__"):
        return "specialist"
    if archetype.startswith("leaning__"):
        return "leaning"
    if archetype.startswith("mixed__"):
        return "mixed"
    return "other"


def summarize_archetypes(users: pd.DataFrame) -> pd.DataFrame:
    eligible = users[users["eligible_for_archetype"]].copy()
    total = len(eligible)
    grouped = eligible.groupby("archetype", dropna=False)
    summary = grouped.agg(
        n_users=("username", "count"),
        median_selected_owned=("total_selected_owned", "median"),
        mean_selected_owned=("total_selected_owned", "mean"),
        mean_included_share=("included_share", "mean"),
        median_included_share=("included_share", "median"),
        mean_entropy=("profile_entropy_norm", "mean"),
        median_entropy=("profile_entropy_norm", "median"),
        mean_dominant_share=("dominant_share", "mean"),
        median_dominant_share=("dominant_share", "median"),
        most_common_dominant_dimension=("dominant_dimension", lambda s: s.mode().iat[0] if not s.mode().empty else ""),
        most_common_taste_dimension=("dominant_taste_dimension", lambda s: s.mode().iat[0] if not s.mode().empty else ""),
    ).reset_index()
    summary["pct_eligible_users"] = summary["n_users"] / total if total else np.nan
    ordered = [
        "archetype",
        "n_users",
        "pct_eligible_users",
        "median_selected_owned",
        "mean_selected_owned",
        "mean_included_share",
        "median_included_share",
        "mean_entropy",
        "median_entropy",
        "mean_dominant_share",
        "median_dominant_share",
        "most_common_dominant_dimension",
        "most_common_taste_dimension",
    ]
    return summary[ordered].sort_values(["n_users", "archetype"], ascending=[False, True])


def summarize_archetype_families(users: pd.DataFrame) -> pd.DataFrame:
    total = len(users)
    eligible_total = int(users["eligible_for_archetype"].sum())
    grouped = users.groupby("archetype_family", dropna=False)
    summary = grouped.agg(
        n_users=("username", "count"),
        eligible_users=("eligible_for_archetype", "sum"),
        median_selected_owned=("total_selected_owned", "median"),
        mean_selected_owned=("total_selected_owned", "mean"),
        mean_included_share=("included_share", "mean"),
        median_included_share=("included_share", "median"),
        mean_entropy=("profile_entropy_norm", "mean"),
        median_entropy=("profile_entropy_norm", "median"),
        mean_dominant_share=("dominant_share", "mean"),
        median_dominant_share=("dominant_share", "median"),
    ).reset_index()
    summary["pct_all_users"] = summary["n_users"] / total if total else np.nan
    summary["pct_eligible_users"] = summary["eligible_users"] / eligible_total if eligible_total else np.nan
    ordered = [
        "archetype_family",
        "n_users",
        "eligible_users",
        "pct_all_users",
        "pct_eligible_users",
        "median_selected_owned",
        "mean_selected_owned",
        "mean_included_share",
        "median_included_share",
        "mean_entropy",
        "median_entropy",
        "mean_dominant_share",
        "median_dominant_share",
    ]
    return summary[ordered].sort_values(["eligible_users", "n_users"], ascending=[False, False])


def summarize_dimensions(users: pd.DataFrame, share_cols: list[str], other_label: str = "other") -> pd.DataFrame:
    eligible = users[users["eligible_for_archetype"]].copy()
    rows = []
    for col in share_cols:
        dim = col.removeprefix("share__")
        if dim == other_label:
            continue
        values = eligible[col]
        rows.append(
            {
                "dimension": dim,
                "users_with_any": int((values > 0).sum()),
                "pct_users_with_any": float((values > 0).mean()) if len(values) else np.nan,
                "mean_share": float(values.mean()) if len(values) else np.nan,
                "median_nonzero_share": float(values[values > 0].median()) if (values > 0).any() else 0.0,
                "users_with_25pct_or_more": int((values >= 0.25).sum()),
                "users_with_40pct_or_more": int((values >= 0.40).sum()),
                "dominant_users": int((eligible["dominant_dimension"] == dim).sum()),
                "dominant_taste_users": int((eligible["dominant_taste_dimension"] == dim).sum()),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values(["dominant_taste_users", "mean_share"], ascending=[False, False])


def build_top_games_by_archetype(
    users: pd.DataFrame,
    matrix,
    game_index: pd.DataFrame,
    game_mapping: pd.DataFrame,
    top_n: int,
    min_users: int,
) -> pd.DataFrame:
    rows = []
    game_meta = game_index.merge(game_mapping, on=["bgg_id", "name", "overall_rank"], how="left")
    eligible = users[users["eligible_for_archetype"]].copy()
    for archetype, group in eligible.groupby("archetype"):
        if len(group) < min_users:
            continue
        row_ids = group["row"].astype(int).to_numpy()
        owned_counts = np.asarray(matrix[row_ids].sum(axis=0)).ravel()
        if owned_counts.max(initial=0) <= 0:
            continue
        top_idx = np.argsort(-owned_counts)[:top_n]
        for rank, col in enumerate(top_idx, start=1):
            count = int(owned_counts[col])
            if count <= 0:
                continue
            meta = game_meta.iloc[int(col)]
            rows.append(
                {
                    "archetype": archetype,
                    "archetype_n_users": int(len(group)),
                    "within_archetype_rank": rank,
                    "bgg_id": int(meta["bgg_id"]),
                    "name": meta["name"],
                    "overall_rank": int(meta["overall_rank"]),
                    "owner_count_in_archetype": count,
                    "owner_share_in_archetype": count / len(group),
                    "profile_dimension": meta.get("profile_dimension", ""),
                    "manual_label": meta.get("manual_label", ""),
                    "community_type": meta.get("community_type", ""),
                    "community": meta.get("community", ""),
                }
            )
    return pd.DataFrame(rows)


def decompose_other_dominant_users(
    users: pd.DataFrame,
    matrix,
    game_mapping: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    other_users = users[
        users["eligible_for_archetype"] & users["dominant_dimension"].eq("other")
    ].copy()
    other_games = game_mapping[game_mapping["profile_dimension"].eq("other")].copy()
    if other_users.empty or other_games.empty:
        return pd.DataFrame(), pd.DataFrame()

    game_col_lookup = game_mapping.reset_index().rename(columns={"index": "col"})
    other_cols = game_col_lookup[game_col_lookup["profile_dimension"].eq("other")]["col"].astype(int).to_numpy()
    row_ids = other_users["row"].astype(int).to_numpy()
    sub = matrix[row_ids][:, other_cols].tocoo()

    other_meta = game_col_lookup.iloc[other_cols].reset_index(drop=True)
    counts_by_type: dict[str, int] = {}
    counts_by_label: dict[str, int] = {}
    user_rows = []

    for user_pos, user in enumerate(other_users.itertuples(index=False)):
        start = sub.row == user_pos
        local_cols = sub.col[start]
        if local_cols.size == 0:
            continue
        meta = other_meta.iloc[local_cols]
        type_counts = meta["community_type"].fillna("unknown").value_counts()
        label_counts = meta["manual_label"].fillna("").replace("", "unlabeled").value_counts()
        total_other_owned = int(local_cols.size)
        top_type = type_counts.index[0]
        top_label = label_counts.index[0]
        user_rows.append(
            {
                "username": user.username,
                "row": int(user.row),
                "total_selected_owned": int(user.total_selected_owned),
                "other_owned_count": total_other_owned,
                "included_share": float(user.included_share),
                "dominant_taste_dimension": user.dominant_taste_dimension,
                "dominant_taste_share": float(user.dominant_taste_share),
                "top_other_community_type": top_type,
                "top_other_community_type_count": int(type_counts.iloc[0]),
                "top_other_community_type_share": float(type_counts.iloc[0] / total_other_owned),
                "top_other_manual_label": top_label,
                "top_other_manual_label_count": int(label_counts.iloc[0]),
                "top_other_manual_label_share": float(label_counts.iloc[0] / total_other_owned),
            }
        )
        for community_type, count in type_counts.items():
            key = str(community_type)
            counts_by_type[key] = counts_by_type.get(key, 0) + int(count)
        for label, count in label_counts.items():
            key = str(label)
            counts_by_label[key] = counts_by_label.get(key, 0) + int(count)

    total = sum(counts_by_type.values())
    aggregate_rows = [
        {
            "group": "community_type",
            "value": value,
            "owned_edges": count,
            "share_of_other_owned_edges": count / total if total else np.nan,
        }
        for value, count in counts_by_type.items()
    ]
    label_total = sum(counts_by_label.values())
    aggregate_rows.extend(
        {
            "group": "manual_label",
            "value": value,
            "owned_edges": count,
            "share_of_other_owned_edges": count / label_total if label_total else np.nan,
        }
        for value, count in counts_by_label.items()
    )
    aggregate = pd.DataFrame(aggregate_rows).sort_values(
        ["group", "owned_edges"], ascending=[True, False]
    )
    per_user = pd.DataFrame(user_rows).sort_values(
        ["top_other_community_type_count", "other_owned_count"], ascending=[False, False]
    )
    return aggregate, per_user


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

    prefix = f"{args.run_label}_{args.incidence_label}"
    profile_path = profile_dir / f"{prefix}_user_profiles.csv"
    game_mapping_path = profile_dir / f"{prefix}_game_profile_mapping.csv"
    profiles = pd.read_csv(profile_path)
    game_mapping = pd.read_csv(game_mapping_path)
    matrix, user_index, game_index = load_incidence(paths.output_dir / "incidence" / args.incidence_label)

    users = profiles.copy()
    users["profile_entropy_norm"] = clean_negative_zero(users["profile_entropy_norm"])
    users["eligible_for_archetype"] = users["total_selected_owned"] >= args.min_selected_owned

    share_cols = [col for col in users.columns if col.startswith("share__")]
    taste_share_cols = [col for col in share_cols if col != "share__other"]
    taste_shares = users[taste_share_cols].to_numpy()
    taste_idx = taste_shares.argmax(axis=1)
    taste_dims = [col.removeprefix("share__") for col in taste_share_cols]
    users["dominant_taste_dimension"] = [taste_dims[i] for i in taste_idx]
    users["dominant_taste_share"] = taste_shares[np.arange(taste_shares.shape[0]), taste_idx]
    zero_taste = taste_shares.sum(axis=1) <= 0
    users.loc[zero_taste, "dominant_taste_dimension"] = ""
    users.loc[zero_taste, "dominant_taste_share"] = 0.0

    users["archetype"] = users.apply(lambda row: classify_user(row, args), axis=1)
    users["archetype_family"] = users["archetype"].map(archetype_family)

    archetype_summary = summarize_archetypes(users)
    archetype_family_summary = summarize_archetype_families(users)
    dimension_summary = summarize_dimensions(users, share_cols)
    top_games = build_top_games_by_archetype(
        users,
        matrix,
        game_index,
        game_mapping,
        top_n=args.top_games_per_archetype,
        min_users=args.min_archetype_users_for_games,
    )
    other_aggregate, other_per_user = decompose_other_dominant_users(users, matrix, game_mapping)

    archetype_path = profile_dir / f"{prefix}_user_archetypes.csv"
    archetype_summary_path = profile_dir / f"{prefix}_archetype_summary.csv"
    archetype_family_summary_path = profile_dir / f"{prefix}_archetype_family_summary.csv"
    dimension_summary_path = profile_dir / f"{prefix}_archetype_dimension_summary.csv"
    top_games_path = profile_dir / f"{prefix}_archetype_top_games.csv"
    other_aggregate_path = profile_dir / f"{prefix}_other_dominant_decomposition.csv"
    other_per_user_path = profile_dir / f"{prefix}_other_dominant_users.csv"

    users.to_csv(archetype_path, index=False)
    archetype_summary.to_csv(archetype_summary_path, index=False)
    archetype_family_summary.to_csv(archetype_family_summary_path, index=False)
    dimension_summary.to_csv(dimension_summary_path, index=False)
    top_games.to_csv(top_games_path, index=False)
    other_aggregate.to_csv(other_aggregate_path, index=False)
    other_per_user.to_csv(other_per_user_path, index=False)

    print(f"wrote {archetype_path}")
    print(f"wrote {archetype_summary_path}")
    print(f"wrote {archetype_family_summary_path}")
    print(f"wrote {dimension_summary_path}")
    print(f"wrote {top_games_path}")
    print(f"wrote {other_aggregate_path}")
    print(f"wrote {other_per_user_path}")
    print("\nEligibility:")
    print(
        users["eligible_for_archetype"]
        .value_counts()
        .rename(index={True: "eligible", False: "filtered_out"})
        .to_string()
    )
    print("\nArchetype summary:")
    print(archetype_summary.head(30).to_string(index=False))
    print("\nArchetype family summary:")
    print(archetype_family_summary.to_string(index=False))
    print("\nDimension summary:")
    print(dimension_summary.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
