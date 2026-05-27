"""NetworkX graph construction, CSV serialisation, and Gephi GEXF export."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


def graph_from_matrix(weights: np.ndarray, game_index: pd.DataFrame) -> nx.Graph:
    """
    Build a NetworkX Graph from a dense weight matrix.
    Nodes carry 'name' and 'overall_rank' attributes from game_index.
    """
    ordered = game_index.sort_values("col")
    id_by_col = ordered["bgg_id"].astype(int).to_list()
    name_by_col = ordered["name"].astype(str).to_list()
    rank_by_col = ordered["overall_rank"].astype(int).to_list()

    graph = nx.Graph()
    for gid, name, rank in zip(id_by_col, name_by_col, rank_by_col, strict=False):
        graph.add_node(gid, label=name, overall_rank=rank)

    rows, cols = np.triu_indices_from(weights, k=1)
    vals = weights[rows, cols]
    for i, j, weight in zip(rows[vals > 0], cols[vals > 0], vals[vals > 0], strict=False):
        graph.add_edge(id_by_col[i], id_by_col[j], weight=float(weight))
    return graph


def read_graph_csv(path: Path) -> nx.Graph:
    """Load a graph from an edge-list CSV produced by write_graph_edges."""
    edges = pd.read_csv(path)
    graph = nx.Graph()
    for row in edges.itertuples(index=False):
        graph.add_edge(int(row.source), int(row.target), weight=float(row.weight))
    return graph


def add_game_nodes(graph: nx.Graph, games: pd.DataFrame) -> nx.Graph:
    """
    Ensure every selected game is present, including isolate nodes.

    Edge-list CSVs only store edges, so reading a strict backbone back from disk
    otherwise drops games with degree zero.
    """
    for row in games.itertuples(index=False):
        gid = int(row.bgg_id)
        graph.add_node(
            gid,
            label=str(row.name),
            overall_rank=int(row.overall_rank),
        )
    return graph


def write_graph_edges(graph: nx.Graph, path: Path) -> None:
    """Write edges to a CSV with columns: source, target, weight."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["source", "target", "weight"])
        writer.writeheader()
        for u, v, data in graph.edges(data=True):
            writer.writerow({"source": u, "target": v, "weight": data.get("weight", 1.0)})


def write_gexf(graph: nx.Graph, path: Path) -> None:
    """
    Export the graph to GEXF format for Gephi.

    Node attributes already set on the graph (label, overall_rank, community, …)
    are preserved. Integer node IDs are used as-is; Gephi displays the 'label'
    attribute as the node name in the canvas.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # NetworkX write_gexf requires string node IDs for full compatibility.
    G = nx.relabel_nodes(graph, {n: str(n) for n in graph.nodes()})
    nx.write_gexf(G, str(path))


def attach_communities(graph: nx.Graph, assignments: pd.DataFrame) -> nx.Graph:
    """
    Copy community assignments onto graph node attributes in-place.
    *assignments* must have columns 'bgg_id' and 'community'.
    Returns the same graph (mutated).
    """
    comm_map = dict(zip(assignments["bgg_id"].astype(int), assignments["community"].astype(int), strict=False))
    for node in graph.nodes():
        graph.nodes[node]["community"] = comm_map.get(int(node), -1)
    return graph


def graph_diagnostics(graph: nx.Graph, label: str) -> dict:
    n = graph.number_of_nodes()
    m = graph.number_of_edges()
    degrees = np.array([d for _, d in graph.degree()], dtype=float)
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    giant_size = len(components[0]) if components else 0
    return {
        "label": label,
        "nodes": n,
        "edges": m,
        "isolates": int((degrees == 0).sum()),
        "non_isolate_nodes": int((degrees > 0).sum()),
        "giant_component_nodes": giant_size,
        "giant_component_fraction": giant_size / n if n else 0.0,
        "density": nx.density(graph) if n > 1 else 0.0,
        "average_degree": float(degrees.mean()) if degrees.size else 0.0,
        "median_degree": float(np.median(degrees)) if degrees.size else 0.0,
        "max_degree": float(degrees.max()) if degrees.size else 0.0,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
