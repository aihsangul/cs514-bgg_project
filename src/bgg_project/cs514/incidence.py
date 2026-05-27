"""Build, save, load, and diagnose user-game incidence matrices."""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from .signals import SIGNAL_SPECS, signal_mask


def compute_edge_overlap(
    edge_paths: list[Path],
    selected_ids: set[int],
    allowed_users: set[str] | None = None,
    chunksize: int = 500_000,
) -> pd.DataFrame:
    """Compute pairwise Jaccard overlap between signal layers at the (user, game) cell level."""
    from collections import Counter

    counts: Counter = Counter()
    selected_ids = set(map(int, selected_ids))
    signals = list(SIGNAL_SPECS)
    pair_names = list(combinations(signals, 2))
    usecols = ["username", "bgg_id", *sorted({c for cols in SIGNAL_SPECS.values() for c in cols})]

    for edge_csv in edge_paths:
        for chunk in pd.read_csv(edge_csv, usecols=usecols, chunksize=chunksize, low_memory=False):
            chunk = chunk[chunk["bgg_id"].isin(selected_ids)]
            if allowed_users is not None:
                chunk = chunk[chunk["username"].astype(str).isin(allowed_users)]
            if chunk.empty:
                continue
            masks = {name: signal_mask(chunk, name) for name in signals}
            for name, mask in masks.items():
                counts[(name, "size")] += int(mask.sum())
            for a, b in pair_names:
                counts[(a, b, "intersection")] += int((masks[a] & masks[b]).sum())
                counts[(a, b, "union")] += int((masks[a] | masks[b]).sum())

    rows = []
    for a, b in pair_names:
        inter = counts[(a, b, "intersection")]
        union = counts[(a, b, "union")]
        rows.append(
            {
                "signal_a": a,
                "signal_b": b,
                "n_a": counts[(a, "size")],
                "n_b": counts[(b, "size")],
                "intersection": inter,
                "union": union,
                "jaccard": inter / union if union else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_incidence(
    edge_paths: list[Path],
    games: pd.DataFrame,
    signal: str,
    allowed_users: set[str] | None = None,
    chunksize: int = 500_000,
) -> tuple[sparse.csr_matrix, pd.DataFrame, pd.DataFrame]:
    """
    Stream edge CSVs and build a binary CSR incidence matrix (users × games).
    Returns (matrix, user_index DataFrame, game_index DataFrame).
    """
    selected_ids = list(games["bgg_id"].astype(int))
    game_to_col = {gid: i for i, gid in enumerate(selected_ids)}
    selected_set = set(selected_ids)
    user_to_row: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    usecols = ["username", "bgg_id", *SIGNAL_SPECS[signal]]

    for edge_csv in edge_paths:
        for chunk in pd.read_csv(edge_csv, usecols=usecols, chunksize=chunksize, low_memory=False):
            chunk = chunk[chunk["bgg_id"].isin(selected_set)]
            if allowed_users is not None:
                chunk = chunk[chunk["username"].astype(str).isin(allowed_users)]
            if chunk.empty:
                continue
            chunk = chunk[signal_mask(chunk, signal)]
            if chunk.empty:
                continue
            chunk = chunk[["username", "bgg_id"]].dropna().drop_duplicates()
            for username, gid in zip(chunk["username"].astype(str), chunk["bgg_id"].astype(int), strict=False):
                row = user_to_row.setdefault(username, len(user_to_row))
                rows.append(row)
                cols.append(game_to_col[int(gid)])

    data = np.ones(len(rows), dtype=np.float32)
    matrix = sparse.coo_matrix(
        (data, (rows, cols)),
        shape=(len(user_to_row), len(selected_ids)),
        dtype=np.float32,
    ).tocsr()
    matrix.data[:] = 1.0
    matrix.eliminate_zeros()

    user_index = pd.DataFrame(
        sorted(user_to_row.items(), key=lambda kv: kv[1]),
        columns=["username", "row"],
    )
    game_index = games[["bgg_id", "name", "overall_rank"]].copy()
    game_index["col"] = range(len(game_index))
    return matrix, user_index, game_index


def save_incidence(
    matrix: sparse.csr_matrix,
    user_index: pd.DataFrame,
    game_index: pd.DataFrame,
    out_prefix: Path,
) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    sparse.save_npz(out_prefix.with_suffix(".npz"), matrix)
    user_index.to_csv(out_prefix.with_name(out_prefix.name + "_users.csv"), index=False)
    game_index.to_csv(out_prefix.with_name(out_prefix.name + "_games.csv"), index=False)


def load_incidence(prefix: Path) -> tuple[sparse.csr_matrix, pd.DataFrame, pd.DataFrame]:
    matrix = sparse.load_npz(prefix.with_suffix(".npz")).tocsr()
    user_index = pd.read_csv(prefix.with_name(prefix.name + "_users.csv"))
    game_index = pd.read_csv(prefix.with_name(prefix.name + "_games.csv"))
    return matrix, user_index, game_index


def incidence_diagnostics(matrix: sparse.csr_matrix, label: str) -> dict:
    row_sum = np.asarray(matrix.sum(axis=1)).ravel()
    col_sum = np.asarray(matrix.sum(axis=0)).ravel()
    active_rows = row_sum[row_sum > 0]
    active_cols = col_sum[col_sum > 0]
    return {
        "label": label,
        "n_users": matrix.shape[0],
        "n_games": matrix.shape[1],
        "nnz": int(matrix.nnz),
        "active_users": int((row_sum > 0).sum()),
        "active_games": int((col_sum > 0).sum()),
        "median_user_degree": float(np.median(active_rows)) if active_rows.size else 0.0,
        "p99_user_degree": float(np.percentile(active_rows, 99)) if active_rows.size else 0.0,
        "max_user_degree": float(active_rows.max()) if active_rows.size else 0.0,
        "median_game_degree": float(np.median(active_cols)) if active_cols.size else 0.0,
        "min_game_degree": float(active_cols.min()) if active_cols.size else 0.0,
        "max_game_degree": float(active_cols.max()) if active_cols.size else 0.0,
    }
