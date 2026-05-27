"""Degree-preserving null-model modularity test."""
from __future__ import annotations

import random
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RewireResult:
    graph: nx.Graph
    requested_swaps: int
    swaps_per_edge: float


def _degree_preserving_rewire(
    graph: nx.Graph,
    rng: random.Random,
    swaps_per_edge: int,
) -> RewireResult:
    """
    Return a successfully rewired copy of *graph*.

    NetworkX mutates during failed swap attempts, so failed candidates are
    discarded. This prevents silently accepting a barely rewired null graph.
    """
    m = graph.number_of_edges()
    for factor in [swaps_per_edge, 2, 1]:
        nswap = max(1, int(factor * m))
        candidate = graph.copy()
        try:
            nx.double_edge_swap(
                candidate,
                nswap=nswap,
                max_tries=max(nswap * 50, 1000),
                seed=rng.randint(0, 10**9),
            )
            return RewireResult(candidate, requested_swaps=nswap, swaps_per_edge=float(factor))
        except nx.NetworkXAlgorithmError:
            continue
    raise RuntimeError(
        "Could not generate a complete degree-preserving null graph. "
        "Try lowering swaps_per_edge or using a less fragmented backbone."
    )


def degree_preserving_null_modularity(
    graph: nx.Graph,
    n_replicates: int = 20,
    seed: int = 123,
    swaps_per_edge: int = 5,
    resolution: float = 1.0,
) -> pd.DataFrame:
    """
    Compare observed Louvain modularity against a degree-preserving null.

    For each replicate:
      1. Double-edge-swap the topology to randomise wiring while preserving degrees.
      2. Shuffle the original edge weights uniformly at random.
      3. Run Louvain and record modularity.

    Returns a DataFrame with columns: replicate, modularity, n_communities.
    The observed values appear in the row where replicate == 'observed'.
    Summary statistics (z_score, null_mean, …) are stored in DataFrame.attrs.
    """
    rng = random.Random(seed)
    observed_communities = nx.algorithms.community.louvain_communities(
        graph, weight="weight", seed=seed, resolution=resolution
    )
    observed_q = nx.algorithms.community.modularity(
        graph, observed_communities, weight="weight", resolution=resolution
    )
    observed_weights = [data.get("weight", 1.0) for _, _, data in graph.edges(data=True)]

    rows = [
        {
            "replicate": "observed",
            "modularity": observed_q,
            "n_communities": len(observed_communities),
            "requested_swaps": 0,
            "swaps_per_edge": 0.0,
        }
    ]

    for rep in range(n_replicates):
        rewire = _degree_preserving_rewire(graph, rng, swaps_per_edge)
        g_null = rewire.graph
        shuffled = observed_weights[:]
        rng.shuffle(shuffled)
        for (u, v), weight in zip(g_null.edges(), shuffled, strict=False):
            g_null[u][v]["weight"] = weight
        communities = nx.algorithms.community.louvain_communities(
            g_null, weight="weight", seed=rng.randint(0, 10**9), resolution=resolution
        )
        q = nx.algorithms.community.modularity(
            g_null, communities, weight="weight", resolution=resolution
        )
        rows.append(
            {
                "replicate": rep,
                "modularity": q,
                "n_communities": len(communities),
                "requested_swaps": rewire.requested_swaps,
                "swaps_per_edge": rewire.swaps_per_edge,
            }
        )

    out = pd.DataFrame(rows)
    null = out[out["replicate"] != "observed"]["modularity"]
    if len(null):
        null_mean = float(null.mean())
        null_std = float(null.std(ddof=1))
        out.attrs["observed_q"] = observed_q
        out.attrs["null_mean"] = null_mean
        out.attrs["null_std"] = null_std
        out.attrs["z_score"] = float((observed_q - null_mean) / null_std) if null_std else np.nan
    return out
