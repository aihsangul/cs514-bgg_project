"""Build cached CS514 user-game incidence matrices and edge-overlap diagnostics."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.cs514.data_io import edge_paths_for, load_games, user_names_for
from bgg_project.cs514.incidence import (
    build_incidence,
    compute_edge_overlap,
    incidence_diagnostics,
    load_incidence,
    save_incidence,
)
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs
from bgg_project.cs514.signals import SIGNAL_SPECS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CS514 incidence matrices.")
    parser.add_argument("--cohorts", nargs="+", default=["baseline", "merged", "expansion"])
    parser.add_argument("--signals", nargs="+", default=list(SIGNAL_SPECS))
    parser.add_argument(
        "--user-list-csv",
        help="Optional CSV with a username column. Builds one custom cohort from these users.",
    )
    parser.add_argument("--user-list-label", help="Label for --user-list-csv custom cohort.")
    parser.add_argument("--chunksize", type=int, default=500_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.from_root(PROJECT_ROOT)
    ensure_dirs(paths)
    games = load_games(paths)
    selected_ids = set(games["bgg_id"].astype(int))

    diagnostics = []
    cohort_jobs = []
    if args.user_list_csv:
        if not args.user_list_label:
            raise SystemExit("--user-list-label is required with --user-list-csv")
        user_df = pd.read_csv(args.user_list_csv)
        allowed_users = set(user_df["username"].astype(str))
        cohort_jobs.append((args.user_list_label, "merged", allowed_users))
    else:
        for cohort in args.cohorts:
            cohort_jobs.append((cohort, cohort, user_names_for(paths, cohort)))

    for cohort, edge_cohort, allowed_users in cohort_jobs:
        overlap = compute_edge_overlap(
            edge_paths_for(paths, edge_cohort),
            selected_ids,
            allowed_users=allowed_users,
            chunksize=args.chunksize,
        )
        overlap.insert(0, "cohort", cohort)
        overlap.to_csv(paths.output_dir / "diagnostics" / f"edge_overlap_{cohort}.csv", index=False)

        for signal in args.signals:
            print(f"building incidence: cohort={cohort} signal={signal}")
            matrix, user_index, game_index = build_incidence(
                edge_paths_for(paths, edge_cohort),
                games,
                signal,
                allowed_users=allowed_users,
                chunksize=args.chunksize,
            )
            label = f"{cohort}_{signal}"
            save_incidence(matrix, user_index, game_index, paths.output_dir / "incidence" / label)
            diagnostics.append(incidence_diagnostics(matrix, label))

    pd.DataFrame(diagnostics).to_csv(paths.output_dir / "diagnostics" / "incidence_diagnostics.csv", index=False)
    print(f"wrote outputs under {paths.output_dir}")


if __name__ == "__main__":
    main()
