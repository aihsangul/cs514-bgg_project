#!/usr/bin/env python3
"""
Sweep disparity alpha and Louvain resolution for the CS514 headline graph.

The goal is parameter selection, not final reporting. The script records graph
size, isolate count, community granularity, modularity, seed stability, and a
lightweight metadata-coherence summary for each alpha/resolution pair.

Default output:
    data/processed/cs514_network_analysis/diagnostics/parameter_sweep.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ALPHAS = [0.001, 0.005, 0.01, 0.025, 0.05]
DEFAULT_RESOLUTIONS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def alpha_label(alpha: float) -> str:
    return str(alpha).replace(".", "p")


def parse_float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CS514 parameter sweep over disparity alpha and Louvain resolution."
    )
    parser.add_argument(
        "--label",
        default="merged_ownership",
        help="Incidence label to project, e.g. merged_ownership.",
    )
    parser.add_argument(
        "--alphas",
        type=parse_float_list,
        default=DEFAULT_ALPHAS,
        help="Comma-separated disparity alpha values.",
    )
    parser.add_argument(
        "--resolutions",
        type=parse_float_list,
        default=DEFAULT_RESOLUTIONS,
        help="Comma-separated Louvain resolution values.",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=10,
        help="Number of Louvain seeds per setting. Use 20 for final confirmation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output CSV path.",
    )
    return parser.parse_args()


def summarize_run_stats(run_stats: pd.DataFrame) -> dict:
    runs = run_stats[run_stats["level_0"] == "runs"].copy()
    pairwise = run_stats[run_stats["level_0"] == "pairwise"].copy()

    representative = runs[runs["representative"] == True]  # noqa: E712
    if representative.empty:
        representative = runs.sort_values("modularity", ascending=False).head(1)

    return {
        "representative_seed": int(representative["seed"].iloc[0]),
        "representative_modularity": float(representative["modularity"].iloc[0]),
        "representative_n_communities": int(representative["n_communities"].iloc[0]),
        "median_seed_modularity": float(runs["modularity"].median()),
        "median_seed_n_communities": float(runs["n_communities"].median()),
        "median_pairwise_nmi": float(pairwise["nmi"].median()) if not pairwise.empty else np.nan,
    }


def summarize_partition(assignments: pd.DataFrame, n_nodes: int) -> dict:
    sizes = assignments["community"].value_counts()
    return {
        "n_communities": int(sizes.size),
        "largest_community_size": int(sizes.max()) if not sizes.empty else 0,
        "largest_community_fraction": float(sizes.max() / n_nodes) if n_nodes and not sizes.empty else np.nan,
        "singleton_communities": int((sizes == 1).sum()) if not sizes.empty else 0,
    }


def summarize_tag_modularity(tag_modularity: pd.DataFrame) -> dict:
    if tag_modularity.empty:
        return {
            "max_tag_modularity": np.nan,
            "mean_top10_tag_modularity": np.nan,
            "positive_tag_modularity_count": 0,
        }
    top10 = tag_modularity.head(10)
    return {
        "max_tag_modularity": float(tag_modularity["binary_modularity"].max()),
        "mean_top10_tag_modularity": float(top10["binary_modularity"].mean()),
        "positive_tag_modularity_count": int((tag_modularity["binary_modularity"] > 0).sum()),
    }


def main() -> None:
    args = parse_args()

    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from bgg_project.cs514.community import detect_louvain
    from bgg_project.cs514.data_io import load_games
    from bgg_project.cs514.graph_io import graph_diagnostics, graph_from_matrix
    from bgg_project.cs514.incidence import load_incidence
    from bgg_project.cs514.metadata import binary_tag_modularity
    from bgg_project.cs514.paths import ProjectPaths, ensure_dirs
    from bgg_project.cs514.projection import disparity_backbone, newman_projection

    paths = ProjectPaths.from_root(project_root)
    ensure_dirs(paths)

    output = args.output or (paths.output_dir / "diagnostics" / "parameter_sweep.csv")
    output.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CS514 PARAMETER SWEEP")
    print("=" * 72)
    print(f"label:       {args.label}")
    print(f"alphas:      {args.alphas}")
    print(f"resolutions: {args.resolutions}")
    print(f"seeds:       {args.seeds}")
    print(f"output:      {output}")
    print("=" * 72)

    matrix, _, game_index = load_incidence(paths.output_dir / "incidence" / args.label)
    games = load_games(paths)

    print("Building Newman projection once ...", end=" ", flush=True)
    t0 = time.perf_counter()
    projection = newman_projection(matrix)
    print(f"done in {time.perf_counter() - t0:.1f}s")

    rows: list[dict] = []
    for alpha in args.alphas:
        label = f"{args.label}_newman_disparity_a{alpha_label(alpha)}"
        print(f"\nalpha={alpha} ({label})")
        t_alpha = time.perf_counter()
        backbone = disparity_backbone(projection, alpha=alpha, mode="or")
        graph = graph_from_matrix(backbone, game_index)
        gdiag = graph_diagnostics(graph, label)
        tag_summary = summarize_tag_modularity(binary_tag_modularity(graph, games))
        print(
            "  graph: "
            f"edges={gdiag['edges']:,} isolates={gdiag['isolates']} "
            f"giant={gdiag['giant_component_fraction']:.1%}"
        )

        for resolution in args.resolutions:
            print(f"  resolution={resolution} ...", end=" ", flush=True)
            t_res = time.perf_counter()
            assignments, run_stats = detect_louvain(
                graph,
                seeds=range(args.seeds),
                resolution=resolution,
            )
            run_summary = summarize_run_stats(run_stats)
            part_summary = summarize_partition(assignments, graph.number_of_nodes())
            stability_pass = run_summary["median_pairwise_nmi"] >= 0.70
            largest_ok = part_summary["largest_community_fraction"] <= 0.75

            rows.append(
                {
                    "label": label,
                    "alpha": alpha,
                    "resolution": resolution,
                    "n_seeds": args.seeds,
                    **gdiag,
                    **run_summary,
                    **part_summary,
                    **tag_summary,
                    "stability_pass_nmi_0p70": bool(stability_pass),
                    "largest_community_le_75pct": bool(largest_ok),
                    "elapsed_seconds": round(time.perf_counter() - t_res, 3),
                }
            )
            print(
                f"Q={run_summary['representative_modularity']:.3f} "
                f"k={part_summary['n_communities']} "
                f"largest={part_summary['largest_community_fraction']:.1%} "
                f"NMI={run_summary['median_pairwise_nmi']:.3f}"
            )

        print(f"  alpha block done in {time.perf_counter() - t_alpha:.1f}s")
        pd.DataFrame(rows).to_csv(output, index=False)

    print("\n" + "=" * 72)
    print(f"Sweep complete: {output}")
    print("Use settings that are stable, not too dense, and not dominated by one giant community.")
    print("=" * 72)


if __name__ == "__main__":
    main()
