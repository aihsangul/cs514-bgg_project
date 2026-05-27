"""Load raw user / game data from processed CSVs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .paths import ProjectPaths
from .signals import split_pipe


def load_users(paths: ProjectPaths) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (baseline, expansion, merged) user DataFrames."""
    baseline = pd.read_csv(paths.baseline_dir / "reliable_users.csv")
    expansion = pd.read_csv(paths.expansion_dir / "reliable_users.csv")
    baseline["cohort"] = "baseline"
    expansion["cohort"] = "expansion"
    merged = pd.concat([baseline, expansion], ignore_index=True)
    return baseline, expansion, merged


def load_games(paths: ProjectPaths) -> pd.DataFrame:
    """Return the 2500 selected games joined with full taxonomy details."""
    selected = pd.read_csv(paths.baseline_dir / "selected_games.csv")
    selected_ids = set(selected["bgg_id"].astype(int))
    details = pd.read_csv(paths.details_csv)
    games = details[details["bgg_id"].isin(selected_ids)].copy()
    games["bgg_id"] = games["bgg_id"].astype(int)
    games = games.sort_values("overall_rank").reset_index(drop=True)
    games["mechanics_list"] = games["mechanics"].map(split_pipe)
    games["categories_list"] = games["categories"].map(split_pipe)
    return games


def edge_paths_for(paths: ProjectPaths, cohort: str) -> list[Path]:
    """Return the list of edge CSVs that make up *cohort*."""
    if cohort == "baseline":
        return [paths.baseline_dir / "reliable_user_collection_edges.csv"]
    if cohort == "expansion":
        return [paths.expansion_dir / "reliable_user_collection_edges.csv"]
    if cohort == "merged":
        return [
            paths.baseline_dir / "reliable_user_collection_edges.csv",
            paths.expansion_dir / "reliable_user_collection_edges.csv",
        ]
    raise ValueError(f"Unknown cohort: {cohort!r}")


def user_names_for(paths: ProjectPaths, cohort: str) -> set[str] | None:
    """Return the set of usernames for *cohort*, or None to accept all."""
    baseline, expansion, merged = load_users(paths)
    if cohort == "baseline":
        return set(baseline["username"].astype(str))
    if cohort == "expansion":
        return set(expansion["username"].astype(str))
    if cohort == "merged":
        return set(merged["username"].astype(str))
    return None
