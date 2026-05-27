#!/usr/bin/env python3
"""
CS514 network-analysis pipeline runner.

USAGE
-----
Run every stage:
    python scripts/cs514_pipeline.py

Run specific stages only:
    python scripts/cs514_pipeline.py --steps incidence backbone

Skip specific stages:
    python scripts/cs514_pipeline.py --skip cohort null_model

Preview what would run without executing:
    python scripts/cs514_pipeline.py --dry-run

CONFIG
All analysis parameters live in the CONFIG block below.
The CLI controls *which* stages run; CONFIG controls *how* each stage runs.

STAGE ORDER
  1. incidence    build user-game sparse matrices + signal-overlap diagnostics
  2. backbone     Newman RA projection → disparity-filter backbone → GEXF
  3. cohort       random + propensity-matched baseline subsamples
  4. community    Louvain detection + tag-modularity + enrichment + GEXF
  5. null_model   degree-preserving null-model modularity test
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


#  CONFIGURATION
CONFIG = {

    # 1. Incidence matrices
    # Which user cohorts to build matrices for.
    #   "baseline"  → 5 175 users from reliable_users_batch1
    #   "expansion" → 478 diversity-expansion users
    #   "merged"    → both combined (use this for the main analysis)
    "incidence_cohorts": ["baseline", "merged"],

    # Which behavioural signal layers to materialise.
    #   "ownership"         -> own == 1
    #   "positive_interest" ->  own | wishlist | want | wanttoplay | wanttobuy
    #   "did_not_retain"    -> prevowned | fortrade
    "incidence_signals": ["ownership", "positive_interest", "did_not_retain"],

    # Pandas CSV chunk size (rows).  Reduce if you hit memory pressure.
    "incidence_chunksize": 500_000,

    # 2. Backbone (projection + disparity filter)
    # Which incidence matrix labels to project.
    # Format: "<cohort>_<signal>"
    "backbone_labels": ["merged_ownership"],

    # Disparity-filter significance thresholds.
    # The sweep selected 0.001 as the primary alpha for this very dense
    # projection; the other values remain available for sensitivity checks.
    "backbone_alphas": [0.001, 0.005, 0.01, 0.025, 0.05],

    # Write the full (pre-filter) Newman projection as an edge CSV?
    # Warning: the merged-ownership full projection is ~98% dense (≈3M edges).
    "backbone_write_full_projection": False,

    # ── 3. Cohort subsamples ──────────────────────────────────────────────
    # Number of bootstrap replicates for the four-graph decomposition.
    # Use 20 for development, 50 for final results.
    "cohort_replicates": 20,

    # k-nearest-neighbours used for propensity matching.
    # Each expansion user is matched to one of its k closest baseline users.
    "cohort_k_neighbors": 5,

    # Random seed for subsample draws.
    "cohort_seed": 123,

    # ── 4. Community detection ────────────────────────────────────────────
    # Which backbone graph to partition.
    # Must match a file in backbones/<label>_edges.csv (produced by step 2).
    # Leave as None to auto-derive from the first backbone_label + first alpha.
    "community_graph_label": "merged_ownership_newman_disparity_a0p001",

    # Number of independent Louvain seeds.  Median pairwise NMI across seeds
    # should be ≥ 0.70 before trusting the partition.
    "community_n_seeds": 20,

    # Louvain resolution parameter. Values > 1 create smaller communities.
    # Use scripts/cs514_parameter_sweep.py to choose the final resolution.
    "community_resolution": 0.75,

    # ── 5. Null model ─────────────────────────────────────────────────────
    # Which backbone graph to test.  Same auto-derive logic as community step.
    "null_model_graph_label": "merged_ownership_newman_disparity_a0p001",

    # Number of degree-preserving rewiring replicates.
    # Use 20 for development, 50 for final results.
    "null_model_replicates": 20,

    # Random seed for rewiring + weight shuffling.
    "null_model_seed": 123,
}

# ---------------------------------------------------------------------------
# ── DERIVED LABELS  (auto-computed; override by setting the None fields above)
# ---------------------------------------------------------------------------

def _primary_graph_label(cfg: dict) -> str:
    """Build the canonical backbone label from the first label + first alpha."""
    label = cfg["backbone_labels"][0]
    alpha_str = str(cfg["backbone_alphas"][0]).replace(".", "p")
    return f"{label}_newman_disparity_a{alpha_str}"


# ---------------------------------------------------------------------------
# ── STAGE IMPLEMENTATIONS ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_incidence(paths, cfg: dict) -> None:
    import pandas as pd
    from bgg_project.cs514.data_io import edge_paths_for, load_games, user_names_for
    from bgg_project.cs514.incidence import (
        build_incidence,
        compute_edge_overlap,
        incidence_diagnostics,
        save_incidence,
    )

    games = load_games(paths)
    selected_ids = set(games["bgg_id"].astype(int))
    diagnostics = []

    for cohort in cfg["incidence_cohorts"]:
        allowed = user_names_for(paths, cohort)
        edge_paths = edge_paths_for(paths, cohort)

        overlap = compute_edge_overlap(edge_paths, selected_ids, allowed_users=allowed,
                                       chunksize=cfg["incidence_chunksize"])
        overlap.insert(0, "cohort", cohort)
        overlap.to_csv(paths.output_dir / "diagnostics" / f"edge_overlap_{cohort}.csv", index=False)
        print(f"  [{cohort}] edge overlap written")

        for signal in cfg["incidence_signals"]:
            print(f"  [{cohort}] building {signal} …", end=" ", flush=True)
            matrix, user_index, game_index = build_incidence(
                edge_paths, games, signal, allowed_users=allowed,
                chunksize=cfg["incidence_chunksize"],
            )
            label = f"{cohort}_{signal}"
            save_incidence(matrix, user_index, game_index, paths.output_dir / "incidence" / label)
            diag = incidence_diagnostics(matrix, label)
            diagnostics.append(diag)
            print(f"nnz={diag['nnz']:,}  active_users={diag['active_users']}")

    pd.DataFrame(diagnostics).to_csv(paths.output_dir / "diagnostics" / "incidence_diagnostics.csv", index=False)


def run_backbone(paths, cfg: dict) -> None:
    import pandas as pd
    from bgg_project.cs514.graph_io import graph_diagnostics, graph_from_matrix, write_gexf, write_graph_edges
    from bgg_project.cs514.incidence import load_incidence
    from bgg_project.cs514.projection import disparity_backbone, matrix_to_edges, newman_projection

    diagnostics = []
    for label in cfg["backbone_labels"]:
        print(f"  projecting {label} …", end=" ", flush=True)
        matrix, _, game_index = load_incidence(paths.output_dir / "incidence" / label)
        projection = newman_projection(matrix)
        print("done")

        if cfg["backbone_write_full_projection"]:
            matrix_to_edges(projection, game_index).to_csv(
                paths.output_dir / "projections" / f"{label}_newman_edges.csv", index=False
            )

        for alpha in cfg["backbone_alphas"]:
            alpha_str = str(alpha).replace(".", "p")
            out_label = f"{label}_newman_disparity_a{alpha_str}"
            print(f"  disparity filter alpha={alpha} …", end=" ", flush=True)
            backbone = disparity_backbone(projection, alpha=alpha, mode="or")
            graph = graph_from_matrix(backbone, game_index)
            write_graph_edges(graph, paths.output_dir / "backbones" / f"{out_label}_edges.csv")
            write_gexf(graph, paths.output_dir / "gephi" / f"{out_label}.gexf")
            diag = graph_diagnostics(graph, out_label)
            diagnostics.append(diag)
            print(f"nodes={diag['nodes']}  edges={diag['edges']}  giant={diag['giant_component_fraction']:.1%}")

    pd.DataFrame(diagnostics).to_csv(paths.output_dir / "diagnostics" / "backbone_diagnostics.csv", index=False)


def run_cohort(paths, cfg: dict) -> None:
    import numpy as np
    import pandas as pd
    from bgg_project.cs514.cohort import (
        BALANCE_FEATURES,
        MATCH_FEATURES,
        balance_summary,
        build_nn_matcher,
        coerce_numeric,
        draw_matched_subsample,
        draw_random_subsample,
    )
    from bgg_project.cs514.data_io import load_users

    out_dir = paths.output_dir / "diagnostics" / "cohort_subsamples"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg["cohort_seed"])

    baseline, expansion, _ = load_users(paths)
    baseline = coerce_numeric(baseline, MATCH_FEATURES + BALANCE_FEATURES)
    expansion = coerce_numeric(expansion, MATCH_FEATURES + BALANCE_FEATURES)
    n_exp = len(expansion)
    print(f"  baseline={len(baseline)}  expansion={n_exp}")

    distances, indices, _ = build_nn_matcher(baseline, expansion, k_neighbors=cfg["cohort_k_neighbors"])

    user_rows, balance_rows, match_rows = [], [], []
    balance_rows.extend(balance_summary(baseline, "baseline_full", "full"))
    balance_rows.extend(balance_summary(expansion, "expansion", "full"))

    for rep in range(cfg["cohort_replicates"]):
        rand = draw_random_subsample(baseline, n_exp, rng, rep)
        user_rows.append(rand)
        balance_rows.extend(
            balance_summary(baseline[baseline["username"].isin(rand["username"])], "baseline_random", rep)
        )
        matched, diag = draw_matched_subsample(baseline, distances, indices, rng, rep)
        user_rows.append(matched)
        balance_rows.extend(
            balance_summary(baseline[baseline["username"].isin(matched["username"])], "baseline_matched", rep)
        )
        match_rows.append(diag)

    pd.concat(user_rows, ignore_index=True).to_csv(out_dir / "cohort_subsample_users.csv", index=False)
    pd.DataFrame(balance_rows).to_csv(out_dir / "cohort_subsample_balance.csv", index=False)
    pd.DataFrame(match_rows).to_csv(out_dir / "cohort_subsample_match_diagnostics.csv", index=False)
    print(f"  {cfg['cohort_replicates']} replicates written to {out_dir.relative_to(paths.root)}")


def run_community(paths, cfg: dict) -> None:
    import pandas as pd
    from bgg_project.cs514.community import community_output_label, detect_louvain
    from bgg_project.cs514.data_io import load_games
    from bgg_project.cs514.graph_io import add_game_nodes, attach_communities, read_graph_csv, write_gexf
    from bgg_project.cs514.metadata import binary_tag_modularity, community_tag_enrichment

    graph_label = cfg["community_graph_label"] or _primary_graph_label(cfg)
    out_label = community_output_label(graph_label, cfg["community_resolution"])
    print(f"  graph: {graph_label}")
    print(f"  output label: {out_label}")

    games = load_games(paths)
    graph = read_graph_csv(paths.output_dir / "backbones" / f"{graph_label}_edges.csv")
    add_game_nodes(graph, games)

    print(f"  running Louvain  ({cfg['community_n_seeds']} seeds) …", end=" ", flush=True)
    assignments, run_stats = detect_louvain(
        graph, seeds=range(cfg["community_n_seeds"]), resolution=cfg["community_resolution"]
    )
    assignments = assignments.merge(games[["bgg_id", "name", "overall_rank"]], on="bgg_id", how="left")
    assignments.to_csv(paths.output_dir / "communities" / f"{out_label}_communities.csv", index=False)
    run_stats.to_csv(paths.output_dir / "communities" / f"{out_label}_community_runs.csv", index=False)

    # Report stability gate
    pairwise = run_stats[run_stats.iloc[:, 0] == "pairwise"] if "pairwise" in run_stats.iloc[:, 0].values else pd.DataFrame()
    if not pairwise.empty and "nmi" in pairwise.columns:
        med_nmi = pairwise["nmi"].median()
        gate = "PASS" if med_nmi >= 0.70 else "FAIL (re-run with more seeds or adjust resolution)"
        print(f"median pairwise NMI={med_nmi:.3f}  [{gate}]")
    else:
        print("done")

    print("  computing tag modularity + enrichment …", end=" ", flush=True)
    binary_tag_modularity(graph, games).to_csv(
        paths.output_dir / "metadata" / f"{out_label}_tag_modularity.csv", index=False
    )
    community_tag_enrichment(assignments[["bgg_id", "community"]], games).to_csv(
        paths.output_dir / "metadata" / f"{out_label}_community_tag_enrichment.csv", index=False
    )
    print("done")

    attach_communities(graph, assignments[["bgg_id", "community"]])
    write_gexf(graph, paths.output_dir / "gephi" / f"{out_label}_communities.gexf")
    print(f"  GEXF with communities -> gephi/{out_label}_communities.gexf")


def run_null_model(paths, cfg: dict) -> None:
    from bgg_project.cs514.data_io import load_games
    from bgg_project.cs514.graph_io import add_game_nodes, read_graph_csv, write_json
    from bgg_project.cs514.null_model import degree_preserving_null_modularity

    graph_label = cfg["null_model_graph_label"] or _primary_graph_label(cfg)
    print(f"  graph: {graph_label}  replicates={cfg['null_model_replicates']}")

    graph = read_graph_csv(paths.output_dir / "backbones" / f"{graph_label}_edges.csv")
    add_game_nodes(graph, load_games(paths))
    result = degree_preserving_null_modularity(
        graph,
        n_replicates=cfg["null_model_replicates"],
        seed=cfg["null_model_seed"],
        resolution=cfg["community_resolution"],
    )
    result.to_csv(paths.output_dir / "diagnostics" / f"{graph_label}_null_modularity.csv", index=False)

    null = result[result["replicate"] != "observed"]["modularity"]
    observed = float(result[result["replicate"] == "observed"]["modularity"].iloc[0])
    summary = {
        "observed_modularity": observed,
        "null_mean": float(null.mean()) if len(null) else None,
        "null_std": float(null.std(ddof=1)) if len(null) > 1 else None,
        "z_score": result.attrs.get("z_score"),
        "replicates": int(len(null)),
    }
    write_json(paths.output_dir / "diagnostics" / f"{graph_label}_null_modularity_summary.json", summary)
    z = summary["z_score"]
    print(f"  Q_obs={observed:.4f}  Q_null={summary['null_mean']:.4f}±{summary['null_std']:.4f}  z={z:.2f}" if z else f"  Q_obs={observed:.4f}")


# ---------------------------------------------------------------------------
# ── STAGE REGISTRY ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

STAGES: list[tuple[str, callable]] = [
    ("incidence",  run_incidence),
    ("backbone",   run_backbone),
    ("cohort",     run_cohort),
    ("community",  run_community),
    ("null_model", run_null_model),
]

STAGE_NAMES = [name for name, _ in STAGES]

DEPENDENCIES: dict[str, list[str]] = {
    "backbone":   ["incidence"],
    "community":  ["backbone"],
    "null_model": ["backbone"],
    "cohort":     [],
    "incidence":  [],
}


# ---------------------------------------------------------------------------
# ── CLI + RUNNER ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CS514 pipeline runner.  Edit CONFIG at the top of this file to set parameters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--steps", nargs="+", choices=STAGE_NAMES, metavar="STAGE",
        help=f"Run only these stages (default: all). Choices: {', '.join(STAGE_NAMES)}",
    )
    parser.add_argument(
        "--skip", nargs="+", choices=STAGE_NAMES, metavar="STAGE",
        help="Skip these stages.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the execution plan without running anything.",
    )
    return parser.parse_args()


def resolve_stages(args: argparse.Namespace) -> list[str]:
    requested = args.steps if args.steps else STAGE_NAMES
    skipped = set(args.skip or [])
    return [s for s in STAGE_NAMES if s in requested and s not in skipped]


def _outputs_exist(stage: str, paths) -> bool:
    """Return True if the key output files for *stage* already exist on disk."""
    d = paths.output_dir
    checks = {
        "incidence": lambda: any((d / "incidence").glob("*.npz")),
        "backbone":  lambda: any((d / "backbones").glob("*_edges.csv")),
        "cohort":    lambda: (d / "diagnostics" / "cohort_subsamples" / "cohort_subsample_users.csv").exists(),
        "community": lambda: any((d / "communities").glob("*_communities.csv")),
        "null_model": lambda: True,
    }
    return checks.get(stage, lambda: False)()


def _check_dep(stage: str, completed: set[str], paths) -> bool:
    """A dependency is satisfied if it ran this session OR its outputs exist on disk."""
    missing = [
        d for d in DEPENDENCIES.get(stage, [])
        if d not in completed and not _outputs_exist(d, paths)
    ]
    if missing:
        print(f"  SKIPPED — outputs for {missing} not found; run those stages first")
        return False
    return True


def main() -> None:
    args = parse_args()
    stages_to_run = resolve_stages(args)

    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    SRC_DIR = PROJECT_ROOT / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from bgg_project.cs514.paths import ProjectPaths, ensure_dirs
    paths = ProjectPaths.from_root(PROJECT_ROOT)

    # Print plan
    print("=" * 60)
    print("CS514 PIPELINE")
    print("=" * 60)
    for name in STAGE_NAMES:
        marker = ">>" if name in stages_to_run else "  "
        print(f"  {marker} {name}")
    print(f"output root: {paths.output_dir}")
    print("=" * 60)

    if args.dry_run:
        print("(dry-run - exiting without executing)")
        return

    ensure_dirs(paths)
    completed: set[str] = set()
    total_start = time.perf_counter()

    for name, fn in STAGES:
        if name not in stages_to_run:
            continue
        if not _check_dep(name, completed, paths):
            continue
        print(f"\n-- {name.upper()} ------------------------------------------")
        t0 = time.perf_counter()
        fn(paths, CONFIG)
        elapsed = time.perf_counter() - t0
        completed.add(name)
        print(f"  [done] {elapsed:.1f}s")

    total = time.perf_counter() - total_start
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete — {len(completed)}/{len(stages_to_run)} stages in {total:.1f}s")
    print(f"Outputs: {paths.output_dir}")
    if any(name in completed for name in ("backbone", "community")):
        print(f"Gephi:   {paths.output_dir / 'gephi'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
