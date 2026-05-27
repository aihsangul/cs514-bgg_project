"""Newman RA projection and disparity-filter backbone extraction."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse


def newman_projection(matrix: sparse.csr_matrix) -> np.ndarray:
    """
    Weighted game-game projection using Newman's resource-allocation scheme.
    Each user with degree d contributes 1/(d-1) to each co-owned game pair.
    Users with d < 2 are excluded.
    Returns a dense float32 symmetric matrix of shape (n_games, n_games).
    """
    row_degree = np.asarray(matrix.sum(axis=1)).ravel()
    active = row_degree >= 2
    if not active.any():
        return np.zeros((matrix.shape[1], matrix.shape[1]), dtype=np.float32)
    weights = np.zeros_like(row_degree, dtype=np.float32)
    weights[active] = 1.0 / (row_degree[active] - 1.0)
    weighted = matrix.multiply(weights[:, None])
    projected = (matrix.T @ weighted).toarray().astype(np.float32)
    np.fill_diagonal(projected, 0.0)
    return projected


def cosine_projection(matrix: sparse.csr_matrix) -> np.ndarray:
    """Co-occurrence cosine similarity projection."""
    co = (matrix.T @ matrix).toarray().astype(np.float32)
    degree = np.diag(co).copy()
    denom = np.sqrt(np.outer(degree, degree))
    with np.errstate(divide="ignore", invalid="ignore"):
        cos = np.divide(co, denom, out=np.zeros_like(co), where=denom > 0)
    np.fill_diagonal(cos, 0.0)
    return cos.astype(np.float32)


def disparity_backbone(weights: np.ndarray, alpha: float = 0.05, mode: str = "or") -> np.ndarray:
    """
    Serrano-Boguñá-Vespignani (PNAS 2009) disparity filter.
    Retains edge (i,j) if its p-value is significant from at least one endpoint (mode='or')
    or from both endpoints (mode='and').
    """
    if mode not in {"or", "and"}:
        raise ValueError("mode must be 'or' or 'and'")
    w = weights.copy().astype(np.float64)
    np.fill_diagonal(w, 0.0)
    degree = (w > 0).sum(axis=1)
    strength = w.sum(axis=1)
    pvals = np.ones_like(w, dtype=np.float64)
    valid = (w > 0) & (strength[:, None] > 0) & (degree[:, None] > 1)
    p = np.divide(w, strength[:, None], out=np.zeros_like(w), where=strength[:, None] > 0)
    exponent = np.broadcast_to((degree - 1)[:, None], w.shape)
    pvals[valid] = np.power(1.0 - p[valid], exponent[valid])
    sig_i = pvals < alpha
    sig_j = sig_i.T
    keep = (sig_i | sig_j) if mode == "or" else (sig_i & sig_j)
    out = np.where(keep, w, 0.0).astype(np.float32)
    np.fill_diagonal(out, 0.0)
    return out


def matrix_to_edges(weights: np.ndarray, game_index: pd.DataFrame, min_weight: float = 0.0) -> pd.DataFrame:
    """Convert the upper triangle of a weight matrix to a tidy edge DataFrame."""
    rows, cols = np.triu_indices_from(weights, k=1)
    vals = weights[rows, cols]
    keep = vals > min_weight
    ordered = game_index.sort_values("col")
    game_ids = ordered["bgg_id"].astype(int).to_numpy()
    names = ordered["name"].astype(str).to_numpy()
    return pd.DataFrame(
        {
            "source": game_ids[rows[keep]],
            "target": game_ids[cols[keep]],
            "source_name": names[rows[keep]],
            "target_name": names[cols[keep]],
            "weight": vals[keep],
        }
    )
