from __future__ import annotations

import argparse
import csv
from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.candidate_users import parse_play_users, parse_rating_comment_users
from bgg_project.collectors.rank_range_users import (
    DISCOVERY_ERROR_FIELDNAMES,
    DISCOVERY_PLAY_ROW_FIELDNAMES,
    DISCOVERY_RATING_ROW_FIELDNAMES,
    USER_COLLECTION_EDGE_FIELDNAMES,
    USER_ERROR_FIELDNAMES,
    USER_SUMMARY_FIELDNAMES,
    _user_file_stem,
    build_user_summary,
    parse_collection_items,
)
from bgg_project.config import get_api_token, load_settings
from bgg_project.logging_utils import setup_logging


DEFAULT_DETAILS_CSV = (
    "data/processed/top_ranked_games_details/"
    "top_ranked_games_details_top5000_ranked_only/top_ranked_games_details.csv"
)

SEED_FIELDNAMES = [
    "seed_index",
    "bgg_id",
    "name",
    "overall_rank",
    "average_rating",
    "owned",
    "num_comments",
    "wanting_plus_wishing",
    "wishlist_interest_ratio",
    "mechanics",
    "categories",
    "seed_type",
    "reason_codes",
    "target_kinds",
    "target_tags",
    "plays_pages",
    "ratingcomments_pages",
    "priority_score",
]

DISCOVERY_EXTRA_FIELDNAMES = [
    "seed_type",
    "reason_codes",
    "target_kinds",
    "target_tags",
    "priority_score",
]
DISCOVERY_RATING_EXT_FIELDNAMES = DISCOVERY_RATING_ROW_FIELDNAMES + DISCOVERY_EXTRA_FIELDNAMES
DISCOVERY_PLAY_EXT_FIELDNAMES = DISCOVERY_PLAY_ROW_FIELDNAMES + DISCOVERY_EXTRA_FIELDNAMES

CANDIDATE_FIELDNAMES = [
    "username",
    "should_enrich",
    "candidate_score",
    "candidate_class",
    "scoring_reason",
    "already_in_baseline",
    "discovery_count",
    "rating_comment_count",
    "play_player_count",
    "source_game_count",
    "source_games",
    "source_game_ranks",
    "source_bgg_ids",
    "source_types",
    "seed_types",
    "target_kinds",
    "target_tags",
]

COHORT_FIELDNAMES = [
    "username",
    "cohort",
    "pool",
    "collection_item_count",
    "selected_game_overlap_count",
    "selected_owned_count",
    "selected_rated_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a diversity-expansion user cohort from seed games outside the first "
            "69 ranks, targeting underrepresented BGG communities while keeping outputs "
            "isolated from reliable_users_batch1."
        )
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--output-label", default="diversity_expansion_batch1")
    parser.add_argument("--baseline-label", default="reliable_users_batch1")
    parser.add_argument("--details-csv", default=DEFAULT_DETAILS_CSV)
    parser.add_argument("--taxonomy-seed-count", type=int, default=180)
    parser.add_argument("--rank-seed-count", type=int, default=90)
    parser.add_argument("--contrast-seed-count", type=int, default=30)
    parser.add_argument("--taxonomy-target-mechanics", type=int, default=15)
    parser.add_argument("--taxonomy-target-categories", type=int, default=15)
    parser.add_argument("--taxonomy-games-per-tag", type=int, default=5)
    parser.add_argument("--ratingcomments-page-size", type=int, default=100)
    parser.add_argument("--max-enriched-users", type=int, default=5000)
    parser.add_argument("--max-runtime-hours", type=float, default=14.0)
    parser.add_argument("--checkpoint-every-users", type=int, default=500)
    parser.add_argument("--throughput-log-every-users", type=int, default=100)
    parser.add_argument("--request-spacing-seconds", type=int, default=7)
    parser.add_argument("--tight-min-collection-items", type=int, default=50)
    parser.add_argument("--tight-min-selected-overlap", type=int, default=10)
    parser.add_argument("--community-min-collection-items", type=int, default=20)
    parser.add_argument("--community-min-selected-overlap", type=int, default=3)
    parser.add_argument("--quality-window", type=int, default=200)
    parser.add_argument("--quality-min-tight-rate", type=float, default=0.15)
    parser.add_argument("--prepare-seeds-only", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--disable-soft-stop", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.discover_additional_users_a")
    started_monotonic = time.monotonic()
    observed_at_utc = datetime.now(timezone.utc).isoformat()

    paths = _build_paths(settings, args.output_label, args.baseline_label)
    _ensure_output_files(paths)

    details_csv = _resolve_project_path(settings, args.details_csv)
    game_rows = _load_game_details(details_csv)
    selected_game_ids = _load_selected_game_ids(paths["baseline_selected_games_csv"])
    baseline_skip_usernames = _load_baseline_usernames(paths["baseline_run_dir"])
    baseline_reliable_usernames = _load_usernames_from_summary(paths["baseline_users_csv"])
    mechanics_by_game, categories_by_game = _build_tag_maps(game_rows)

    logger.info("Loaded %s detailed games.", len(game_rows))
    logger.info("Loaded %s selected baseline games.", len(selected_game_ids))
    logger.info("Loaded %s baseline reliable users.", len(baseline_reliable_usernames))
    logger.info("Loaded %s previously fetched baseline usernames for de-duplication.", len(baseline_skip_usernames))

    state = _load_state(paths["state_json"])
    if not paths["seed_games_csv"].exists() or not _read_csv_dicts(paths["seed_games_csv"]):
        logger.info("Selecting diversity-expansion seed games.")
        target_info = _compute_target_tag_info(
            baseline_edges_csv=paths["baseline_edges_csv"],
            selected_game_ids=selected_game_ids,
            mechanics_by_game=mechanics_by_game,
            categories_by_game=categories_by_game,
            total_baseline_users=len(baseline_reliable_usernames),
            mechanic_target_count=args.taxonomy_target_mechanics,
            category_target_count=args.taxonomy_target_categories,
            logger=logger,
        )
        seed_rows = _select_seed_games(
            game_rows=game_rows,
            target_info=target_info,
            taxonomy_seed_count=args.taxonomy_seed_count,
            rank_seed_count=args.rank_seed_count,
            contrast_seed_count=args.contrast_seed_count,
            taxonomy_games_per_tag=args.taxonomy_games_per_tag,
        )
        _write_csv(paths["seed_games_csv"], seed_rows, SEED_FIELDNAMES)
        _write_json(
            paths["seed_selection_log_json"],
            {
                "observed_at_utc": observed_at_utc,
                "output_label": args.output_label,
                "baseline_label": args.baseline_label,
                "target_info": target_info,
                "seed_count": len(seed_rows),
                "seed_type_counts": _count_by(seed_rows, "seed_type"),
            },
        )
    else:
        target_info = _load_seed_target_info(paths["seed_selection_log_json"])
        seed_rows = _read_seed_rows(paths["seed_games_csv"])
        logger.info("Loaded %s existing seed games from %s.", len(seed_rows), paths["seed_games_csv"])

    _write_selection_thresholds(paths["selection_thresholds_json"], args, target_info)
    _write_metadata(
        paths["metadata_json"],
        args,
        observed_at_utc,
        paths,
        len(seed_rows),
        len(baseline_reliable_usernames),
        len(baseline_skip_usernames),
    )

    if args.prepare_seeds_only:
        _write_stop_reason(paths["stop_reason_txt"], "prepare_seeds_only")
        logger.info("Prepared seed list only. No API requests were sent.")
        return 0

    _write_stop_reason(paths["stop_reason_txt"], "run_in_progress")
    token = get_api_token(settings)
    client = BGGClient(
        base_url=settings["api"]["base_url"],
        token=token,
        use_environment_proxies=False,
        timeout_seconds=settings["api"]["request_timeout_seconds"],
        min_seconds_between_requests=max(args.request_spacing_seconds, settings["api"]["min_seconds_between_requests"]),
        max_retries=settings["api"]["max_retries"],
        retry_backoff_seconds=settings["api"]["retry_backoff_seconds"],
        logger=logger,
    )

    _run_discovery_stage(
        client=client,
        seed_rows=seed_rows,
        paths=paths,
        state=state,
        ratingcomments_page_size=args.ratingcomments_page_size,
        logger=logger,
    )
    _write_state(paths["state_json"], state)

    candidate_rows = _build_and_write_candidates(
        paths=paths,
        baseline_usernames=baseline_skip_usernames,
    )
    logger.info("Candidate users available after discovery: %s", len(candidate_rows))

    if args.discover_only:
        _write_stop_reason(paths["stop_reason_txt"], "discover_only")
        logger.info("Discovery-only mode complete. No user collections were fetched.")
        return 0

    stop_reason = _run_enrichment_stage(
        client=client,
        candidate_rows=candidate_rows,
        paths=paths,
        state=state,
        selected_game_ids=selected_game_ids,
        baseline_paths=paths,
        target_info=target_info,
        mechanics_by_game=mechanics_by_game,
        categories_by_game=categories_by_game,
        max_enriched_users=args.max_enriched_users,
        max_runtime_hours=args.max_runtime_hours,
        started_monotonic=started_monotonic,
        checkpoint_every_users=args.checkpoint_every_users,
        throughput_log_every_users=args.throughput_log_every_users,
        quality_window=args.quality_window,
        quality_min_tight_rate=args.quality_min_tight_rate,
        tight_min_collection_items=args.tight_min_collection_items,
        tight_min_selected_overlap=args.tight_min_selected_overlap,
        community_min_collection_items=args.community_min_collection_items,
        community_min_selected_overlap=args.community_min_selected_overlap,
        disable_soft_stop=args.disable_soft_stop,
        logger=logger,
    )

    _refresh_pool_outputs(
        paths=paths,
        tight_min_collection_items=args.tight_min_collection_items,
        tight_min_selected_overlap=args.tight_min_selected_overlap,
        community_min_collection_items=args.community_min_collection_items,
        community_min_selected_overlap=args.community_min_selected_overlap,
    )
    _write_final_evaluation(
        paths=paths,
        selected_game_ids=selected_game_ids,
        mechanics_by_game=mechanics_by_game,
        categories_by_game=categories_by_game,
        target_info=target_info,
        logger=logger,
    )
    _write_stop_reason(paths["stop_reason_txt"], stop_reason)
    logger.info("Finished diversity expansion run. Stop reason: %s", stop_reason)
    return 0


