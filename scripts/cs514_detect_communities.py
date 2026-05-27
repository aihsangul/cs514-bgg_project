"""Run Louvain community detection and metadata alignment for CS514 graphs.

Outputs:
  communities/<label>_communities.csv          — node → community assignments
  communities/<label>_community_runs.csv       — per-seed modularity + pairwise NMI
  metadata/<label>_tag_modularity.csv          — binary modularity per mechanic/category
  metadata/<label>_community_tag_enrichment.csv
  gephi/<label>_communities.gexf               — backbone + community as node attribute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.cs514.community import community_output_label, detect_louvain
from bgg_project.cs514.data_io import load_games
from bgg_project.cs514.graph_io import add_game_nodes, attach_communities, read_graph_csv, write_gexf
from bgg_project.cs514.metadata import binary_tag_modularity, community_tag_enrichment
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect communities and compute metadata alignment.")
    parser.add_argument("--graph-label", default="merged_ownership_newman_disparity_a0p001")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--resolution", type=float, default=0.75)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.from_root(PROJECT_ROOT)
    ensure_dirs(paths)

    graph = read_graph_csv(paths.output_dir / "backbones" / f"{args.graph_label}_edges.csv")
    games = load_games(paths)

    add_game_nodes(graph, games)

    assignments, run_stats = detect_louvain(graph, seeds=range(args.seeds), resolution=args.resolution)
    out_label = community_output_label(args.graph_label, args.resolution)
    assignments = assignments.merge(games[["bgg_id", "name", "overall_rank"]], on="bgg_id", how="left")
    assignments.to_csv(paths.output_dir / "communities" / f"{out_label}_communities.csv", index=False)
    run_stats.to_csv(paths.output_dir / "communities" / f"{out_label}_community_runs.csv", index=False)

    tag_modularity = binary_tag_modularity(graph, games)
    tag_modularity.to_csv(paths.output_dir / "metadata" / f"{out_label}_tag_modularity.csv", index=False)

    enrichment = community_tag_enrichment(assignments[["bgg_id", "community"]], games)
    enrichment.to_csv(
        paths.output_dir / "metadata" / f"{out_label}_community_tag_enrichment.csv", index=False
    )

    # Export Gephi file with community as a node attribute
    attach_communities(graph, assignments[["bgg_id", "community"]])
    write_gexf(graph, paths.output_dir / "gephi" / f"{out_label}_communities.gexf")

    median_nmi = run_stats[run_stats.get("level_0", run_stats.columns[0]) == "runs"]["median_pairwise_nmi"].iloc[0] if "median_pairwise_nmi" in run_stats.columns else "n/a"
    print(f"communities detected | median pairwise NMI: {median_nmi}")
    print(f"output label: {out_label}")
    print(f"wrote outputs under {paths.output_dir}")


if __name__ == "__main__":
    main()
