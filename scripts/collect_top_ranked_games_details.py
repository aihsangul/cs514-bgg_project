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
from bgg_project.collectors.mechanics_top25 import load_ranked_games_from_csv
from bgg_project.collectors.top_ranked_games_details import (
    collect_top_ranked_games_details_snapshot,
    write_top_ranked_games_details_snapshot,
)
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect detailed /thing metadata for the top-ranked games in the BGG rank CSV."
        )
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to the project settings YAML file.",
    )
    parser.add_argument(
        "--rank-csv",
        default=None,
        help="Path to the ranked games CSV. Defaults to the config value.",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="How many top-ranked games to enrich. Defaults to the config value.",
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
    logger = logging.getLogger("bgg_project.collect_top_ranked_games_details")

    collector_settings = settings["collection"]["top_ranked_games_details"]
    rank_csv_value = Path(args.rank_csv) if args.rank_csv else Path(collector_settings["rank_csv_path"])
    rank_csv_path = rank_csv_value if rank_csv_value.is_absolute() else settings["_meta"]["project_root"] / rank_csv_value
    max_games = args.max_games or collector_settings["max_games"]
    thing_batch_size = collector_settings["thing_batch_size"]

    ranked_games = load_ranked_games_from_csv(rank_csv_path)
    token = get_api_token(settings)
    client = BGGClient(
        base_url=settings["api"]["base_url"],
        token=token,
        use_environment_proxies=False,
        timeout_seconds=settings["api"]["request_timeout_seconds"],
        min_seconds_between_requests=settings["api"]["min_seconds_between_requests"],
        max_retries=settings["api"]["max_retries"],
        retry_backoff_seconds=settings["api"]["retry_backoff_seconds"],
        logger=logger,
    )

    logger.info("Loaded %s ranked games from %s", len(ranked_games), rank_csv_path)
    logger.info("Collecting detailed /thing metadata for the top %s ranked games.", max_games)

    artifacts = collect_top_ranked_games_details_snapshot(
        client,
        ranked_games,
        max_games=max_games,
        thing_batch_size=thing_batch_size,
    )
    outputs = write_top_ranked_games_details_snapshot(
        artifacts,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        output_label=args.output_label,
    )

    logger.info("Collected detailed rows: %s", artifacts.snapshot["collected_game_count"])
    logger.info("Snapshot JSON: %s", outputs["snapshot_json_path"])
    logger.info("Detailed CSV: %s", outputs["detailed_games_csv_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