def _build_paths(settings: dict[str, Any], output_label: str, baseline_label: str) -> dict[str, Path]:
    raw_root = settings["paths"]["raw_data_dir"] / "reliable_users" / output_label
    processed_root = settings["paths"]["processed_data_dir"] / "reliable_users" / output_label
    baseline_root = settings["paths"]["processed_data_dir"] / "reliable_users" / baseline_label
    return {
        "raw_run_dir": raw_root,
        "processed_run_dir": processed_root,
        "discovery_raw_dir": raw_root / "discovery",
        "collections_raw_dir": raw_root / "collections",
        "diversity_snapshots_dir": processed_root / "diversity_snapshots",
        "baseline_run_dir": baseline_root,
        "baseline_selected_games_csv": baseline_root / "selected_games.csv",
        "baseline_users_csv": baseline_root / "reliable_users.csv",
        "baseline_all_summaries_csv": baseline_root / "all_user_summaries.csv",
        "baseline_edges_csv": baseline_root / "reliable_user_collection_edges.csv",
        "seed_games_csv": processed_root / "seed_games.csv",
        "seed_selection_log_json": raw_root / "seed_games_selection_log.json",
        "rating_rows_csv": processed_root / "all_discovery_rating_comment_rows.csv",
        "play_rows_csv": processed_root / "all_discovery_play_rows.csv",
        "candidate_users_csv": processed_root / "all_candidate_users.csv",
        "user_summaries_csv": processed_root / "all_user_summaries.csv",
        "user_edges_csv": processed_root / "all_user_collection_edges.csv",
        "user_errors_csv": processed_root / "all_user_errors.csv",
        "discovery_errors_csv": processed_root / "all_discovery_errors.csv",
        "reliable_users_csv": processed_root / "reliable_users.csv",
        "reliable_edges_csv": processed_root / "reliable_user_collection_edges.csv",
        "community_users_csv": processed_root / "community_users.csv",
        "community_edges_csv": processed_root / "community_user_collection_edges.csv",
        "cohorts_csv": processed_root / "user_cohorts.csv",
        "state_json": processed_root / "pipeline_state.json",
        "metadata_json": processed_root / "metadata.json",
        "selection_thresholds_json": processed_root / "selection_thresholds.json",
        "evaluation_report_txt": processed_root / "diversity_evaluation_report.txt",
        "evaluation_json": processed_root / "diversity_evaluation.json",
        "stop_reason_txt": processed_root / "SCRIPT_STOPPED_REASON.txt",
        "errors_log": processed_root / "cumulative_errors.log",
    }


def _ensure_output_files(paths: dict[str, Path]) -> None:
    for key in ("raw_run_dir", "processed_run_dir", "discovery_raw_dir", "collections_raw_dir", "diversity_snapshots_dir"):
        paths[key].mkdir(parents=True, exist_ok=True)
    _ensure_csv(paths["rating_rows_csv"], DISCOVERY_RATING_EXT_FIELDNAMES)
    _ensure_csv(paths["play_rows_csv"], DISCOVERY_PLAY_EXT_FIELDNAMES)
    _ensure_csv(paths["candidate_users_csv"], CANDIDATE_FIELDNAMES)
    _ensure_csv(paths["user_summaries_csv"], USER_SUMMARY_FIELDNAMES)
    _ensure_csv(paths["user_edges_csv"], USER_COLLECTION_EDGE_FIELDNAMES)
    _ensure_csv(paths["user_errors_csv"], USER_ERROR_FIELDNAMES)
    _ensure_csv(paths["discovery_errors_csv"], DISCOVERY_ERROR_FIELDNAMES)


