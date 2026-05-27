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
from bgg_project.collectors.rank_range_users import run_rank_range_user_extraction
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover users from a ranked-game range, then collect their full and "
            "rated collection details into analysis-ready tables."
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
        "--start-rank",
        type=int,
        default=None,
        help="Starting overall rank, inclusive. Defaults to the config value.",
    )
    parser.add_argument(
        "--end-rank",
        type=int,
        default=None,
        help="Ending overall rank, inclusive. Defaults to the config value.",
    )
    parser.add_argument(
        "--ratingcomments-pages",
        type=int,
        default=None,
        help="How many rating-comment pages to collect per seed game.",
    )
    parser.add_argument(
        "--ratingcomments-page-size",
        type=int,
        default=None,
        help="How many rating comments to request per page.",
    )
    parser.add_argument(
        "--plays-pages",
        type=int,
        default=None,
        help="How many play-log pages to collect per seed game.",
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="Optional cap on discovered users to enrich with collection details.",
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
    logger = logging.getLogger("bgg_project.collect_rank_range_users")

    collector_settings = settings["collection"]["rank_range_users"]
    rank_csv_value = Path(args.rank_csv) if args.rank_csv else Path(collector_settings["rank_csv_path"])
    rank_csv_path = rank_csv_value if rank_csv_value.is_absolute() else settings["_meta"]["project_root"] / rank_csv_value

    start_rank = args.start_rank or collector_settings["start_rank"]
    end_rank = args.end_rank or collector_settings["end_rank"]
    ratingcomments_pages = args.ratingcomments_pages or collector_settings["ratingcomments_pages_per_game"]
    ratingcomments_page_size = args.ratingcomments_page_size or collector_settings["ratingcomments_page_size"]
    plays_pages = args.plays_pages or collector_settings["plays_pages_per_game"]
    max_users = args.max_users or collector_settings.get("max_users")

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
    logger.info(
        "Starting detailed rank-range user extraction for ranks %s to %s.",
        start_rank,
        end_rank,
    )

    artifacts = run_rank_range_user_extraction(
        client,
        ranked_games,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        start_rank=start_rank,
        end_rank=end_rank,
        ratingcomments_pages_per_game=ratingcomments_pages,
        ratingcomments_page_size=ratingcomments_page_size,
        plays_pages_per_game=plays_pages,
        max_users=max_users,
        output_label=args.output_label,
        logger=logger,
    )

    logger.info("Selected seed games: %s", artifacts.metadata["selected_game_count"])
    logger.info("Candidate users discovered: %s", artifacts.metadata["candidate_user_count"])
    logger.info("Successful user collections: %s", artifacts.metadata["successful_user_count"])
    logger.info("Failed user collections: %s", artifacts.metadata["failed_user_count"])
    logger.info("User edges collected: %s", artifacts.metadata["user_collection_edge_count"])
    logger.info("Processed discovery through rank: %s", artifacts.metadata["processed_game_end_rank"])
    logger.info("Next recommended start rank: %s", artifacts.metadata["next_start_rank"])
    logger.info("Metadata JSON: %s", artifacts.outputs["metadata_path"])
    logger.info("Resume checkpoint JSON: %s", artifacts.outputs["checkpoint_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
