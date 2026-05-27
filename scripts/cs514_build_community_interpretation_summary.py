#!/usr/bin/env python3
"""Build a community interpretation summary CSV for a CS514 community run."""
from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-label", default="merged_ownership_newman_disparity_a0p025")
    parser.add_argument("--run-label", default="merged_ownership_newman_disparity_a0p025_r1p75")
    return parser.parse_args()


def split_pipe(value) -> list[str]:
    if pd.isna(value) or value == "":
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / "data" / "processed" / "cs514_network_analysis"
    details_csv = (
        root
        / "data"
        / "processed"
        / "top_ranked_games_details"
        / "top_ranked_games_details_top5000_ranked_only"
        / "top_ranked_games_details.csv"
    )
    selected_games_csv = root / "data" / "processed" / "reliable_users" / "reliable_users_batch1" / "selected_games.csv"

    communities = pd.read_csv(out / "communities" / f"{args.run_label}_communities.csv")
    enrichment = pd.read_csv(out / "metadata" / f"{args.run_label}_community_tag_enrichment.csv")
    edges = pd.read_csv(out / "backbones" / f"{args.graph_label}_edges.csv")

    selected = pd.read_csv(selected_games_csv)
    details = pd.read_csv(details_csv)
    games = details[details["bgg_id"].isin(set(selected["bgg_id"].astype(int)))].copy()
    games["bgg_id"] = games["bgg_id"].astype(int)
    games["mechanics_list"] = games.get("mechanics", pd.Series(index=games.index, dtype=str)).map(split_pipe)
    games["categories_list"] = games.get("categories", pd.Series(index=games.index, dtype=str)).map(split_pipe)
    comm_games = communities.merge(games, on="bgg_id", how="left", suffixes=("", "_detail"))

    size_df = (
        communities.groupby("community")
        .size()
        .rename("size")
        .reset_index()
        .sort_values("size", ascending=False)
    )

    def top_enriched_tags(community_id: int, kind: str, n: int = 5, min_observed: int = 2) -> pd.DataFrame:
        df = enrichment[(enrichment["community"].astype(int) == int(community_id)) & (enrichment["tag_kind"] == kind)].copy()
        df = df[df["observed"] >= min_observed]
        return df.sort_values(["p_value", "fold_enrichment"], ascending=[True, False]).head(n)

    def join_top_tags(community_id: int, kind: str, n: int = 5) -> str:
        df = top_enriched_tags(community_id, kind=kind, n=n)
        return "; ".join(f"{r.tag} ({int(r.observed)}, {float(r.fold_enrichment):.1f}x)" for r in df.itertuples())

    def top_games_by_rank(community_id: int, n: int = 8) -> pd.DataFrame:
        cols = ["bgg_id", "name", "overall_rank"]
        if "average_weight" in comm_games.columns:
            cols.append("average_weight")
        if "year_published" in comm_games.columns:
            cols.append("year_published")
        return (
            comm_games[comm_games["community"] == community_id]
            .sort_values("overall_rank")
            [cols]
            .head(n)
        )

    def join_top_games(community_id: int, n: int = 8) -> str:
        df = top_games_by_rank(community_id, n=n)
        return "; ".join(f"{r.name} (#{int(r.overall_rank)})" for r in df.itertuples())

    graph = nx.Graph()
    graph.add_nodes_from(communities["bgg_id"].astype(int))
    for row in edges.itertuples(index=False):
        graph.add_edge(int(row.source), int(row.target), weight=float(row.weight))

    community_map = dict(zip(communities["bgg_id"].astype(int), communities["community"].astype(int), strict=False))
    weighted_degree = dict(graph.degree(weight="weight"))
    degree = dict(graph.degree())

    def community_graph_stats(community_id: int) -> dict:
        nodes = [node for node, cid in community_map.items() if cid == community_id]
        sub = graph.subgraph(nodes)
        internal_weight = sum(d.get("weight", 1.0) for _, _, d in sub.edges(data=True))
        total_incident_weight = sum(weighted_degree.get(node, 0.0) for node in nodes)
        return {
            "community": community_id,
            "internal_edges": sub.number_of_edges(),
            "internal_density": nx.density(sub) if len(nodes) > 1 else 0.0,
            "internal_weight": internal_weight,
            "internal_weight_share": (2 * internal_weight / total_incident_weight) if total_incident_weight else np.nan,
            "avg_degree_global": np.mean([degree.get(node, 0) for node in nodes]) if nodes else np.nan,
            "avg_weighted_degree_global": np.mean([weighted_degree.get(node, 0.0) for node in nodes]) if nodes else np.nan,
        }

    def join_central_games(community_id: int, n: int = 6) -> str:
        nodes = [node for node, cid in community_map.items() if cid == community_id]
        sub = graph.subgraph(nodes)
        centrality = dict(sub.degree(weight="weight"))
        central = (
            pd.DataFrame({"bgg_id": list(centrality.keys()), "internal_weighted_degree": list(centrality.values())})
            .merge(comm_games[["bgg_id", "name", "overall_rank"]], on="bgg_id", how="left")
            .sort_values(["internal_weighted_degree", "overall_rank"], ascending=[False, True])
            .head(n)
        )
        return "; ".join(f"{r.name} ({float(r.internal_weighted_degree):.1f})" for r in central.itertuples())

    enrichment_counts = (
        enrichment[enrichment["p_value"] <= 0.001]
        .groupby(["community", "tag_kind"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    enrichment_counts.columns.name = None
    for col in ["mechanic", "category"]:
        if col not in enrichment_counts:
            enrichment_counts[col] = 0

    rows = []
    for cid in sorted(communities["community"].unique()):
        group = comm_games[comm_games["community"] == cid]
        row = {
            "community": int(cid),
            "size": int(len(group)),
            "manual_label": "",
            "community_type": "",
            "include_in_user_profiles": "",
            "manual_meaningfulness": "",
            "manual_notes": "",
            "top_categories": join_top_tags(cid, "category", n=5),
            "top_mechanics": join_top_tags(cid, "mechanic", n=5),
            "median_rank": float(group["overall_rank"].median()),
            "top_games_by_rank": join_top_games(cid, n=8),
            "central_games": join_central_games(cid, n=6),
        }
        if "average_weight" in group.columns:
            row["median_weight"] = float(group["average_weight"].median())
        if "year_published" in group.columns:
            row["median_year"] = float(group["year_published"].median())
        rows.append(row)

    summary = pd.DataFrame(rows)
    summary = summary.merge(pd.DataFrame([community_graph_stats(int(cid)) for cid in communities["community"].unique()]), on="community")
    summary = summary.merge(enrichment_counts[["community", "category", "mechanic"]], on="community", how="left")
    summary[["category", "mechanic"]] = summary[["category", "mechanic"]].fillna(0).astype(int)
    summary = summary.rename(
        columns={
            "category": "n_strong_category_enrichments_p001",
            "mechanic": "n_strong_mechanic_enrichments_p001",
        }
    )

    def rough_flag(row: pd.Series) -> str:
        strong_tags = row["n_strong_category_enrichments_p001"] + row["n_strong_mechanic_enrichments_p001"]
        if row["size"] >= 20 and strong_tags >= 3:
            return "high_candidate"
        if row["size"] >= 10 and strong_tags >= 1:
            return "medium_candidate"
        if row["size"] < 6:
            return "tiny_fragment"
        return "needs_manual_review"

    summary["rough_meaningfulness_flag"] = summary.apply(rough_flag, axis=1)
    summary = summary.sort_values(["size", "community"], ascending=[False, True])

    out_path = out / "metadata" / f"{args.run_label}_community_interpretation_summary.csv"
    summary.to_csv(out_path, index=False)
    print(f"wrote {out_path}")
    print(summary[["community", "size", "rough_meaningfulness_flag", "top_categories", "top_mechanics"]].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