def _resolve_project_path(settings: dict[str, Any], value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return settings["_meta"]["project_root"] / path


def _load_game_details(details_csv: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with details_csv.open("r", encoding="utf-8", newline="") as file_handle:
        for row in csv.DictReader(file_handle):
            bgg_id = _maybe_int(row.get("bgg_id"))
            rank = _maybe_int(row.get("overall_rank") or row.get("boardgame_rank"))
            if bgg_id is None or rank is None:
                continue
            owned = _maybe_int(row.get("owned")) or 0
            wanting_plus_wishing = _maybe_int(row.get("wanting_plus_wishing")) or 0
            rows.append(
                {
                    **row,
                    "bgg_id": bgg_id,
                    "overall_rank": rank,
                    "average_rating": _maybe_float(row.get("average_rating")) or _maybe_float(row.get("average_rating_from_rank_csv")) or 0.0,
                    "owned": owned,
                    "num_comments": _maybe_int(row.get("num_comments")) or 0,
                    "wanting_plus_wishing": wanting_plus_wishing,
                    "wishlist_interest_ratio": (wanting_plus_wishing / owned) if owned >= 500 else 0.0,
                    "mechanics_list": _split_tags(row.get("mechanics")),
                    "categories_list": _split_tags(row.get("categories")),
                }
            )
    return sorted(rows, key=lambda row: row["overall_rank"])


def _load_selected_game_ids(selected_csv: Path) -> set[int]:
    selected_ids: set[int] = set()
    for row in _read_csv_dicts(selected_csv):
        bgg_id = _maybe_int(row.get("bgg_id"))
        if bgg_id is not None:
            selected_ids.add(bgg_id)
    return selected_ids


def _load_baseline_usernames(baseline_run_dir: Path) -> set[str]:
    usernames: set[str] = set()
    for filename in ("reliable_users.csv", "all_user_summaries.csv"):
        for row in _read_csv_dicts(baseline_run_dir / filename):
            username = (row.get("username") or "").strip()
            if username:
                usernames.add(username)
    return usernames


def _build_tag_maps(game_rows: list[dict[str, Any]]) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    mechanics_by_game = {row["bgg_id"]: list(row["mechanics_list"]) for row in game_rows}
    categories_by_game = {row["bgg_id"]: list(row["categories_list"]) for row in game_rows}
    return mechanics_by_game, categories_by_game


def _compute_target_tag_info(
    *,
    baseline_edges_csv: Path,
    selected_game_ids: set[int],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    total_baseline_users: int,
    mechanic_target_count: int,
    category_target_count: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    logger.info("Computing committed taxonomy coverage for target selection.")
    mechanics = _compute_committed_coverage_for_kind(
        edges_csv=baseline_edges_csv,
        selected_game_ids=selected_game_ids,
        tags_by_game=mechanics_by_game,
        tag_kind="mechanic",
        total_baseline_users=total_baseline_users,
    )
    categories = _compute_committed_coverage_for_kind(
        edges_csv=baseline_edges_csv,
        selected_game_ids=selected_game_ids,
        tags_by_game=categories_by_game,
        tag_kind="category",
        total_baseline_users=total_baseline_users,
    )
    target_mechanics = [
        row
        for row in sorted(mechanics, key=lambda item: (item["committed_user_count"], -item["n_games_with_tag"]))
        if row["n_games_with_tag"] >= 3
    ][:mechanic_target_count]
    target_categories = [
        row
        for row in sorted(categories, key=lambda item: (item["committed_user_count"], -item["n_games_with_tag"]))
        if row["n_games_with_tag"] >= 3
    ][:category_target_count]
    return {
        "committed_user_definition": "user has >= threshold committed edges to games with the tag; committed edge is own=1 or user_rating present or numplays>0",
        "threshold_rule": "2 committed edges for tags with <=5 games, otherwise 3",
        "target_mechanics": target_mechanics,
        "target_categories": target_categories,
    }


def _compute_committed_coverage_for_kind(
    *,
    edges_csv: Path,
    selected_game_ids: set[int],
    tags_by_game: dict[int, list[str]],
    tag_kind: str,
    total_baseline_users: int,
) -> list[dict[str, Any]]:
    games_by_tag: dict[str, set[int]] = defaultdict(set)
    for game_id in selected_game_ids:
        for tag in tags_by_game.get(game_id, []):
            games_by_tag[tag].add(game_id)

    per_user_tag_counts: dict[tuple[str, str], int] = defaultdict(int)
    committed_edges_by_tag: dict[str, int] = defaultdict(int)
    for row in _iter_csv_dicts(edges_csv):
        bgg_id = _maybe_int(row.get("bgg_id"))
        username = row.get("username") or ""
        if bgg_id not in selected_game_ids or not username:
            continue
        if not _is_committed_edge(row):
            continue
        for tag in tags_by_game.get(bgg_id, []):
            per_user_tag_counts[(username, tag)] += 1
            committed_edges_by_tag[tag] += 1

    committed_users_by_tag: dict[str, set[str]] = defaultdict(set)
    for (username, tag), count in per_user_tag_counts.items():
        threshold = _tag_commitment_threshold(len(games_by_tag.get(tag, set())))
        if count >= threshold:
            committed_users_by_tag[tag].add(username)

    rows: list[dict[str, Any]] = []
    for tag, games in games_by_tag.items():
        committed_user_count = len(committed_users_by_tag.get(tag, set()))
        rows.append(
            {
                "tag_kind": tag_kind,
                "tag": tag,
                "n_games_with_tag": len(games),
                "commitment_threshold": _tag_commitment_threshold(len(games)),
                "committed_user_count": committed_user_count,
                "committed_coverage_ratio": round(committed_user_count / total_baseline_users, 6) if total_baseline_users else 0.0,
                "committed_edge_count": committed_edges_by_tag.get(tag, 0),
            }
        )
    return rows


def _select_seed_games(
    *,
    game_rows: list[dict[str, Any]],
    target_info: dict[str, Any],
    taxonomy_seed_count: int,
    rank_seed_count: int,
    contrast_seed_count: int,
    taxonomy_games_per_tag: int,
) -> list[dict[str, Any]]:
    selected: dict[int, dict[str, Any]] = {}
    taxonomy_targets = [
        ("mechanic", row["tag"], index)
        for index, row in enumerate(target_info.get("target_mechanics", []), start=1)
    ] + [
        ("category", row["tag"], index)
        for index, row in enumerate(target_info.get("target_categories", []), start=1)
    ]

    taxonomy_candidates: list[tuple[int, int, int, dict[str, Any], str, str]] = []
    for target_kind, target_tag, target_rank in taxonomy_targets:
        matching_games = [
            row
            for row in game_rows
            if row["overall_rank"] > 69
            and (
                target_tag in row["mechanics_list"]
                if target_kind == "mechanic"
                else target_tag in row["categories_list"]
            )
        ]
        matching_games.sort(key=lambda row: (-row["num_comments"], -row["owned"], row["overall_rank"]))
        for game_rank, game in enumerate(matching_games[:taxonomy_games_per_tag], start=1):
            taxonomy_candidates.append((target_rank, game_rank, -game["num_comments"], game, target_kind, target_tag))

    taxonomy_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    for target_rank, game_rank, _score, game, target_kind, target_tag in taxonomy_candidates:
        if _selected_count_by_type(selected, "taxonomy_deficit") >= taxonomy_seed_count:
            break
        _add_or_update_seed(
            selected,
            game,
            seed_type="taxonomy_deficit",
            reason_code=f"underrep_{target_kind}={target_tag}",
            target_kind=target_kind,
            target_tag=target_tag,
            plays_pages=2,
            ratingcomments_pages=1,
            priority_score=100000 - (target_rank * 100) - game_rank,
        )

    rank_bands = [
        (70, 200, 0.22),
        (201, 500, 0.26),
        (501, 1000, 0.26),
        (1001, 2500, 0.26),
    ]
    remaining_rank_count = rank_seed_count
    for band_index, (start_rank, end_rank, share) in enumerate(rank_bands, start=1):
        count = round(rank_seed_count * share)
        if band_index == len(rank_bands):
            count = remaining_rank_count
        remaining_rank_count -= count
        available = [
            row
            for row in game_rows
            if start_rank <= row["overall_rank"] <= end_rank
            and row["bgg_id"] not in selected
        ]
        for game in _evenly_sample_by_rank(available, count):
            _add_or_update_seed(
                selected,
                game,
                seed_type="rank_stratified",
                reason_code=f"rank_band={start_rank}-{end_rank}",
                target_kind="rank_band",
                target_tag=f"{start_rank}-{end_rank}",
                plays_pages=1,
                ratingcomments_pages=1,
                priority_score=50000 - game["overall_rank"],
            )

    contrast_candidates = [
        row
        for row in game_rows
        if row["overall_rank"] > 69
        and row["owned"] >= 500
        and row["bgg_id"] not in selected
        and row["wishlist_interest_ratio"] > 0
    ]
    contrast_candidates.sort(key=lambda row: (-row["wishlist_interest_ratio"], -row["wanting_plus_wishing"], row["overall_rank"]))
    for game in contrast_candidates[:contrast_seed_count]:
        _add_or_update_seed(
            selected,
            game,
            seed_type="wishlist_contrast",
            reason_code="high_wanting_plus_wishing_to_owned_ratio",
            target_kind="contrast",
            target_tag="wishlist_interest_ratio",
            plays_pages=1,
            ratingcomments_pages=1,
            priority_score=25000 + game["wishlist_interest_ratio"],
        )

    seed_rows = list(selected.values())
    seed_type_order = {"taxonomy_deficit": 0, "rank_stratified": 1, "wishlist_contrast": 2}
    seed_rows.sort(
        key=lambda row: (
            seed_type_order.get(row["seed_type"].split(" | ")[0], 9),
            -float(row["priority_score"]),
            int(row["overall_rank"]),
        )
    )
    for index, row in enumerate(seed_rows, start=1):
        row["seed_index"] = index
    return seed_rows


def _add_or_update_seed(
    selected: dict[int, dict[str, Any]],
    game: dict[str, Any],
    *,
    seed_type: str,
    reason_code: str,
    target_kind: str,
    target_tag: str,
    plays_pages: int,
    ratingcomments_pages: int,
    priority_score: float,
) -> None:
    existing = selected.get(game["bgg_id"])
    if existing is None:
        selected[game["bgg_id"]] = {
            "seed_index": 0,
            "bgg_id": game["bgg_id"],
            "name": game.get("name") or "",
            "overall_rank": game["overall_rank"],
            "average_rating": game["average_rating"],
            "owned": game["owned"],
            "num_comments": game["num_comments"],
            "wanting_plus_wishing": game["wanting_plus_wishing"],
            "wishlist_interest_ratio": round(game["wishlist_interest_ratio"], 6),
            "mechanics": " | ".join(game["mechanics_list"]),
            "categories": " | ".join(game["categories_list"]),
            "seed_type": seed_type,
            "reason_codes": reason_code,
            "target_kinds": target_kind,
            "target_tags": target_tag,
            "plays_pages": plays_pages,
            "ratingcomments_pages": ratingcomments_pages,
            "priority_score": round(priority_score, 6),
        }
        return

    existing["seed_type"] = _append_unique_piece(existing["seed_type"], seed_type)
    existing["reason_codes"] = _append_unique_piece(existing["reason_codes"], reason_code)
    existing["target_kinds"] = _append_unique_piece(existing["target_kinds"], target_kind)
    existing["target_tags"] = _append_unique_piece(existing["target_tags"], target_tag)
    existing["plays_pages"] = max(int(existing["plays_pages"]), plays_pages)
    existing["ratingcomments_pages"] = max(int(existing["ratingcomments_pages"]), ratingcomments_pages)
    existing["priority_score"] = max(float(existing["priority_score"]), priority_score)


def _run_discovery_stage(
    *,
    client: BGGClient,
    seed_rows: list[dict[str, Any]],
    paths: dict[str, Path],
    state: dict[str, Any],
    ratingcomments_page_size: int,
    logger: logging.Logger,
) -> None:
    processed_seed_ids = set(str(item) for item in state.get("processed_discovery_seed_ids", []))
    for seed in seed_rows:
        seed_key = str(seed["bgg_id"])
        if seed_key in processed_seed_ids:
            continue
        logger.info(
            "Discovering candidates from seed %s/%s: rank %s, %s.",
            seed.get("seed_index"),
            len(seed_rows),
            seed.get("overall_rank"),
            seed.get("name"),
        )
        for page in range(1, int(seed["ratingcomments_pages"]) + 1):
            try:
                xml_text = client.get_thing_ratingcomments(
                    int(seed["bgg_id"]),
                    page=page,
                    page_size=ratingcomments_page_size,
                )
                _write_text(
                    paths["discovery_raw_dir"]
                    / f"ratingcomments_seed_{int(seed['seed_index']):04d}_rank_{int(seed['overall_rank']):05d}_page_{page:03d}.xml",
                    xml_text,
                )
                rows = parse_rating_comment_users(
                    xml_text,
                    bgg_id=int(seed["bgg_id"]),
                    game_name=str(seed["name"]),
                    overall_rank=int(seed["overall_rank"]),
                    page=page,
                )
                _append_csv_rows(
                    paths["rating_rows_csv"],
                    [_with_seed_metadata(row, seed) for row in rows],
                    DISCOVERY_RATING_EXT_FIELDNAMES,
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("Failed rating-comment discovery for seed %s page %s.", seed.get("name"), page)
                _append_error(paths["errors_log"], f"ratingcomments seed={seed.get('bgg_id')} page={page}: {exc}")
                _append_csv_rows(
                    paths["discovery_errors_csv"],
                    [
                        {
                            "bgg_id": seed["bgg_id"],
                            "game_name": seed["name"],
                            "overall_rank": seed["overall_rank"],
                            "source_type": "rating_comment",
                            "page": page,
                            "error_message": str(exc),
                        }
                    ],
                    DISCOVERY_ERROR_FIELDNAMES,
                )

        for page in range(1, int(seed["plays_pages"]) + 1):
            try:
                xml_text = client.get_plays_for_item(int(seed["bgg_id"]), page=page)
                _write_text(
                    paths["discovery_raw_dir"]
                    / f"plays_seed_{int(seed['seed_index']):04d}_rank_{int(seed['overall_rank']):05d}_page_{page:03d}.xml",
                    xml_text,
                )
                rows = parse_play_users(
                    xml_text,
                    bgg_id=int(seed["bgg_id"]),
                    game_name=str(seed["name"]),
                    overall_rank=int(seed["overall_rank"]),
                    page=page,
                )
                _append_csv_rows(
                    paths["play_rows_csv"],
                    [_with_seed_metadata(row, seed) for row in rows],
                    DISCOVERY_PLAY_EXT_FIELDNAMES,
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("Failed play discovery for seed %s page %s.", seed.get("name"), page)
                _append_error(paths["errors_log"], f"plays seed={seed.get('bgg_id')} page={page}: {exc}")
                _append_csv_rows(
                    paths["discovery_errors_csv"],
                    [
                        {
                            "bgg_id": seed["bgg_id"],
                            "game_name": seed["name"],
                            "overall_rank": seed["overall_rank"],
                            "source_type": "play_player",
                            "page": page,
                            "error_message": str(exc),
                        }
                    ],
                    DISCOVERY_ERROR_FIELDNAMES,
                )

        processed_seed_ids.add(seed_key)
        state["processed_discovery_seed_ids"] = sorted(processed_seed_ids, key=int)
        state["stage"] = "discovery"
        _write_state(paths["state_json"], state)

    state["stage"] = "discovery_complete"


def _build_and_write_candidates(
    *,
    paths: dict[str, Path],
    baseline_usernames: set[str],
) -> list[dict[str, Any]]:
    discovery_rows = _read_csv_dicts(paths["rating_rows_csv"]) + _read_csv_dicts(paths["play_rows_csv"])
    aggregated: dict[str, dict[str, Any]] = {}
    for row in discovery_rows:
        username = row.get("username") or ""
        if not username:
            continue
        entry = aggregated.setdefault(
            username,
            {
                "username": username,
                "discovery_count": 0,
                "rating_comment_count": 0,
                "play_player_count": 0,
                "source_games": set(),
                "source_game_ranks": set(),
                "source_bgg_ids": set(),
                "source_types": set(),
                "seed_types": set(),
                "target_kinds": set(),
                "target_tags": set(),
            },
        )
        entry["discovery_count"] += 1
        source_type = row.get("source_type")
        if source_type == "rating_comment":
            entry["rating_comment_count"] += 1
        elif source_type == "play_player":
            entry["play_player_count"] += 1
        _set_add_clean(entry["source_games"], row.get("game_name"))
        _set_add_clean(entry["source_game_ranks"], row.get("overall_rank"))
        _set_add_clean(entry["source_bgg_ids"], row.get("bgg_id"))
        _set_add_clean(entry["source_types"], source_type)
        for piece in _split_pipe_list(row.get("seed_type")):
            entry["seed_types"].add(piece)
        for piece in _split_pipe_list(row.get("target_kinds")):
            entry["target_kinds"].add(piece)
        for piece in _split_pipe_list(row.get("target_tags")):
            entry["target_tags"].add(piece)

    rows: list[dict[str, Any]] = []
    for entry in aggregated.values():
        rows.append(_score_candidate(entry, baseline_usernames))
    rows.sort(
        key=lambda row: (
            -int(row["should_enrich"]),
            -float(row["candidate_score"]),
            -int(row["play_player_count"]),
            -int(row["discovery_count"]),
            row["username"].lower(),
        )
    )
    _write_csv(paths["candidate_users_csv"], rows, CANDIDATE_FIELDNAMES)
    return rows


def _score_candidate(entry: dict[str, Any], baseline_usernames: set[str]) -> dict[str, Any]:
    seed_types = set(entry["seed_types"])
    already_in_baseline = entry["username"] in baseline_usernames
    is_taxonomy_candidate = "taxonomy_deficit" in seed_types
    discovery_count = int(entry["discovery_count"])
    play_count = int(entry["play_player_count"])
    rating_count = int(entry["rating_comment_count"])
    source_game_count = len(entry["source_bgg_ids"])

    if already_in_baseline:
        should_enrich = 0
        candidate_class = "skip_existing_baseline"
        scoring_reason = "already_in_baseline"
    elif is_taxonomy_candidate:
        should_enrich = 1
        candidate_class = "underrepresented_taxonomy"
        scoring_reason = "permissive_underrepresented_seed"
    elif play_count >= 1 or discovery_count >= 2:
        should_enrich = 1
        candidate_class = "rank_or_contrast_active"
        scoring_reason = "play_signal_or_multiple_discovery"
    else:
        should_enrich = 0
        candidate_class = "weak_single_signal"
        scoring_reason = "non_target_single_rating_comment"

    score = (
        (100 if is_taxonomy_candidate else 0)
        + play_count * 6
        + rating_count * 2
        + source_game_count * 4
        + (10 if "wishlist_contrast" in seed_types else 0)
    )
    return {
        "username": entry["username"],
        "should_enrich": should_enrich,
        "candidate_score": score,
        "candidate_class": candidate_class,
        "scoring_reason": scoring_reason,
        "already_in_baseline": 1 if already_in_baseline else 0,
        "discovery_count": discovery_count,
        "rating_comment_count": rating_count,
        "play_player_count": play_count,
        "source_game_count": source_game_count,
        "source_games": _join_sorted(entry["source_games"]),
        "source_game_ranks": _join_sorted(entry["source_game_ranks"], numeric=True),
        "source_bgg_ids": _join_sorted(entry["source_bgg_ids"], numeric=True),
        "source_types": _join_sorted(entry["source_types"]),
        "seed_types": _join_sorted(entry["seed_types"]),
        "target_kinds": _join_sorted(entry["target_kinds"]),
        "target_tags": _join_sorted(entry["target_tags"]),
    }


def _run_enrichment_stage(
    *,
    client: BGGClient,
    candidate_rows: list[dict[str, Any]],
    paths: dict[str, Path],
    state: dict[str, Any],
    selected_game_ids: set[int],
    baseline_paths: dict[str, Path],
    target_info: dict[str, Any],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    max_enriched_users: int,
    max_runtime_hours: float,
    started_monotonic: float,
    checkpoint_every_users: int,
    throughput_log_every_users: int,
    quality_window: int,
    quality_min_tight_rate: float,
    tight_min_collection_items: int,
    tight_min_selected_overlap: int,
    community_min_collection_items: int,
    community_min_selected_overlap: int,
    disable_soft_stop: bool,
    logger: logging.Logger,
) -> str:
    summaries = _read_csv_dicts(paths["user_summaries_csv"])
    already_attempted = {row.get("username") for row in summaries if row.get("username")}
    recent_tight_outcomes = deque(
        [
            _summary_passes(row, tight_min_collection_items, tight_min_selected_overlap)
            for row in summaries[-quality_window:]
        ],
        maxlen=quality_window,
    )
    initial_attempt_count = len(already_attempted)
    fetch_started_monotonic = time.monotonic()

    enrichable = [
        row
        for row in candidate_rows
        if str(row.get("should_enrich")) == "1"
        and row.get("username")
        and row.get("username") not in already_attempted
    ]
    logger.info("Starting enrichment with %s pending candidates.", len(enrichable))

    stop_reason = "candidate_pool_exhausted"
    for candidate in enrichable:
        elapsed_hours = (time.monotonic() - started_monotonic) / 3600
        if elapsed_hours >= max_runtime_hours:
            stop_reason = "max_runtime_hours_reached"
            break
        if len(already_attempted) >= max_enriched_users:
            stop_reason = "max_enriched_users_reached"
            break
        if len(recent_tight_outcomes) == quality_window:
            tight_rate = sum(1 for value in recent_tight_outcomes if value) / quality_window
            if tight_rate < quality_min_tight_rate:
                stop_reason = f"quality_collapse_tight_rate_below_{quality_min_tight_rate}"
                break

        username = candidate["username"]
        logger.info("Fetching stats=1 full collection for %s.", username)
        try:
            xml_path = paths["collections_raw_dir"] / f"{_user_file_stem(username)}_collection_all_stats.xml"
            if xml_path.exists():
                xml_text = xml_path.read_text(encoding="utf-8")
            else:
                xml_text = client.get_collection_for_user(username, stats=True)
                _write_text(xml_path, xml_text)
            collection_rows = parse_collection_items(
                xml_text,
                username=username,
                source_label="collection_all",
            )
            summary = build_user_summary(
                _candidate_to_summary_input(candidate),
                collection_rows,
                selected_game_ids=selected_game_ids,
                status="success",
                error_message=None,
            )
            _append_csv_rows(paths["user_summaries_csv"], [summary], USER_SUMMARY_FIELDNAMES)
            _append_csv_rows(paths["user_edges_csv"], collection_rows, USER_COLLECTION_EDGE_FIELDNAMES)
            recent_tight_outcomes.append(
                _summary_passes(summary, tight_min_collection_items, tight_min_selected_overlap)
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to enrich candidate user %s.", username)
            _append_error(paths["errors_log"], f"enrichment user={username}: {exc}")
            failed_summary = build_user_summary(
                _candidate_to_summary_input(candidate),
                [],
                selected_game_ids=selected_game_ids,
                status="failed",
                error_message=str(exc),
            )
            _append_csv_rows(paths["user_summaries_csv"], [failed_summary], USER_SUMMARY_FIELDNAMES)
            _append_csv_rows(
                paths["user_errors_csv"],
                [{"username": username, "error_message": str(exc)}],
                USER_ERROR_FIELDNAMES,
            )
            recent_tight_outcomes.append(False)

        already_attempted.add(username)
        state["stage"] = "enrichment"
        state["enriched_attempt_count"] = len(already_attempted)
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_state(paths["state_json"], state)

        new_attempts = len(already_attempted) - initial_attempt_count
        if throughput_log_every_users > 0 and new_attempts > 0 and new_attempts % throughput_log_every_users == 0:
            elapsed = max(time.monotonic() - fetch_started_monotonic, 1)
            logger.info(
                "Throughput checkpoint: %s new enrichment attempts, %.2f users/hour.",
                new_attempts,
                new_attempts / (elapsed / 3600),
            )

        if checkpoint_every_users > 0 and len(already_attempted) > 0 and len(already_attempted) % checkpoint_every_users == 0:
            _refresh_pool_outputs(
                paths=paths,
                tight_min_collection_items=tight_min_collection_items,
                tight_min_selected_overlap=tight_min_selected_overlap,
                community_min_collection_items=community_min_collection_items,
                community_min_selected_overlap=community_min_selected_overlap,
            )
            snapshot = _write_diversity_snapshot(
                paths=paths,
                selected_game_ids=selected_game_ids,
                mechanics_by_game=mechanics_by_game,
                categories_by_game=categories_by_game,
                target_info=target_info,
                checkpoint_count=len(already_attempted),
                logger=logger,
            )
            if not disable_soft_stop and snapshot.get("soft_stop_recommended"):
                stop_reason = snapshot["soft_stop_reason"]
                break

    return stop_reason


def _write_final_evaluation(
    *,
    paths: dict[str, Path],
    selected_game_ids: set[int],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    target_info: dict[str, Any],
    logger: logging.Logger,
) -> None:
    evaluation = _evaluate_diversity(
        paths=paths,
        selected_game_ids=selected_game_ids,
        mechanics_by_game=mechanics_by_game,
        categories_by_game=categories_by_game,
        target_info=target_info,
        logger=logger,
    )
    _write_json(paths["evaluation_json"], evaluation)
    lines = [
        "=" * 78,
        "DIVERSITY EXPANSION EVALUATION",
        "=" * 78,
        f"core users:      {evaluation['core_metrics']['n_users']}",
        f"expansion users: {evaluation['expansion_metrics']['n_users']}",
        f"merged users:    {evaluation['merged_metrics']['n_users']}",
        f"core density:      {evaluation['core_metrics']['selected_density']:.6f}",
        f"expansion density: {evaluation['expansion_metrics']['selected_density']:.6f}",
        f"merged density:    {evaluation['merged_metrics']['selected_density']:.6f}",
        f"ownership JS divergence core-vs-expansion: {evaluation['ownership_js_divergence_core_vs_expansion']:.6f}",
        "",
        "Target tags with >=20% committed-user improvement:",
        f"  {evaluation['target_tag_summary']['tags_with_20pct_improvement']} / {evaluation['target_tag_summary']['target_tag_count']}",
        "",
        "Top target-tag deltas:",
    ]
    for row in evaluation["target_tag_deltas"][:20]:
        lines.append(
            f"  {row['tag_kind']:<8} {row['tag']:<42} "
            f"core={row['core_committed_users']:<6} expansion={row['expansion_committed_users']:<6} "
            f"relative_gain={row['relative_gain']:.3f}"
        )
    lines.append("=" * 78)
    _write_text(paths["evaluation_report_txt"], "\n".join(lines))


def _write_diversity_snapshot(
    *,
    paths: dict[str, Path],
    selected_game_ids: set[int],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    target_info: dict[str, Any],
    checkpoint_count: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    evaluation = _evaluate_diversity(
        paths=paths,
        selected_game_ids=selected_game_ids,
        mechanics_by_game=mechanics_by_game,
        categories_by_game=categories_by_game,
        target_info=target_info,
        logger=logger,
    )
    previous_snapshots = sorted(paths["diversity_snapshots_dir"].glob("snapshot_*.json"))
    previous_median_gain = None
    if previous_snapshots:
        try:
            previous = json.loads(previous_snapshots[-1].read_text(encoding="utf-8"))
            previous_median_gain = previous.get("target_tag_summary", {}).get("median_relative_gain")
        except json.JSONDecodeError:
            previous_median_gain = None

    summary = evaluation["target_tag_summary"]
    soft_stop_recommended = False
    soft_stop_reason = None
    if summary["target_tag_count"] and summary["share_tags_with_20pct_improvement"] >= 0.75:
        soft_stop_recommended = True
        soft_stop_reason = "target_tags_meaningfully_improved"
    elif (
        len(previous_snapshots) >= 2
        and previous_median_gain is not None
        and summary["median_relative_gain"] - previous_median_gain < 0.05
    ):
        soft_stop_recommended = True
        soft_stop_reason = "diversity_gain_plateau"

    evaluation["checkpoint_count"] = checkpoint_count
    evaluation["soft_stop_recommended"] = soft_stop_recommended
    evaluation["soft_stop_reason"] = soft_stop_reason
    snapshot_path = paths["diversity_snapshots_dir"] / f"snapshot_{checkpoint_count:04d}.json"
    _write_json(snapshot_path, evaluation)
    return evaluation


def _evaluate_diversity(
    *,
    paths: dict[str, Path],
    selected_game_ids: set[int],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    target_info: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    core_users = _load_usernames_from_summary(paths["baseline_users_csv"])
    expansion_users = _load_usernames_from_summary(paths["user_summaries_csv"], success_only=True)
    merged_users = set(core_users) | set(expansion_users)

    core_metrics = _compute_structural_metrics(paths["baseline_edges_csv"], core_users, selected_game_ids)
    expansion_metrics = _compute_structural_metrics(paths["user_edges_csv"], expansion_users, selected_game_ids)
    merged_metrics = _merge_structural_metrics(core_metrics, expansion_metrics, len(merged_users), len(selected_game_ids))

    core_own_counts = _selected_game_own_counts(paths["baseline_edges_csv"], selected_game_ids)
    expansion_own_counts = _selected_game_own_counts(paths["user_edges_csv"], selected_game_ids)
    js_divergence = _jensen_shannon_divergence(
        [core_own_counts.get(game_id, 0) for game_id in sorted(selected_game_ids)],
        [expansion_own_counts.get(game_id, 0) for game_id in sorted(selected_game_ids)],
    )

    target_tags = _target_tag_rows(target_info)
    core_target_counts = _committed_user_counts_for_targets(
        paths["baseline_edges_csv"],
        selected_game_ids,
        mechanics_by_game,
        categories_by_game,
        target_tags,
    )
    expansion_target_counts = _committed_user_counts_for_targets(
        paths["user_edges_csv"],
        selected_game_ids,
        mechanics_by_game,
        categories_by_game,
        target_tags,
    )
    deltas: list[dict[str, Any]] = []
    for tag_row in target_tags:
        key = (tag_row["tag_kind"], tag_row["tag"])
        core_count = core_target_counts.get(key, 0)
        expansion_count = expansion_target_counts.get(key, 0)
        relative_gain = expansion_count / max(core_count, 1)
        deltas.append(
            {
                "tag_kind": tag_row["tag_kind"],
                "tag": tag_row["tag"],
                "core_committed_users": core_count,
                "expansion_committed_users": expansion_count,
                "merged_committed_users": core_count + expansion_count,
                "relative_gain": round(relative_gain, 6),
            }
        )
    deltas.sort(key=lambda row: (-row["relative_gain"], row["tag_kind"], row["tag"]))
    relative_gains = sorted(row["relative_gain"] for row in deltas)
    tags_with_20pct = sum(1 for row in deltas if row["relative_gain"] >= 0.20)
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_metrics": core_metrics,
        "expansion_metrics": expansion_metrics,
        "merged_metrics": merged_metrics,
        "ownership_js_divergence_core_vs_expansion": js_divergence,
        "target_tag_summary": {
            "target_tag_count": len(deltas),
            "tags_with_20pct_improvement": tags_with_20pct,
            "share_tags_with_20pct_improvement": tags_with_20pct / len(deltas) if deltas else 0.0,
            "median_relative_gain": _median(relative_gains),
        },
        "target_tag_deltas": deltas,
    }


def _compute_structural_metrics(edges_csv: Path, usernames: set[str], selected_game_ids: set[int]) -> dict[str, Any]:
    selected_edges = 0
    selected_owned_edges = 0
    selected_rated_edges = 0
    degree_by_user: dict[str, int] = defaultdict(int)
    game_users: dict[int, set[str]] = defaultdict(set)
    for row in _iter_csv_dicts(edges_csv):
        username = row.get("username") or ""
        if usernames and username not in usernames:
            continue
        bgg_id = _maybe_int(row.get("bgg_id"))
        if bgg_id not in selected_game_ids:
            continue
        selected_edges += 1
        degree_by_user[username] += 1
        game_users[bgg_id].add(username)
        if row.get("own") == "1":
            selected_owned_edges += 1
        if row.get("user_rating") not in {None, ""}:
            selected_rated_edges += 1
    n_users = len(usernames) if usernames else len(degree_by_user)
    max_possible = n_users * len(selected_game_ids)
    degrees = sorted(degree_by_user.values())
    return {
        "n_users": n_users,
        "selected_edges": selected_edges,
        "selected_owned_edges": selected_owned_edges,
        "selected_rated_edges": selected_rated_edges,
        "selected_games_touched": len(game_users),
        "selected_density": selected_edges / max_possible if max_possible else 0.0,
        "avg_selected_degree": selected_edges / n_users if n_users else 0.0,
        "median_selected_degree": _median(degrees),
        "max_selected_degree": max(degrees) if degrees else 0,
        "degree_gini": _gini(degrees),
    }


def _merge_structural_metrics(core: dict[str, Any], expansion: dict[str, Any], n_users: int, selected_game_count: int) -> dict[str, Any]:
    selected_edges = core["selected_edges"] + expansion["selected_edges"]
    max_possible = n_users * selected_game_count
    return {
        "n_users": n_users,
        "selected_edges": selected_edges,
        "selected_owned_edges": core["selected_owned_edges"] + expansion["selected_owned_edges"],
        "selected_rated_edges": core["selected_rated_edges"] + expansion["selected_rated_edges"],
        "selected_density": selected_edges / max_possible if max_possible else 0.0,
        "avg_selected_degree": selected_edges / n_users if n_users else 0.0,
    }


def _refresh_pool_outputs(
    *,
    paths: dict[str, Path],
    tight_min_collection_items: int,
    tight_min_selected_overlap: int,
    community_min_collection_items: int,
    community_min_selected_overlap: int,
) -> None:
    summaries = _read_csv_dicts(paths["user_summaries_csv"])
    reliable = [
        row
        for row in summaries
        if _summary_passes(row, tight_min_collection_items, tight_min_selected_overlap)
    ]
    community = [
        row
        for row in summaries
        if _summary_passes(row, community_min_collection_items, community_min_selected_overlap)
    ]
    reliable_names = {row["username"] for row in reliable}
    community_names = {row["username"] for row in community}
    _write_csv(paths["reliable_users_csv"], reliable, USER_SUMMARY_FIELDNAMES)
    _write_csv(paths["community_users_csv"], community, USER_SUMMARY_FIELDNAMES)
    _filter_edges_by_user(paths["user_edges_csv"], paths["reliable_edges_csv"], reliable_names)
    _filter_edges_by_user(paths["user_edges_csv"], paths["community_edges_csv"], community_names)
    _write_cohort_rows(paths["cohorts_csv"], reliable, community)


def _filter_edges_by_user(source_csv: Path, destination_csv: Path, usernames: set[str]) -> None:
    with source_csv.open("r", encoding="utf-8", newline="") as source_handle, destination_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as destination_handle:
        reader = csv.DictReader(source_handle)
        writer = csv.DictWriter(destination_handle, fieldnames=USER_COLLECTION_EDGE_FIELDNAMES)
        writer.writeheader()
        for row in reader:
            if row.get("username") in usernames:
                writer.writerow(row)


def _write_cohort_rows(path: Path, reliable: list[dict[str, Any]], community: list[dict[str, Any]]) -> None:
    reliable_names = {row["username"] for row in reliable}
    community_names = {row["username"] for row in community}
    rows: list[dict[str, Any]] = []
    for row in community:
        username = row["username"]
        rows.append(
            {
                "username": username,
                "cohort": "expanded_diversity_01",
                "pool": "reliable" if username in reliable_names else "community_only",
                "collection_item_count": row.get("collection_item_count"),
                "selected_game_overlap_count": row.get("selected_game_overlap_count"),
                "selected_owned_count": row.get("selected_owned_count"),
                "selected_rated_count": row.get("selected_rated_count"),
            }
        )
    _write_csv(path, rows, COHORT_FIELDNAMES)


def _summary_passes(row: dict[str, Any], min_collection_items: int, min_selected_overlap: int) -> bool:
    return (
        row.get("collection_fetch_status") == "success"
        and (_maybe_int(row.get("collection_item_count")) or 0) >= min_collection_items
        and (_maybe_int(row.get("selected_game_overlap_count")) or 0) >= min_selected_overlap
    )


def _committed_user_counts_for_targets(
    edges_csv: Path,
    selected_game_ids: set[int],
    mechanics_by_game: dict[int, list[str]],
    categories_by_game: dict[int, list[str]],
    target_tags: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    target_lookup = {(row["tag_kind"], row["tag"]) for row in target_tags}
    games_by_key: dict[tuple[str, str], set[int]] = defaultdict(set)
    for game_id in selected_game_ids:
        for tag in mechanics_by_game.get(game_id, []):
            key = ("mechanic", tag)
            if key in target_lookup:
                games_by_key[key].add(game_id)
        for tag in categories_by_game.get(game_id, []):
            key = ("category", tag)
            if key in target_lookup:
                games_by_key[key].add(game_id)

    per_user_tag_counts: dict[tuple[str, tuple[str, str]], int] = defaultdict(int)
    for row in _iter_csv_dicts(edges_csv):
        bgg_id = _maybe_int(row.get("bgg_id"))
        username = row.get("username") or ""
        if bgg_id not in selected_game_ids or not username or not _is_committed_edge(row):
            continue
        for tag in mechanics_by_game.get(bgg_id, []):
            key = ("mechanic", tag)
            if key in target_lookup:
                per_user_tag_counts[(username, key)] += 1
        for tag in categories_by_game.get(bgg_id, []):
            key = ("category", tag)
            if key in target_lookup:
                per_user_tag_counts[(username, key)] += 1

    users_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (username, key), count in per_user_tag_counts.items():
        if count >= _tag_commitment_threshold(len(games_by_key.get(key, set()))):
            users_by_key[key].add(username)
    return {key: len(users) for key, users in users_by_key.items()}


def _selected_game_own_counts(edges_csv: Path, selected_game_ids: set[int]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for row in _iter_csv_dicts(edges_csv):
        bgg_id = _maybe_int(row.get("bgg_id"))
        if bgg_id in selected_game_ids and row.get("own") == "1":
            counts[bgg_id] += 1
    return counts


def _target_tag_rows(target_info: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"tag_kind": "mechanic", "tag": row["tag"]}
        for row in target_info.get("target_mechanics", [])
    ] + [
        {"tag_kind": "category", "tag": row["tag"]}
        for row in target_info.get("target_categories", [])
    ]


def _load_seed_target_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"target_mechanics": [], "target_categories": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("target_info", {"target_mechanics": [], "target_categories": []})


def _read_seed_rows(path: Path) -> list[dict[str, Any]]:
    return _read_csv_dicts(path)


def _with_seed_metadata(row: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "seed_type": seed["seed_type"],
        "reason_codes": seed["reason_codes"],
        "target_kinds": seed["target_kinds"],
        "target_tags": seed["target_tags"],
        "priority_score": seed["priority_score"],
    }


def _candidate_to_summary_input(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": candidate["username"],
        "discovery_count": _maybe_int(candidate.get("discovery_count")) or 0,
        "rating_comment_count": _maybe_int(candidate.get("rating_comment_count")) or 0,
        "play_player_count": _maybe_int(candidate.get("play_player_count")) or 0,
        "source_games": _split_pipe_list(candidate.get("source_games")),
        "source_game_ranks": [
            value
            for value in (_maybe_int(piece) for piece in _split_pipe_list(candidate.get("source_game_ranks")))
            if value is not None
        ],
        "source_types": _split_pipe_list(candidate.get("source_types")),
    }


def _load_usernames_from_summary(path: Path, *, success_only: bool = False) -> set[str]:
    usernames: set[str] = set()
    for row in _read_csv_dicts(path):
        if success_only and row.get("collection_fetch_status") != "success":
            continue
        username = row.get("username") or ""
        if username:
            usernames.add(username)
    return usernames


def _is_committed_edge(row: dict[str, Any]) -> bool:
    return (
        row.get("own") == "1"
        or row.get("user_rating") not in {None, ""}
        or (_maybe_int(row.get("numplays")) or 0) > 0
    )


def _tag_commitment_threshold(n_games_with_tag: int) -> int:
    return 2 if n_games_with_tag <= 5 else 3


def _evenly_sample_by_rank(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not rows:
        return []
    rows = sorted(rows, key=lambda row: row["overall_rank"])
    if count >= len(rows):
        return rows
    if count == 1:
        return [rows[len(rows) // 2]]
    selected_indices = {
        round(index * (len(rows) - 1) / (count - 1))
        for index in range(count)
    }
    return [rows[index] for index in sorted(selected_indices)]


def _selected_count_by_type(selected: dict[int, dict[str, Any]], seed_type: str) -> int:
    return sum(1 for row in selected.values() if seed_type in _split_pipe_list(str(row.get("seed_type"))))


def _append_unique_piece(value: str, piece: str) -> str:
    pieces = _split_pipe_list(value)
    if piece not in pieces:
        pieces.append(piece)
    return " | ".join(pieces)


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [piece.strip() for piece in raw.split("|") if piece.strip()]


def _split_pipe_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    return [piece.strip() for piece in str(raw).split("|") if piece.strip()]


def _set_add_clean(values: set[Any], value: Any) -> None:
    if value in {None, ""}:
        return
    values.add(value)


def _join_sorted(values: set[Any], *, numeric: bool = False) -> str:
    if numeric:
        parsed = []
        for value in values:
            maybe_int = _maybe_int(value)
            if maybe_int is not None:
                parsed.append(maybe_int)
        return " | ".join(str(value) for value in sorted(parsed))
    return " | ".join(str(value) for value in sorted(values, key=lambda item: str(item).lower()))


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for piece in _split_pipe_list(row.get(field)):
            counts[piece] += 1
    return dict(sorted(counts.items()))


def _jensen_shannon_divergence(left_counts: list[int], right_counts: list[int]) -> float:
    left_total = sum(left_counts)
    right_total = sum(right_counts)
    if left_total == 0 or right_total == 0:
        return 0.0
    left = [value / left_total for value in left_counts]
    right = [value / right_total for value in right_counts]
    midpoint = [(l_value + r_value) / 2 for l_value, r_value in zip(left, right)]
    return (_kl_divergence(left, midpoint) + _kl_divergence(right, midpoint)) / 2


def _kl_divergence(values: list[float], reference: list[float]) -> float:
    total = 0.0
    for value, ref in zip(values, reference):
        if value > 0 and ref > 0:
            total += value * math.log(value / ref, 2)
    return total


def _median(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return float(sorted_values[midpoint])
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _gini(values: list[int]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    total = sum(sorted_values)
    if total == 0:
        return 0.0
    weighted_sum = sum((index + 1) * value for index, value in enumerate(sorted_values))
    n = len(sorted_values)
    return (2 * weighted_sum) / (n * total) - (n + 1) / n


def _maybe_int(value: Any) -> int | None:
    if value in {None, "", "N/A", "Not Ranked"}:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _maybe_float(value: Any) -> float | None:
    if value in {None, "", "N/A", "Not Ranked"}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _iter_csv_dicts(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            yield dict(row)


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        return [dict(row) for row in csv.DictReader(file_handle)]


def _ensure_csv(path: Path, fieldnames: list[str]) -> None:
    if path.exists():
        return
    _write_csv(path, [], fieldnames)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalize_for_csv(row, fieldnames))


def _append_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        for row in rows:
            writer.writerow(_normalize_for_csv(row, fieldnames))


def _normalize_for_csv(row: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in fieldnames:
        value = row.get(field)
        if isinstance(value, list):
            normalized[field] = " | ".join(str(piece) for piece in value)
        elif isinstance(value, set):
            normalized[field] = " | ".join(str(piece) for piece in sorted(value))
        else:
            normalized[field] = value
    return normalized


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, ensure_ascii=True))


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "stage": "initialized",
            "processed_discovery_seed_ids": [],
            "enriched_attempt_count": 0,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, state)


def _write_metadata(
    path: Path,
    args: argparse.Namespace,
    observed_at_utc: str,
    paths: dict[str, Path],
    seed_count: int,
    baseline_reliable_user_count: int,
    baseline_dedupe_user_count: int,
) -> None:
    _write_json(
        path,
        {
            "dataset_name": "diversity_expansion_users",
            "observed_at_utc": observed_at_utc,
            "output_label": args.output_label,
            "baseline_label": args.baseline_label,
            "baseline_reliable_user_count": baseline_reliable_user_count,
            "baseline_dedupe_user_count": baseline_dedupe_user_count,
            "seed_count": seed_count,
            "collection_method": (
                "Hybrid diversity expansion: taxonomy-deficit seeds, rank-stratified seeds, "
                "and wishlist-ratio contrast seeds. Candidate users are de-duplicated against "
                "the baseline cohort and enriched with one collection?stats=1 request."
            ),
            "raw_run_dir": str(paths["raw_run_dir"]),
            "processed_run_dir": str(paths["processed_run_dir"]),
        },
    )


def _write_selection_thresholds(path: Path, args: argparse.Namespace, target_info: dict[str, Any]) -> None:
    _write_json(
        path,
        {
            "output_label": args.output_label,
            "seed_selection": {
                "taxonomy_seed_count": args.taxonomy_seed_count,
                "rank_seed_count": args.rank_seed_count,
                "contrast_seed_count": args.contrast_seed_count,
                "taxonomy_games_per_tag": args.taxonomy_games_per_tag,
                "taxonomy_target_mechanics": args.taxonomy_target_mechanics,
                "taxonomy_target_categories": args.taxonomy_target_categories,
            },
            "collection": {
                "request_spacing_seconds": args.request_spacing_seconds,
                "collection_request": "collection?stats=1",
                "max_enriched_users": args.max_enriched_users,
                "max_runtime_hours": args.max_runtime_hours,
            },
            "tight_reliable_pool": {
                "min_collection_items": args.tight_min_collection_items,
                "min_selected_overlap": args.tight_min_selected_overlap,
            },
            "community_pool": {
                "min_collection_items": args.community_min_collection_items,
                "min_selected_overlap": args.community_min_selected_overlap,
            },
            "target_info": target_info,
        },
    )


def _write_stop_reason(path: Path, reason: str) -> None:
    _write_text(
        path,
        f"stopped_at_utc={datetime.now(timezone.utc).isoformat()}\nreason={reason}\n",
    )


def _append_error(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(f"{datetime.now(timezone.utc).isoformat()} | {message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
