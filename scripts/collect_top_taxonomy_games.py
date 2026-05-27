from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.top_taxonomy_games import (
    GeekdoLinkedItemsClient,
    collect_top_taxonomy_games_snapshot,
    load_taxonomy_records_from_csv,
    write_top_taxonomy_games_snapshot,
)
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the top linked board games for each mechanic and category, "
            "then enrich the unique games with XML API /thing data."
        )
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to the project settings YAML file.",
    )
    parser.add_argument(
        "--taxonomy-dir",
        default=None,
        help=(
            "Directory containing mechanics.csv and categories.csv. "
            "Defaults to the configured taxonomy snapshot directory."
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="How many games to collect for each mechanic/category. Defaults to the config value.",
    )
    parser.add_argument(
        "--sort",
        default=None,
        help="Linked-items sort field. Defaults to the config value, usually rank.",
    )
    parser.add_argument(
        "--limit-mechanics",
        type=int,
        default=None,
        help="Optional limit for a quick mechanic-only pilot subset.",
    )
    parser.add_argument(
        "--limit-categories",
        type=int,
        default=None,
        help="Optional limit for a quick category-only pilot subset.",
    )
    parser.add_argument(
        "--output-label",
        default=None,
        help="Optional folder label for this snapshot. Defaults to a UTC timestamp.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.collect_top_taxonomy_games")

    collector_settings = settings["collection"]["top_taxonomy_games"]
    taxonomy_dir = _resolve_path(
        args.taxonomy_dir or collector_settings["taxonomy_snapshot_dir"],
        settings["_meta"]["project_root"],
    )
    mechanics_csv_path = taxonomy_dir / "mechanics.csv"
    categories_csv_path = taxonomy_dir / "categories.csv"

    mechanics = load_taxonomy_records_from_csv(mechanics_csv_path)
    categories = load_taxonomy_records_from_csv(categories_csv_path)
    if args.limit_mechanics is not None:
        mechanics = mechanics[: args.limit_mechanics]
    if args.limit_categories is not None:
        categories = categories[: args.limit_categories]

    top_n = args.top_n or collector_settings["top_n_per_taxonomy"]
    sort = args.sort or collector_settings["sort"]
    thing_batch_size = collector_settings["thing_batch_size"]

    geekdo_client = GeekdoLinkedItemsClient(
        base_url=collector_settings["geekdo_base_url"],
        timeout_seconds=collector_settings["request_timeout_seconds"],
        use_environment_proxies=False,
        logger=logger,
    )
    token = get_api_token(settings)
    thing_client = BGGClient(
        base_url=settings["api"]["base_url"],
        token=token,
        use_environment_proxies=False,
        timeout_seconds=settings["api"]["request_timeout_seconds"],
        min_seconds_between_requests=settings["api"]["min_seconds_between_requests"],
        max_retries=settings["api"]["max_retries"],
        retry_backoff_seconds=settings["api"]["retry_backoff_seconds"],
        logger=logger,
    )

    logger.info("Mechanics loaded: %s", len(mechanics))
    logger.info("Categories loaded: %s", len(categories))
    logger.info("Collecting top %s game(s) per taxonomy using sort=%s", top_n, sort)

    artifacts = collect_top_taxonomy_games_snapshot(
        geekdo_client,
        thing_client,
        mechanics=mechanics,
        categories=categories,
        top_n_per_taxonomy=top_n,
        sort=sort,
        thing_batch_size=thing_batch_size,
    )
    outputs = write_top_taxonomy_games_snapshot(
        artifacts,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        output_label=args.output_label,
    )

    logger.info("Selected unique games: %s", artifacts.snapshot["selected_game_count"])
    logger.info("Snapshot JSON: %s", outputs["snapshot_json_path"])
    logger.info("Mechanics CSV: %s", outputs["mechanics_csv_path"])
    logger.info("Categories CSV: %s", outputs["categories_csv_path"])
    logger.info("Selected games CSV: %s", outputs["selected_games_csv_path"])
    return 0


def _resolve_path(value: str | Path, project_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


if __name__ == "__main__":
    raise SystemExit(main())
