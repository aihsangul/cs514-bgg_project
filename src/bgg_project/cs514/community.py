"""Louvain community detection with multi-seed stability measurement."""
from __future__ import annotations

from typing import Iterable

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.metrics import normalized_mutual_info_score


def resolution_label(resolution: float) -> str:
    """Return a filename-safe label for a Louvain/Leiden resolution value."""
    return str(float(resolution)).replace(".", "p")


def community_output_label(graph_label: str, resolution: float) -> str:
    """Combine backbone label and resolution so variants cannot overwrite."""
    return f"{graph_label}_r{resolution_label(resolution)}"


def detect_louvain(
    graph: nx.Graph,
    seeds: Iterable[int],
    resolution: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run Louvain at multiple seeds and return the best partition plus run statistics.

    Returns
    -------
    assignments : DataFrame with columns bgg_id, community
        The partition from the seed that achieved the highest modularity.
    run_stats : DataFrame
        Per-seed modularity + community count, plus pairwise NMI stability rows.
    """
    seed_list = list(seeds)
    node_order = list(graph.nodes())
    partitions: list[dict[int, int]] = []
    run_rows = []

    for seed in seed_list:
        communities = nx.algorithms.community.louvain_communities(
            graph, weight="weight", resolution=resolution, seed=seed
        )
        assignment: dict[int, int] = {}
        for cid, community in enumerate(communities):
            for node in community:
                assignment[int(node)] = cid
        modularity = nx.algorithms.community.modularity(
            graph, communities, weight="weight", resolution=resolution
        )
        run_rows.append({"seed": seed, "n_communities": len(communities), "modularity": modularity})
        partitions.append(assignment)

    stability_rows = []
    for i in range(len(partitions)):
        for j in range(i + 1, len(partitions)):
            labels_i = [partitions[i][n] for n in node_order]
            labels_j = [partitions[j][n] for n in node_order]
            stability_rows.append(
                {
                    "seed_i": seed_list[i],
                    "seed_j": seed_list[j],
                    "nmi": normalized_mutual_info_score(labels_i, labels_j),
                }
            )

    best_idx = int(np.argmax([r["modularity"] for r in run_rows]))
    best = partitions[best_idx]
    assignments = pd.DataFrame({"bgg_id": node_order, "community": [best[n] for n in node_order]})

    run_stats = pd.DataFrame(run_rows)
    run_stats["representative"] = False
    run_stats.loc[best_idx, "representative"] = True
    stability = pd.DataFrame(stability_rows)
    if not stability.empty:
        run_stats["median_pairwise_nmi"] = float(stability["nmi"].median())
    combined = pd.concat([run_stats, stability], keys=["runs", "pairwise"]).reset_index()
    return assignments, combined
