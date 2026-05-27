"""Create random and matched baseline subsamples for the CS514 cohort decomposition."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

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
from bgg_project.cs514.paths import ProjectPaths, ensure_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create baseline_random and baseline_matched user lists.")
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--k-neighbors", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    paths = ProjectPaths.from_root(PROJECT_ROOT)
    ensure_dirs(paths)
    out_dir = paths.output_dir / "diagnostics" / "cohort_subsamples"
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline, expansion, _ = load_users(paths)
    baseline = coerce_numeric(baseline, MATCH_FEATURES + BALANCE_FEATURES)
    expansion = coerce_numeric(expansion, MATCH_FEATURES + BALANCE_FEATURES)
    n_expansion = len(expansion)

    distances, indices, _ = build_nn_matcher(baseline, expansion, k_neighbors=args.k_neighbors)

    user_rows, balance_rows, match_rows = [], [], []
    balance_rows.extend(balance_summary(baseline, "baseline_full", "full"))
    balance_rows.extend(balance_summary(expansion, "expansion", "full"))

    for rep in range(args.replicates):
        random_sample = draw_random_subsample(baseline, n_expansion, rng, rep)
        user_rows.append(random_sample)
        balance_rows.extend(
            balance_summary(
                baseline[baseline["username"].isin(random_sample["username"])],
                "baseline_random",
                rep,
            )
        )

        matched_sample, diagnostics = draw_matched_subsample(baseline, distances, indices, rng, rep)
        user_rows.append(matched_sample)
        balance_rows.extend(
            balance_summary(
                baseline[baseline["username"].isin(matched_sample["username"])],
                "baseline_matched",
                rep,
            )
        )
        match_rows.append(diagnostics)

    pd.concat(user_rows, ignore_index=True).to_csv(out_dir / "cohort_subsample_users.csv", index=False)
    pd.DataFrame(balance_rows).to_csv(out_dir / "cohort_subsample_balance.csv", index=False)
    pd.DataFrame(match_rows).to_csv(out_dir / "cohort_subsample_match_diagnostics.csv", index=False)
    print(f"wrote subsamples under {out_dir}")


if __name__ == "__main__":
    main()
