"""Project path configuration for CS514 network analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    baseline_dir: Path
    expansion_dir: Path
    details_csv: Path
    output_dir: Path

    @classmethod
    def from_root(cls, root: Path, output_label: str = "cs514_network_analysis") -> "ProjectPaths":
        return cls(
            root=root,
            baseline_dir=root / "data" / "processed" / "reliable_users" / "reliable_users_batch1",
            expansion_dir=root / "data" / "processed" / "reliable_users" / "diversity_expansion_batch1",
            details_csv=(
                root
                / "data"
                / "processed"
                / "top_ranked_games_details"
                / "top_ranked_games_details_top5000_ranked_only"
                / "top_ranked_games_details.csv"
            ),
            output_dir=root / "data" / "processed" / output_label,
        )


def ensure_dirs(paths: ProjectPaths) -> None:
    for name in [
        "incidence",
        "projections",
        "backbones",
        "communities",
        "metadata",
        "diagnostics",
        "gephi",
    ]:
        (paths.output_dir / name).mkdir(parents=True, exist_ok=True)
