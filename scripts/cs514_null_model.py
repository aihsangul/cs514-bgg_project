"""Degree-preserving null-model modularity test for a CS514 backbone graph."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.cs514.data_io import load_games
from bgg_project.cs514.graph_io import add_game_nodes, read_graph_csv, write_json
from bgg_project.cs514.null_model import degree_preserving_null_modularity
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run null-model modularity test.")
    parser.add_argument("--graph-label", default="merged_ownership_newman_disparity_a0p05")
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--swaps-per-edge", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.from_root(PROJECT_ROOT)
    ensure_dirs(paths)

    graph = read_graph_csv(paths.output_dir / "backbones" / f"{args.graph_label}_edges.csv")
    add_game_nodes(graph, load_games(paths))
    result = degree_preserving_null_modularity(
        graph,
        n_replicates=args.replicates,
        seed=args.seed,
        swaps_per_edge=args.swaps_per_edge,
        resolution=args.resolution,
    )

    resolution_label = str(float(args.resolution)).replace(".", "p")
    out_label = f"{args.graph_label}_r{resolution_label}"
    out_csv = paths.output_dir / "diagnostics" / f"{out_label}_null_modularity.csv"
    result.to_csv(out_csv, index=False)

    null = result[result["replicate"] != "observed"]["modularity"]
    observed = float(result[result["replicate"] == "observed"]["modularity"].iloc[0])
    summary = {
        "observed_modularity": observed,
        "null_mean": float(null.mean()) if len(null) else None,
        "null_std": float(null.std(ddof=1)) if len(null) > 1 else None,
        "z_score": result.attrs.get("z_score"),
        "replicates": int(len(null)),
        "resolution": float(args.resolution),
        "swaps_per_edge": int(args.swaps_per_edge),
    }
    write_json(paths.output_dir / "diagnostics" / f"{out_label}_null_modularity_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
