"""Project CS514 incidence matrices and build disparity-filtered backbones.

Outputs per label × alpha:
  backbones/<label>_newman_disparity_a<alpha>_edges.csv   — edge list for programmatic use
  gephi/<label>_newman_disparity_a<alpha>.gexf            — annotated graph for Gephi
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

from bgg_project.cs514.graph_io import graph_diagnostics, graph_from_matrix, write_gexf, write_graph_edges
from bgg_project.cs514.incidence import load_incidence
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs
from bgg_project.cs514.projection import disparity_backbone, matrix_to_edges, newman_projection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Newman projections and disparity backbones.")
    parser.add_argument("--labels", nargs="+", default=["merged_ownership"])
    parser.add_argument("--alphas", nargs="+", type=float, default=[0.05])
    parser.add_argument("--write-full-projection", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.from_root(PROJECT_ROOT)
    ensure_dirs(paths)
    diagnostics = []

    for label in args.labels:
        print(f"projecting {label}")
        matrix, _, game_index = load_incidence(paths.output_dir / "incidence" / label)
        projection = newman_projection(matrix)

        if args.write_full_projection:
            matrix_to_edges(projection, game_index).to_csv(
                paths.output_dir / "projections" / f"{label}_newman_edges.csv",
                index=False,
            )

        for alpha in args.alphas:
            alpha_label = str(alpha).replace(".", "p")
            print(f"  applying disparity filter alpha={alpha}")
            backbone = disparity_backbone(projection, alpha=alpha, mode="or")
            graph = graph_from_matrix(backbone, game_index)
            out_label = f"{label}_newman_disparity_a{alpha_label}"

            write_graph_edges(graph, paths.output_dir / "backbones" / f"{out_label}_edges.csv")
            write_gexf(graph, paths.output_dir / "gephi" / f"{out_label}.gexf")
            diagnostics.append(graph_diagnostics(graph, out_label))
            print(f"  -> {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    diagnostics_path = paths.output_dir / "diagnostics" / "backbone_diagnostics.csv"
    new_diagnostics = pd.DataFrame(diagnostics)
    if diagnostics_path.exists() and not new_diagnostics.empty:
        old_diagnostics = pd.read_csv(diagnostics_path)
        old_diagnostics = old_diagnostics[
            ~old_diagnostics["label"].isin(new_diagnostics["label"])
        ]
        new_diagnostics = pd.concat([old_diagnostics, new_diagnostics], ignore_index=True)
    new_diagnostics.to_csv(diagnostics_path, index=False)
    print(f"wrote outputs under {paths.output_dir}")


if __name__ == "__main__":
    main()
