#!/usr/bin/env python3
"""
Targeted gamma + null-model sweep on an existing CS514 backbone graph.

This is intended to find a validated midline setting between:
  - statistically strong but coarse macro communities
  - semantically rich but null-failing high-resolution communities

Default target:
  graph-label = merged_ownership_newman_disparity_a0p025
  gamma       = 0.75, 1.0, 1.25, 1.5, 1.75, 2.0
  seeds       = 20
  null reps   = 20

Outputs:
  diagnostics/<graph_label>_midline_gamma_null_sweep.csv
  diagnostics/<graph_label>_midline_gamma_null_replicates.csv
  communities/<graph_label>_r<gamma>_communities.csv
  communities/<graph_label>_r<gamma>_community_runs.csv
  metadata/<graph_label>_r<gamma>_community_tag_enrichment.csv
  metadata/<graph_label>_r<gamma>_tag_modularity.csv
  gephi/<graph_label>_r<gamma>_communities.gexf
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


DEFAULT_GAMMAS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def parse_float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-label", default="merged_ownership_newman_disparity_a0p025")
    parser.add_argument("--gammas", type=parse_float_list, default=DEFAULT_GAMMAS)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--null-replicates", type=int, default=20)
    parser.add_argument("--swaps-per-edge", type=int, default=1)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--no-community-outputs",
        action="store_true",
        help="Only write sweep diagnostics, not per-gamma community/enrichment/Gephi files.",
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
        "observed_modularity": float(representative["modularity"].iloc[0]),
        "observed_n_communities": int(representative["n_communities"].iloc[0]),
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
        "median_community_size": float(sizes.median()) if not sizes.empty else np.nan,
        "communities_ge_20_games": int((sizes >= 20).sum()) if not sizes.empty else 0,
        "communities_ge_50_games": int((sizes >= 50).sum()) if not sizes.empty else 0,
        "singleton_communities": int((sizes == 1).sum()) if not sizes.empty else 0,
    }


def summarize_enrichment(enrichment: pd.DataFrame, assignments: pd.DataFrame) -> dict:
    if enrichment.empty:
        return {
            "strong_enrichment_rows_p001": 0,
            "communities_with_strong_enrichment_p001": 0,
            "large_communities_with_strong_enrichment_p001": 0,
            "mean_best_neglog10_p_large_communities": np.nan,
            "median_best_fold_enrichment_large_communities": np.nan,
        }

    sizes = assignments["community"].value_counts().rename("community_size_check")
    best = (
        enrichment.sort_values("p_value")
        .groupby("community", as_index=False)
        .first()
        .merge(sizes, left_on="community", right_index=True, how="left")
    )
    large_best = best[best["community_size_check"] >= 20].copy()
    strong = enrichment[enrichment["p_value"] <= 0.001]
    strong_communities = set(strong["community"].astype(int))
    large_communities = set(sizes[sizes >= 20].index.astype(int))

    if not large_best.empty:
        best_p = large_best["p_value"].clip(lower=1e-300)
        mean_neglog = float((-np.log10(best_p)).mean())
        median_fold = float(large_best["fold_enrichment"].median())
    else:
        mean_neglog = np.nan
        median_fold = np.nan

    return {
        "strong_enrichment_rows_p001": int(len(strong)),
        "communities_with_strong_enrichment_p001": int(len(strong_communities)),
        "large_communities_with_strong_enrichment_p001": int(len(strong_communities & large_communities)),
        "mean_best_neglog10_p_large_communities": mean_neglog,
        "median_best_fold_enrichment_large_communities": median_fold,
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


def evaluate_null_graphs(
    graph: nx.Graph,
    gammas: list[float],
    n_replicates: int,
    swaps_per_edge: int,
    seed: int,
) -> pd.DataFrame:
    from bgg_project.cs514.null_model import _degree_preserving_rewire

    rng = random.Random(seed)
    observed_weights = [data.get("weight", 1.0) for _, _, data in graph.edges(data=True)]
    rows = []

    for rep in range(n_replicates):
        t0 = time.perf_counter()
        rewire = _degree_preserving_rewire(graph, rng, swaps_per_edge)
        g_null = rewire.graph
        shuffled = observed_weights[:]
        rng.shuffle(shuffled)
        for (u, v), weight in zip(g_null.edges(), shuffled, strict=False):
            g_null[u][v]["weight"] = weight

        for gamma in gammas:
            communities = nx.algorithms.community.louvain_communities(
                g_null,
                weight="weight",
                seed=rng.randint(0, 10**9),
                resolution=gamma,
            )
            q = nx.algorithms.community.modularity(
                g_null,
                communities,
                weight="weight",
                resolution=gamma,
            )
            rows.append(
                {
                    "replicate": rep,
                    "gamma": gamma,
                    "null_modularity": q,
                    "null_n_communities": len(communities),
                    "requested_swaps": rewire.requested_swaps,
                    "swaps_per_edge": rewire.swaps_per_edge,
                    "replicate_elapsed_seconds": round(time.perf_counter() - t0, 3),
                }
            )
        print(f"  null replicate {rep + 1}/{n_replicates} complete")

    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()

    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from bgg_project.cs514.community import community_output_label, detect_louvain
    from bgg_project.cs514.data_io import load_games
    from bgg_project.cs514.graph_io import add_game_nodes, attach_communities, graph_diagnostics, read_graph_csv, write_gexf
    from bgg_project.cs514.metadata import binary_tag_modularity, community_tag_enrichment
    from bgg_project.cs514.paths import ProjectPaths, ensure_dirs

    paths = ProjectPaths.from_root(project_root)
    ensure_dirs(paths)

    graph_path = paths.output_dir / "backbones" / f"{args.graph_label}_edges.csv"
    graph = read_graph_csv(graph_path)
    games = load_games(paths)
    add_game_nodes(graph, games)
    gdiag = graph_diagnostics(graph, args.graph_label)

    print("=" * 72)
    print("CS514 MIDLINE GAMMA + NULL SWEEP")
    print("=" * 72)
    print(f"graph:          {args.graph_label}")
    print(f"gammas:         {args.gammas}")
    print(f"seeds:          {args.seeds}")
    print(f"null reps:      {args.null_replicates}")
    print(f"swaps/edge:     {args.swaps_per_edge}")
    print(f"graph edges:    {gdiag['edges']:,}")
    print("=" * 72)

    observed_rows = []
    for gamma in args.gammas:
        out_label = community_output_label(args.graph_label, gamma)
        print(f"\nobserved gamma={gamma} ({out_label})")
        t0 = time.perf_counter()
        assignments, run_stats = detect_louvain(
            graph,
            seeds=range(args.seeds),
            resolution=gamma,
        )
        run_summary = summarize_run_stats(run_stats)
        part_summary = summarize_partition(assignments, graph.number_of_nodes())

        assignments = assignments.merge(games[["bgg_id", "name", "overall_rank"]], on="bgg_id", how="left")
        enrichment = community_tag_enrichment(assignments[["bgg_id", "community"]], games)
        tag_modularity = binary_tag_modularity(graph, games)
        enrichment_summary = summarize_enrichment(enrichment, assignments)
        tag_mod_summary = summarize_tag_modularity(tag_modularity)

        if not args.no_community_outputs:
            assignments.to_csv(paths.output_dir / "communities" / f"{out_label}_communities.csv", index=False)
            run_stats.to_csv(paths.output_dir / "communities" / f"{out_label}_community_runs.csv", index=False)
            enrichment.to_csv(paths.output_dir / "metadata" / f"{out_label}_community_tag_enrichment.csv", index=False)
            tag_modularity.to_csv(paths.output_dir / "metadata" / f"{out_label}_tag_modularity.csv", index=False)
            graph_for_gexf = graph.copy()
            attach_communities(graph_for_gexf, assignments[["bgg_id", "community"]])
            write_gexf(graph_for_gexf, paths.output_dir / "gephi" / f"{out_label}_communities.gexf")

        row = {
            "graph_label": args.graph_label,
            "output_label": out_label,
            "gamma": gamma,
            "n_seeds": args.seeds,
            **gdiag,
            **run_summary,
            **part_summary,
            **enrichment_summary,
            **tag_mod_summary,
            "observed_elapsed_seconds": round(time.perf_counter() - t0, 3),
        }
        observed_rows.append(row)
        print(
            f"  k={part_summary['n_communities']} "
            f"largest={part_summary['largest_community_fraction']:.1%} "
            f"Q={run_summary['observed_modularity']:.4f} "
            f"NMI={run_summary['median_pairwise_nmi']:.3f} "
            f"large_enriched={enrichment_summary['large_communities_with_strong_enrichment_p001']}"
        )

    print("\nnull-model sweep")
    null_reps = evaluate_null_graphs(
        graph,
        args.gammas,
        n_replicates=args.null_replicates,
        swaps_per_edge=args.swaps_per_edge,
        seed=args.seed,
    )

    observed = pd.DataFrame(observed_rows)
    null_summary = (
        null_reps.groupby("gamma")
        .agg(
            null_mean_modularity=("null_modularity", "mean"),
            null_std_modularity=("null_modularity", lambda s: s.std(ddof=1)),
            null_median_n_communities=("null_n_communities", "median"),
            null_mean_n_communities=("null_n_communities", "mean"),
            null_replicates=("null_modularity", "size"),
        )
        .reset_index()
    )
    summary = observed.merge(null_summary, on="gamma", how="left")
    summary["z_score"] = (
        (summary["observed_modularity"] - summary["null_mean_modularity"])
        / summary["null_std_modularity"]
    )
    summary["passes_nmi_gate"] = summary["median_pairwise_nmi"] >= 0.70
    summary["passes_null_gate"] = summary["z_score"] > 2.0
    summary["validated_midline_candidate"] = summary["passes_nmi_gate"] & summary["passes_null_gate"]

    out_summary = paths.output_dir / "diagnostics" / f"{args.graph_label}_midline_gamma_null_sweep.csv"
    out_reps = paths.output_dir / "diagnostics" / f"{args.graph_label}_midline_gamma_null_replicates.csv"
    summary.to_csv(out_summary, index=False)
    null_reps.to_csv(out_reps, index=False)

    print("\n" + "=" * 72)
    print(f"summary:    {out_summary}")
    print(f"replicates: {out_reps}")
    print("=" * 72)
    display_cols = [
        "gamma",
        "n_communities",
        "largest_community_fraction",
        "median_pairwise_nmi",
        "observed_modularity",
        "null_mean_modularity",
        "z_score",
        "validated_midline_candidate",
    ]
    print(summary[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
