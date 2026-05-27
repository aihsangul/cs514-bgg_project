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
from bgg_project.collectors.candidate_users import (
    collect_candidate_users_snapshot,
    write_candidate_users_snapshot,
)
from bgg_project.collectors.mechanics_top25 import load_ranked_games_from_csv
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover candidate usernames from top-ranked games using item-level "
            "rating comments and play logs."
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
        "--top-ranked-games",
        type=int,
        default=None,
        help="How many top-ranked games to use. Defaults to the config value.",
    )
    parser.add_argument(
        "--ratingcomments-pages",
        type=int,
        default=None,
        help="How many rating-comment pages to collect per game.",
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
        help="How many play-log pages to collect per game.",
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
    logger = logging.getLogger("bgg_project.discover_candidate_users")

    collector_settings = settings["collection"]["candidate_users"]
    rank_csv_value = Path(args.rank_csv) if args.rank_csv else Path(collector_settings["rank_csv_path"])
    rank_csv_path = rank_csv_value if rank_csv_value.is_absolute() else settings["_meta"]["project_root"] / rank_csv_value
    top_ranked_games = args.top_ranked_games or collector_settings["top_ranked_games"]
    ratingcomments_pages = args.ratingcomments_pages or collector_settings["ratingcomments_pages_per_game"]
    ratingcomments_page_size = args.ratingcomments_page_size or collector_settings["ratingcomments_page_size"]
    plays_pages = args.plays_pages or collector_settings["plays_pages_per_game"]

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
        "Discovering candidate users from the top %s ranked games (%s rating-comment page(s), %s play page(s) per game).",
        top_ranked_games,
        ratingcomments_pages,
        plays_pages,
    )

    artifacts = collect_candidate_users_snapshot(
        client,
        ranked_games,
        top_ranked_games=top_ranked_games,
        ratingcomments_pages_per_game=ratingcomments_pages,
        ratingcomments_page_size=ratingcomments_page_size,
        plays_pages_per_game=plays_pages,
    )
    outputs = write_candidate_users_snapshot(
        artifacts,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        output_label=args.output_label,
    )

    logger.info("Candidate users discovered: %s", artifacts.snapshot["candidate_user_count"])
    logger.info("Snapshot JSON: %s", outputs["snapshot_json_path"])
    logger.info("Candidate users CSV: %s", outputs["candidate_users_csv_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
