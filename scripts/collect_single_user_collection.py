"""Fetch collection details for a single BGG user and save raw + parsed outputs.

Useful for spot-checking what a user's collection looks like, verifying that
ratings (`stats=1`) are coming through, and producing an isolated user sample
without touching the reliable_users pipeline state.

By default it fetches for username LOJIMA. Outputs are written to:
  data/raw/single_user/<username>/
  data/processed/single_user/<username>/

Two fetches are done (mirroring rank_range_users):
  1) full collection (stats=1)          -> all items + ratings where present
  2) rated-only       (rated=1, stats=1) -> rated items slice for cross-check

Usage:
  python scripts/collect_single_user_collection.py
  python scripts/collect_single_user_collection.py --username SomeUser
  python scripts/collect_single_user_collection.py --username LOJIMA --no-rated
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.rank_range_users import (
    USER_COLLECTION_EDGE_FIELDNAMES,
    USER_SUMMARY_FIELDNAMES,
    build_user_summary,
    merge_collection_rows,
    parse_collection_items,
)
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


DEFAULT_USERNAME = "LOJIMA"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a single BGG user's collection details.")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="BGG username to fetch (default: LOJIMA).")
    parser.add_argument(
        "--selected-games-csv",
        default="data/processed/reliable_users/reliable_users_batch1/selected_games.csv",
        help="Path to selected_games.csv used to compute selected_game_overlap_count.",
    )
    parser.add_argument("--no-stats", action="store_true", help="Disable stats=1 on the main fetch (NOT recommended — ratings will be missing).")
    parser.add_argument("--no-rated", action="store_true", help="Skip the separate rated=1 cross-check fetch.")
    parser.add_argument(
        "--output-root",
        default=None,
        help="Override processed output root. Defaults to <project>/data/processed/single_user/<username>/.",
    )
    return parser.parse_args()


def _load_selected_game_ids(csv_path: Path) -> set[int]:
    if not csv_path.exists():
        return set()
    ids: set[int] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                ids.add(int(row["bgg_id"]))
            except (KeyError, ValueError):
                continue
    return ids


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Normalize list-valued fields (summary) to pipe-delimited strings.
            out = {}
            for k, v in row.items():
                if isinstance(v, list):
                    out[k] = " | ".join(str(x) for x in v)
                else:
                    out[k] = v
            writer.writerow(out)


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.collect_single_user_collection")

    username = args.username.strip()
    if not username:
        logger.error("Empty username.")
        return 2

    project_root = settings["_meta"]["project_root"]
    raw_root = Path(settings["paths"]["raw_data_dir"])
    if not raw_root.is_absolute():
        raw_root = project_root / raw_root
    proc_root = Path(settings["paths"]["processed_data_dir"])
    if not proc_root.is_absolute():
        proc_root = project_root / proc_root

    raw_dir = raw_root / "single_user" / username
    proc_dir = Path(args.output_root) if args.output_root else proc_root / "single_user" / username
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    selected_csv = Path(args.selected_games_csv)
    if not selected_csv.is_absolute():
        selected_csv = project_root / selected_csv
    selected_ids = _load_selected_game_ids(selected_csv)
    logger.info("Loaded %s selected game ids from %s", len(selected_ids), selected_csv)

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

    use_stats = not args.no_stats
    logger.info("Fetching full collection for user %s (stats=%s)...", username, use_stats)
    all_xml = client.get_collection_for_user(username, stats=use_stats)
    (raw_dir / f"{username}_collection_all.xml").write_text(all_xml, encoding="utf-8")
    all_rows = parse_collection_items(all_xml, username=username, source_label="collection_all")
    logger.info("  -> %s items parsed from collection_all.", len(all_rows))

    merged_rows = all_rows
    if not args.no_rated:
        logger.info("Fetching rated-only slice for user %s (rated=1, stats=1)...", username)
        rated_xml = client.get_collection_for_user(username, rated=True, stats=True)
        (raw_dir / f"{username}_collection_rated.xml").write_text(rated_xml, encoding="utf-8")
        rated_rows = parse_collection_items(rated_xml, username=username, source_label="collection_rated")
        logger.info("  -> %s items parsed from collection_rated.", len(rated_rows))
        merged_rows = merge_collection_rows(all_rows, rated_rows)

    edges_path = proc_dir / f"{username}_collection_edges.csv"
    _write_csv(edges_path, merged_rows, USER_COLLECTION_EDGE_FIELDNAMES)
    logger.info("Wrote %s edges -> %s", len(merged_rows), edges_path)

    candidate_stub = {
        "username": username,
        "discovery_count": 0,
        "rating_comment_count": 0,
        "play_player_count": 0,
        "source_games": [],
        "source_game_ranks": [],
        "source_types": [],
    }
    summary = build_user_summary(candidate_stub, merged_rows, selected_game_ids=selected_ids)
    summary_path = proc_dir / f"{username}_user_summary.csv"
    _write_csv(summary_path, [summary], USER_SUMMARY_FIELDNAMES)
    logger.info("Wrote user summary -> %s", summary_path)

    rated_edges = sum(1 for r in merged_rows if r.get("user_rating") is not None)
    logger.info(
        "Summary for %s: total_items=%s, owned=%s, rated=%s, selected_overlap=%s, numplays_sum=%s",
        username,
        summary["collection_item_count"],
        summary["owned_count"],
        summary["rated_count"],
        summary["selected_game_overlap_count"],
        summary["numplays_sum"],
    )
    logger.info("Edges with a numeric user_rating: %s / %s", rated_edges, len(merged_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
