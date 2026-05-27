"""Per-tag modularity contribution and community hypergeometric enrichment."""
from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import hypergeom


def tag_sets(games: pd.DataFrame, tag_kind: str) -> dict[str, set[int]]:
    """Return a mapping of tag → set of bgg_ids that carry it."""
    col = "mechanics_list" if tag_kind == "mechanic" else "categories_list"
    out: dict[str, set[int]] = defaultdict(set)
    for row in games.itertuples(index=False):
        gid = int(getattr(row, "bgg_id"))
        for tag in getattr(row, col):
            out[tag].add(gid)
    return dict(out)


def binary_tag_modularity(graph: nx.Graph, games: pd.DataFrame, min_games: int = 3) -> pd.DataFrame:
    """
    Treat each mechanic/category as a binary partition (games with tag vs. without)
    and compute its modularity contribution against the graph.
    Higher values indicate the tag aligns with the network's community structure.
    """
    all_nodes = set(graph.nodes())
    rows = []
    for kind in ["mechanic", "category"]:
        for tag, nodes in tag_sets(games, kind).items():
            nodes = nodes & all_nodes
            if len(nodes) < min_games or len(nodes) == len(all_nodes):
                continue
            other = all_nodes - nodes
            q = nx.algorithms.community.modularity(graph, [nodes, other], weight="weight")
            rows.append({"tag_kind": kind, "tag": tag, "n_games": len(nodes), "binary_modularity": q})
    return pd.DataFrame(rows).sort_values("binary_modularity", ascending=False)


def community_tag_enrichment(
    assignments: pd.DataFrame,
    games: pd.DataFrame,
    min_games_in_community: int = 2,
) -> pd.DataFrame:
    """
    Hypergeometric enrichment test for every (community, tag) pair.
    Returns p-values and fold-enrichment; rows are sorted by community then p-value.
    """
    game_tags = games[["bgg_id", "mechanics_list", "categories_list"]].copy()
    merged = assignments.merge(game_tags, on="bgg_id", how="left")
    n_total = len(merged)
    rows = []

    for kind, col in [("mechanic", "mechanics_list"), ("category", "categories_list")]:
        all_tags: Counter = Counter(tag for tags in merged[col] for tag in tags)
        for community, group in merged.groupby("community"):
            n_comm = len(group)
            observed: Counter = Counter(tag for tags in group[col] for tag in tags)
            for tag, x in observed.items():
                if x < min_games_in_community:
                    continue
                K = all_tags[tag]
                p = hypergeom.sf(x - 1, n_total, K, n_comm)
                expected = n_comm * K / n_total if K else np.nan
                rows.append(
                    {
                        "community": community,
                        "tag_kind": kind,
                        "tag": tag,
                        "observed": x,
                        "community_size": n_comm,
                        "tag_total": K,
                        "expected": expected,
                        "fold_enrichment": x / expected if expected and not np.isnan(expected) else np.nan,
                        "p_value": p,
                    }
                )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["rank_in_community_kind"] = result.groupby(["community", "tag_kind"])["p_value"].rank(method="first")
    return result.sort_values(["community", "tag_kind", "p_value"])
