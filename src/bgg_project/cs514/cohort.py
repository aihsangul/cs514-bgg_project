"""Baseline subsample helpers: random draw and propensity-matched sampling."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


MATCH_FEATURES = ["collection_item_count", "selected_owned_count"]

BALANCE_FEATURES = [
    "collection_item_count",
    "owned_count",
    "rated_count",
    "numplays_sum",
    "selected_game_overlap_count",
    "selected_owned_count",
    "selected_rated_count",
]


def coerce_numeric(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    df = df.copy()
    for f in features:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0)
    return df


def balance_summary(users: pd.DataFrame, label: str, replicate: int | str) -> list[dict]:
    """Descriptive statistics for each balance feature in *users*."""
    rows = []
    for feature in BALANCE_FEATURES:
        if feature not in users.columns:
            continue
        vals = pd.to_numeric(users[feature], errors="coerce").dropna()
        rows.append(
            {
                "replicate": replicate,
                "sample": label,
                "feature": feature,
                "n_users": len(users),
                "p25": vals.quantile(0.25),
                "median": vals.quantile(0.50),
                "p75": vals.quantile(0.75),
                "mean": vals.mean(),
            }
        )
    return rows


def build_nn_matcher(
    baseline: pd.DataFrame,
    expansion: pd.DataFrame,
    k_neighbors: int = 5,
) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    """
    Fit a k-NN matcher on log1p(MATCH_FEATURES) and return
    (distances, indices, fitted_scaler) from kneighbors(expansion).
    """
    x_base = np.log1p(baseline[MATCH_FEATURES].to_numpy(dtype=float))
    x_exp = np.log1p(expansion[MATCH_FEATURES].to_numpy(dtype=float))
    scaler = StandardScaler().fit(np.vstack([x_base, x_exp]))
    x_base_s = scaler.transform(x_base)
    x_exp_s = scaler.transform(x_exp)
    k = min(k_neighbors, len(baseline))
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean").fit(x_base_s)
    distances, indices = nn.kneighbors(x_exp_s)
    return distances, indices, scaler


def draw_random_subsample(
    baseline: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    rep: int,
) -> pd.DataFrame:
    """Draw a random subsample of size *n* from *baseline*."""
    sample = baseline.sample(n=n, replace=False, random_state=int(rng.integers(0, 10**9))).copy()
    sample[["replicate", "sample", "match_distance", "reuse_count"]] = [rep, "baseline_random", np.nan, 1]
    return sample[["replicate", "sample", "username", "match_distance", "reuse_count"]]


def draw_matched_subsample(
    baseline: pd.DataFrame,
    distances: np.ndarray,
    indices: np.ndarray,
    rng: np.random.Generator,
    rep: int,
) -> tuple[pd.DataFrame, dict]:
    """
    Draw one matched subsample from *baseline* using pre-computed k-NN indices.
    For each expansion user, pick one of its k nearest baseline neighbours at random.
    """
    chosen_idxs, chosen_distances = [], []
    for row_distances, row_indices in zip(distances, indices, strict=False):
        pick = int(rng.integers(0, len(row_indices)))
        chosen_idxs.append(int(row_indices[pick]))
        chosen_distances.append(float(row_distances[pick]))

    matched = baseline.iloc[chosen_idxs].copy()
    reuse = matched["username"].value_counts()
    matched["replicate"] = rep
    matched["sample"] = "baseline_matched"
    matched["match_distance"] = chosen_distances
    matched["reuse_count"] = matched["username"].map(reuse).astype(int)

    diagnostics = {
        "replicate": rep,
        "n_requested": len(chosen_idxs),
        "n_unique_baseline_users_used": int(matched["username"].nunique()),
        "max_reuse_count": int(matched["reuse_count"].max()),
        "median_match_distance": float(np.median(chosen_distances)),
        "p95_match_distance": float(np.percentile(chosen_distances, 95)),
    }
    return matched[["replicate", "sample", "username", "match_distance", "reuse_count"]], diagnostics
