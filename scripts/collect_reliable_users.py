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
from bgg_project.collectors.reliable_users import run_reliable_users_pipeline
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a reliable user pool by reusing existing discovery batches, "
            "fetching full collections first, and stopping when enough users pass "
            "a configurable collection-density threshold."
        )
    )
    parser.add_argument("--config", default="config/settings.yaml", help="Path to the project settings YAML file.")
    parser.add_argument("--rank-csv", default=None, help="Path to the ranked games CSV. Defaults to the config value.")
    parser.add_argument("--start-rank", type=int, default=None, help="Starting overall rank, inclusive.")
    parser.add_argument("--end-rank", type=int, default=None, help="Ending overall rank, inclusive.")
    parser.add_argument("--bootstrap-run-label", default=None, help="Existing rank_range_users run label to reuse as bootstrap state.")
    parser.add_argument("--target-established-users", type=int, default=None, help="How many established users to collect before stopping.")
    parser.add_argument("--min-collection-items", type=int, default=None, help="Minimum collection items for an established user.")
    parser.add_argument("--min-selected-overlap", type=int, default=None, help="Minimum overlap with the selected game universe for an established user.")
    parser.add_argument("--discovery-new-candidate-target", type=int, default=None, help="How many new candidate users to discover before pausing discovery and returning to enrichment.")
    parser.add_argument("--ratingcomments-pages", type=int, default=None, help="How many rating-comment pages to collect per newly discovered game.")
    parser.add_argument("--ratingcomments-page-size", type=int, default=None, help="How many rating comments to request per page.")
    parser.add_argument("--plays-pages", type=int, default=None, help="How many play-log pages to collect per newly discovered game.")
    parser.add_argument("--enrichment-batch-size", type=int, default=None, help="How many candidate users to enrich with full collections per batch.")
    parser.add_argument("--output-label", default=None, help="Optional snapshot label. Reuse the same label to resume a reliable-user pipeline run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.collect_reliable_users")

    collector_settings = settings["collection"]["reliable_users"]
    rank_csv_value = Path(args.rank_csv) if args.rank_csv else Path(collector_settings["rank_csv_path"])
    rank_csv_path = rank_csv_value if rank_csv_value.is_absolute() else settings["_meta"]["project_root"] / rank_csv_value

    ranked_games = load_ranked_games_from_csv(rank_csv_path)
    token = get_api_token(settings)
    client = BGGClient(
        base_url=settings["api"]["base_url"],
        token=token,
        use_environment_proxies=False,
        timeout_seconds=settings["api"]["request_timeout_seconds"],
        min_seconds_between_requests=max(settings["api"]["min_seconds_between_requests"], 6),
        max_retries=settings["api"]["max_retries"],
        retry_backoff_seconds=settings["api"]["retry_backoff_seconds"],
        logger=logger,
    )

    artifacts = run_reliable_users_pipeline(
        client,
        ranked_games,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        start_rank=args.start_rank or collector_settings["start_rank"],
        end_rank=args.end_rank or collector_settings["end_rank"],
        target_established_users=args.target_established_users or collector_settings["target_established_users"],
        min_collection_items=args.min_collection_items or collector_settings["min_collection_items"],
        min_selected_overlap_count=args.min_selected_overlap or collector_settings["min_selected_overlap_count"],
        discovery_new_candidate_target=args.discovery_new_candidate_target or collector_settings["discovery_new_candidate_target"],
        ratingcomments_pages_per_game=args.ratingcomments_pages or collector_settings["ratingcomments_pages_per_game"],
        ratingcomments_page_size=args.ratingcomments_page_size or collector_settings["ratingcomments_page_size"],
        plays_pages_per_game=args.plays_pages or collector_settings["plays_pages_per_game"],
        enrichment_batch_size=args.enrichment_batch_size or collector_settings["enrichment_batch_size"],
        bootstrap_run_label=args.bootstrap_run_label or collector_settings.get("bootstrap_run_label"),
        output_label=args.output_label,
        logger=logger,
    )

    logger.info("Candidate users available: %s", artifacts.metadata["candidate_user_count"])
    logger.info("Fully fetched users: %s", artifacts.metadata["fully_fetched_user_count"])
    logger.info("Established users: %s", artifacts.metadata["established_user_count"])
    logger.info("Next start rank for discovery: %s", artifacts.metadata["next_start_rank"])
    logger.info("Metadata JSON: %s", artifacts.outputs["metadata_path"])
    logger.info("Pipeline state JSON: %s", artifacts.outputs["state_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
