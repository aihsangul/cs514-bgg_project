"""Export CS514 community-level condensation graphs for Gephi.

This script turns the community condensation CSVs into GEXF files with rich
node and edge attributes. Use the full graph for measurement and the top-edge
graph for cleaner ForceAtlas2 visualization.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "data" / "processed" / "cs514_network_analysis"
STRUCTURAL = ANALYSIS / "structural_analysis"
METADATA = ANALYSIS / "metadata"
OUT_DIR = ANALYSIS / "gephi"

COMMUNITY_NODES = STRUCTURAL / "community_condensation_nodes.csv"
COMMUNITY_EDGES = STRUCTURAL / "community_condensation_edges.csv"
COMMUNITY_MAPPING = METADATA / "merged_ownership_newman_disparity_a0p025_r1p75_community_manual_mapping.csv"


TYPE_ORDER = {
    "taste_specialist": 1,
    "taste_cross_over": 2,
    "temporal_canon": 3,
    "temporal_artifact": 4,
    "franchise_series": 5,
    "bridge_cluster": 6,
    "bridge_singleton": 7,
    "shared_culture": 8,
    "tiny_fragment": 9,
}


def _clean_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def build_graph(edge_top_n: int | None = None) -> nx.Graph:
    nodes = pd.read_csv(COMMUNITY_NODES)
    mapping = pd.read_csv(COMMUNITY_MAPPING)
    edges = pd.read_csv(COMMUNITY_EDGES).sort_values("weight", ascending=False).reset_index(drop=True)

    if edge_top_n is not None:
        edges = edges.head(edge_top_n).copy()

    mapping_by_id = mapping.set_index("community")
    graph = nx.Graph()

    for row in nodes.itertuples(index=False):
        community = int(row.community)
        manual = mapping_by_id.loc[community] if community in mapping_by_id.index else None
        community_type = str(row.community_type)
        manual_label = str(row.label)
        include = ""
        meaningfulness = ""
        notes = ""
        if manual is not None:
            manual_label = _clean_value(manual.get("manual_label", manual_label)) or manual_label
            community_type = _clean_value(manual.get("community_type", community_type)) or community_type
            include = _clean_value(manual.get("include_in_user_profiles", ""))
            meaningfulness = _clean_value(manual.get("manual_meaningfulness", ""))
            notes = _clean_value(manual.get("manual_notes", ""))

        graph.add_node(
            str(community),
            label=f"C{community}: {manual_label}",
            community_id=community,
            manual_label=manual_label,
            community_type=community_type,
            community_type_code=TYPE_ORDER.get(community_type, 99),
            include_in_user_profiles=include,
            manual_meaningfulness=meaningfulness,
            manual_notes=notes,
            size=int(row.size),
            internal_weight=float(row.internal_weight),
            external_weight=float(row.external_weight),
            internal_weight_share=float(row.internal_weight_share),
            community_degree=int(row.community_degree),
            community_strength=float(row.community_strength),
        )

    max_weight = float(edges["weight"].max()) if not edges.empty else 1.0
    max_count = float(edges["edge_count"].max()) if not edges.empty else 1.0
    for rank, row in enumerate(edges.itertuples(index=False), start=1):
        source = str(int(row.community_a))
        target = str(int(row.community_b))
        weight = float(row.weight)
        edge_count = int(row.edge_count)
        graph.add_edge(
            source,
            target,
            weight=weight,
            edge_count=edge_count,
            normalized_weight=weight / max_weight if max_weight else 0.0,
            normalized_edge_count=edge_count / max_count if max_count else 0.0,
            edge_rank=rank,
            label=f"C{source}-C{target}",
            source_label=str(row.label_a),
            target_label=str(row.label_b),
        )

    return graph


def write_gexf(graph: nx.Graph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(graph, str(path))


def main() -> None:
    full = build_graph(edge_top_n=None)
    top_120 = build_graph(edge_top_n=120)
    top_80 = build_graph(edge_top_n=80)

    outputs = {
        "cs514_community_condensation_full_alpha0p025_gamma1p75.gexf": full,
        "cs514_community_condensation_top120_alpha0p025_gamma1p75.gexf": top_120,
        "cs514_community_condensation_top80_alpha0p025_gamma1p75.gexf": top_80,
    }
    for name, graph in outputs.items():
        path = OUT_DIR / name
        write_gexf(graph, path)
        print(f"Wrote {path} ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)")


if __name__ == "__main__":
    main()
