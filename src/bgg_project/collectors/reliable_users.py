from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.candidate_users import (
    _aggregate_candidate_users,
    parse_play_users,
    parse_rating_comment_users,
)
from bgg_project.collectors.mechanics_top25 import RankedGame
from bgg_project.collectors.rank_range_users import (
    CANDIDATE_USER_FIELDNAMES,
    DISCOVERY_ERROR_FIELDNAMES,
    DISCOVERY_PLAY_ROW_FIELDNAMES,
    DISCOVERY_RATING_ROW_FIELDNAMES,
    SELECTED_GAMES_FIELDNAMES,
    USER_COLLECTION_EDGE_FIELDNAMES,
    USER_ERROR_FIELDNAMES,
    USER_SUMMARY_FIELDNAMES,
    _normalize_csv_row,
    _user_file_stem,
    _write_text,
    build_user_summary,
    parse_collection_items,
    select_ranked_games_in_range,
)


DISCOVERY_FILENAME_PATTERN = re.compile(r"(?:plays|ratingcomments)_rank_(\d+)_page_\d+\.xml$", re.IGNORECASE)


@dataclass(slots=True)
class ReliableUsersArtifacts:
    metadata: dict[str, Any]
    outputs: dict[str, Path]


@dataclass(slots=True)
class BootstrapState:
    rating_rows: list[dict[str, Any]]
    play_rows: list[dict[str, Any]]
    user_summaries: dict[str, dict[str, Any]]
    next_start_rank: int | None
    full_edges_source_path: Path | None


@dataclass(slots=True)
class ReliableUserRatingsBackfillArtifacts:
    metadata: dict[str, Any]
    outputs: dict[str, Path]


RATINGS_BACKFILL_PROGRESS_FIELDNAMES = [
    "username",
    "fetch_status",
    "rating_item_count",
    "used_cached_xml",
    "error_message",
    "updated_at_utc",
]


def run_reliable_users_pipeline(
    client: BGGClient,
    ranked_games: list[RankedGame],
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    start_rank: int,
    end_rank: int,
    target_established_users: int,
    min_collection_items: int,
    min_selected_overlap_count: int,
    discovery_new_candidate_target: int,
    ratingcomments_pages_per_game: int,
    ratingcomments_page_size: int,
    plays_pages_per_game: int,
    enrichment_batch_size: int,
    bootstrap_run_label: str | None,
    output_label: str | None,
    logger: logging.Logger | None = None,
) -> ReliableUsersArtifacts:
    log = logger or logging.getLogger(__name__)
    observed_at_utc = datetime.now(timezone.utc).isoformat()
    label = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    selected_games = select_ranked_games_in_range(
        ranked_games,
        start_rank=start_rank,
        end_rank=end_rank,
    )
    selected_game_ids = {game.bgg_id for game in selected_games}

    raw_snapshot_dir = raw_data_dir / "reliable_users" / label
    processed_snapshot_dir = processed_data_dir / "reliable_users" / label
    discovery_raw_dir = raw_snapshot_dir / "discovery"
    collections_raw_dir = raw_snapshot_dir / "collections"
    discovery_raw_dir.mkdir(parents=True, exist_ok=True)
    collections_raw_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "selected_games_csv_path": processed_snapshot_dir / "selected_games.csv",
        "all_candidate_users_csv_path": processed_snapshot_dir / "all_candidate_users.csv",
        "all_rating_rows_csv_path": processed_snapshot_dir / "all_discovery_rating_comment_rows.csv",
        "all_play_rows_csv_path": processed_snapshot_dir / "all_discovery_play_rows.csv",
        "all_user_summaries_csv_path": processed_snapshot_dir / "all_user_summaries.csv",
        "all_user_collection_edges_csv_path": processed_snapshot_dir / "all_user_collection_edges.csv",
        "all_user_errors_csv_path": processed_snapshot_dir / "all_user_errors.csv",
        "all_discovery_errors_csv_path": processed_snapshot_dir / "all_discovery_errors.csv",
        "reliable_users_csv_path": processed_snapshot_dir / "reliable_users.csv",
        "reliable_user_collection_edges_csv_path": processed_snapshot_dir / "reliable_user_collection_edges.csv",
        "reliable_rating_rows_csv_path": processed_snapshot_dir / "reliable_discovery_rating_comment_rows.csv",
        "reliable_play_rows_csv_path": processed_snapshot_dir / "reliable_discovery_play_rows.csv",
        "selection_thresholds_path": processed_snapshot_dir / "selection_thresholds.json",
        "state_path": processed_snapshot_dir / "pipeline_state.json",
        "metadata_path": processed_snapshot_dir / "metadata.json",
        "latest_path": processed_data_dir / "reliable_users" / "latest.json",
    }

    _write_csv(
        outputs["selected_games_csv_path"],
        [
            {
                "bgg_id": game.bgg_id,
                "name": game.name,
                "overall_rank": game.overall_rank,
                "average_rating_from_rank_csv": game.average_rating,
            }
            for game in selected_games
        ],
        fieldnames=SELECTED_GAMES_FIELDNAMES,
    )

    if outputs["state_path"].exists():
        state = _load_pipeline_state(outputs)
        rating_rows = state["rating_rows"]
        play_rows = state["play_rows"]
        user_summaries = state["user_summaries"]
        next_start_rank = state["next_start_rank"]
        discovery_errors = state["discovery_errors"]
        user_errors = state["user_errors"]
    else:
        bootstrap = _load_bootstrap_state(
            raw_data_dir=raw_data_dir,
            processed_data_dir=processed_data_dir,
            bootstrap_run_label=bootstrap_run_label,
        )
        rating_rows = bootstrap.rating_rows
        play_rows = bootstrap.play_rows
        user_summaries = bootstrap.user_summaries
        next_start_rank = bootstrap.next_start_rank
        discovery_errors: list[dict[str, Any]] = []
        user_errors: list[dict[str, Any]] = []

        _write_csv(outputs["all_rating_rows_csv_path"], rating_rows, fieldnames=DISCOVERY_RATING_ROW_FIELDNAMES)
        _write_csv(outputs["all_play_rows_csv_path"], play_rows, fieldnames=DISCOVERY_PLAY_ROW_FIELDNAMES)
        _write_csv(
            outputs["all_candidate_users_csv_path"],
            _aggregate_candidate_users(rating_rows + play_rows),
            fieldnames=CANDIDATE_USER_FIELDNAMES,
        )
        _write_csv(
            outputs["all_user_summaries_csv_path"],
            list(user_summaries.values()),
            fieldnames=USER_SUMMARY_FIELDNAMES,
        )
        _copy_or_initialize_edges(
            bootstrap.full_edges_source_path,
            outputs["all_user_collection_edges_csv_path"],
        )
        _write_csv(outputs["all_user_errors_csv_path"], user_errors, fieldnames=USER_ERROR_FIELDNAMES)
        _write_csv(outputs["all_discovery_errors_csv_path"], discovery_errors, fieldnames=DISCOVERY_ERROR_FIELDNAMES)

    repaired_edge_usernames = _sync_missing_full_collection_edges(
        collections_raw_dir=collections_raw_dir,
        summaries=list(user_summaries.values()),
        edges_csv_path=outputs["all_user_collection_edges_csv_path"],
        logger=log,
    )
    if repaired_edge_usernames:
        log.info(
            "Recovered missing edge rows for %s previously fetched users from saved collection XMLs.",
            len(repaired_edge_usernames),
        )

    while True:
        candidate_users = _aggregate_candidate_users(rating_rows + play_rows)
        _write_csv(outputs["all_candidate_users_csv_path"], candidate_users, fieldnames=CANDIDATE_USER_FIELDNAMES)

        established_users = [
            summary
            for summary in user_summaries.values()
            if is_established_user(
                summary,
                min_collection_items=min_collection_items,
                min_selected_overlap_count=min_selected_overlap_count,
            )
        ]
        established_count = len(established_users)
        log.info(
            "Established users so far: %s (target=%s). Fully fetched users: %s. Candidate pool: %s.",
            established_count,
            target_established_users,
            len(user_summaries),
            len(candidate_users),
        )
        if established_count >= target_established_users:
            break

        pending_candidates = [
            candidate
            for candidate in candidate_users
            if candidate["username"] not in user_summaries
        ]
        if pending_candidates:
            batch = pending_candidates[:enrichment_batch_size]
            log.info(
                "Fetching full collection snapshots for the next %s candidate users.",
                len(batch),
            )
            new_summaries, new_user_errors = _enrich_candidate_batch(
                client,
                batch,
                collections_raw_dir=collections_raw_dir,
                selected_game_ids=selected_game_ids,
                logger=log,
            )
            if new_summaries:
                for summary in new_summaries:
                    user_summaries[summary["username"]] = summary
                _append_csv_rows(outputs["all_user_summaries_csv_path"], new_summaries, USER_SUMMARY_FIELDNAMES)
                _append_full_collection_edges(
                    collections_raw_dir=collections_raw_dir,
                    usernames=[summary["username"] for summary in new_summaries],
                    destination_csv_path=outputs["all_user_collection_edges_csv_path"],
                )
            if new_user_errors:
                user_errors.extend(new_user_errors)
                _append_csv_rows(outputs["all_user_errors_csv_path"], new_user_errors, USER_ERROR_FIELDNAMES)

            _write_state(
                outputs["state_path"],
                next_start_rank=next_start_rank,
                rating_rows=rating_rows,
                play_rows=play_rows,
                user_summaries=user_summaries,
                discovery_errors=discovery_errors,
                user_errors=user_errors,
            )
            continue

        if next_start_rank is None or next_start_rank > end_rank:
            log.info("No more ranks remain for discovery and no unenriched candidates remain.")
            break

        log.info(
            "Candidate pool exhausted before reaching the established-user target. "
            "Discovering more candidates starting at rank %s.",
            next_start_rank,
        )
        new_discovery = _discover_additional_candidates(
            client,
            ranked_games=selected_games,
            start_rank=next_start_rank,
            end_rank=end_rank,
            existing_usernames={candidate["username"] for candidate in candidate_users},
            discovery_raw_dir=discovery_raw_dir,
            ratingcomments_pages_per_game=ratingcomments_pages_per_game,
            ratingcomments_page_size=ratingcomments_page_size,
            plays_pages_per_game=plays_pages_per_game,
            new_candidate_target=discovery_new_candidate_target,
            logger=log,
        )
        rating_rows.extend(new_discovery["rating_rows"])
        play_rows.extend(new_discovery["play_rows"])
        discovery_errors.extend(new_discovery["discovery_errors"])
        next_start_rank = new_discovery["next_start_rank"]
        _append_csv_rows(outputs["all_rating_rows_csv_path"], new_discovery["rating_rows"], DISCOVERY_RATING_ROW_FIELDNAMES)
        _append_csv_rows(outputs["all_play_rows_csv_path"], new_discovery["play_rows"], DISCOVERY_PLAY_ROW_FIELDNAMES)
        _append_csv_rows(outputs["all_discovery_errors_csv_path"], new_discovery["discovery_errors"], DISCOVERY_ERROR_FIELDNAMES)
        _write_state(
            outputs["state_path"],
            next_start_rank=next_start_rank,
            rating_rows=rating_rows,
            play_rows=play_rows,
            user_summaries=user_summaries,
            discovery_errors=discovery_errors,
            user_errors=user_errors,
        )

    candidate_users = _aggregate_candidate_users(rating_rows + play_rows)
    established_users = [
        summary
        for summary in user_summaries.values()
        if is_established_user(
            summary,
            min_collection_items=min_collection_items,
            min_selected_overlap_count=min_selected_overlap_count,
        )
    ]
    reliable_usernames = {summary["username"] for summary in established_users}

    _write_csv(outputs["reliable_users_csv_path"], established_users, fieldnames=USER_SUMMARY_FIELDNAMES)
    _filter_csv_by_username(
        outputs["all_user_collection_edges_csv_path"],
        outputs["reliable_user_collection_edges_csv_path"],
        reliable_usernames,
    )
    _filter_csv_by_username(
        outputs["all_rating_rows_csv_path"],
        outputs["reliable_rating_rows_csv_path"],
        reliable_usernames,
    )
    _filter_csv_by_username(
        outputs["all_play_rows_csv_path"],
        outputs["reliable_play_rows_csv_path"],
        reliable_usernames,
    )

    metadata = {
        "dataset_name": "reliable_users",
        "collection_method": (
            "Reused existing discovery/enrichment data when available, discovered "
            "additional candidate users in ranked-game batches, fetched full "
            "collection snapshots only, and kept users that passed a coarse "
            "collection-density threshold."
        ),
        "observed_at_utc": observed_at_utc,
        "output_label": label,
        "bootstrap_run_label": bootstrap_run_label,
        "start_rank": start_rank,
        "end_rank": end_rank,
        "next_start_rank": next_start_rank,
        "target_established_users": target_established_users,
        "min_collection_items": min_collection_items,
        "min_selected_overlap_count": min_selected_overlap_count,
        "candidate_user_count": len(candidate_users),
        "fully_fetched_user_count": len(user_summaries),
        "established_user_count": len(established_users),
        "discovery_rating_row_count": len(rating_rows),
        "discovery_play_row_count": len(play_rows),
        "discovery_error_count": len(discovery_errors),
        "user_error_count": len(user_errors),
        "raw_snapshot_dir": str(raw_snapshot_dir),
        "processed_snapshot_dir": str(processed_snapshot_dir),
    }
    selection_thresholds = {
        "output_label": label,
        "observed_at_utc": observed_at_utc,
        "bootstrap_run_label": bootstrap_run_label,
        "rank_window": {
            "start_rank": start_rank,
            "end_rank": end_rank,
            "next_start_rank": next_start_rank,
        },
        "reliable_user_target": {
            "target_established_users": target_established_users,
        },
        "established_user_rule": {
            "collection_fetch_status_must_equal": "success",
            "min_collection_items": min_collection_items,
            "min_selected_overlap_count": min_selected_overlap_count,
        },
        "batching": {
            "discovery_new_candidate_target": discovery_new_candidate_target,
            "enrichment_batch_size": enrichment_batch_size,
            "ratingcomments_pages_per_game": ratingcomments_pages_per_game,
            "ratingcomments_page_size": ratingcomments_page_size,
            "plays_pages_per_game": plays_pages_per_game,
        },
    }
    _write_text(
        outputs["selection_thresholds_path"],
        json.dumps(selection_thresholds, indent=2, ensure_ascii=True),
    )
    _write_text(outputs["metadata_path"], json.dumps(metadata, indent=2, ensure_ascii=True))
    _write_text(outputs["latest_path"], json.dumps(metadata, indent=2, ensure_ascii=True))
    _write_state(
        outputs["state_path"],
        next_start_rank=next_start_rank,
        rating_rows=rating_rows,
        play_rows=play_rows,
        user_summaries=user_summaries,
        discovery_errors=discovery_errors,
        user_errors=user_errors,
    )
    return ReliableUsersArtifacts(metadata=metadata, outputs=outputs)


def run_reliable_user_ratings_backfill(
    client: BGGClient,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    run_label: str,
    logger: logging.Logger | None = None,
) -> ReliableUserRatingsBackfillArtifacts:
    log = logger or logging.getLogger(__name__)
    observed_at_utc = datetime.now(timezone.utc).isoformat()

    raw_snapshot_dir = raw_data_dir / "reliable_users" / run_label
    processed_snapshot_dir = processed_data_dir / "reliable_users" / run_label
    collections_raw_dir = raw_snapshot_dir / "collections"
    collections_raw_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "selected_games_csv_path": processed_snapshot_dir / "selected_games.csv",
        "reliable_users_csv_path": processed_snapshot_dir / "reliable_users.csv",
        "reliable_user_collection_edges_csv_path": processed_snapshot_dir / "reliable_user_collection_edges.csv",
        "progress_csv_path": processed_snapshot_dir / "user_ratings_backfill_progress.csv",
        "state_path": processed_snapshot_dir / "user_ratings_backfill_state.json",
        "metadata_path": processed_snapshot_dir / "user_ratings_backfill_metadata.json",
    }

    for required_path in (
        outputs["selected_games_csv_path"],
        outputs["reliable_users_csv_path"],
        outputs["reliable_user_collection_edges_csv_path"],
    ):
        if not required_path.exists():
            raise FileNotFoundError(f"Missing expected file: {required_path}")

    selected_game_ids = {
        row["bgg_id"]
        for row in _read_csv_dicts(outputs["selected_games_csv_path"])
        if row.get("bgg_id")
    }
    reliable_users = _read_csv_dicts(outputs["reliable_users_csv_path"])
    target_usernames = [
        row["username"]
        for row in reliable_users
        if row.get("username")
    ]

    progress = _load_backfill_progress(outputs["progress_csv_path"])
    successful_before_run = {
        username
        for username, row in progress.items()
        if row.get("fetch_status") == "success"
    }
    pending_usernames = [
        username
        for username in target_usernames
        if progress.get(username, {}).get("fetch_status") != "success"
    ]

    log.info(
        "Ratings backfill for %s reliable users. Already complete: %s. Remaining: %s.",
        len(target_usernames),
        len(successful_before_run),
        len(pending_usernames),
    )

    for index, username in enumerate(pending_usernames, start=1):
        raw_xml_path = collections_raw_dir / f"{_user_file_stem(username)}_collection_rated_stats.xml"
        used_cached_xml = raw_xml_path.exists()
        try:
            log.info(
                "Collecting rated collection with stats for user %s (%s/%s remaining in this run).",
                username,
                index,
                len(pending_usernames),
            )
            if used_cached_xml:
                rated_xml = raw_xml_path.read_text(encoding="utf-8")
            else:
                rated_xml = client.get_collection_for_user(username, rated=True, stats=True)
                _write_text(raw_xml_path, rated_xml)

            rated_rows = parse_collection_items(
                rated_xml,
                username=username,
                source_label="collection_rated",
            )
            progress[username] = {
                "username": username,
                "fetch_status": "success",
                "rating_item_count": len(rated_rows),
                "used_cached_xml": 1 if used_cached_xml else 0,
                "error_message": None,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # pragma: no cover
            log.exception("Failed to backfill rated collection for user %s.", username)
            progress[username] = {
                "username": username,
                "fetch_status": "failed",
                "rating_item_count": 0,
                "used_cached_xml": 1 if used_cached_xml else 0,
                "error_message": str(exc),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }

        _write_csv(
            outputs["progress_csv_path"],
            list(progress.values()),
            fieldnames=RATINGS_BACKFILL_PROGRESS_FIELDNAMES,
        )
        _write_ratings_backfill_state(
            outputs["state_path"],
            progress=progress,
            target_user_count=len(target_usernames),
        )

    successful_usernames = sorted(
        username
        for username, row in progress.items()
        if row.get("fetch_status") == "success"
    )
    if successful_usernames:
        log.info(
            "Applying ratings backfill to the reliable edge and summary tables for %s users.",
            len(successful_usernames),
        )
        ratings_rows_by_key = _load_backfilled_rating_rows(
            collections_raw_dir=collections_raw_dir,
            usernames=successful_usernames,
            logger=log,
        )
        _rewrite_edges_with_rating_backfill(
            edges_csv_path=outputs["reliable_user_collection_edges_csv_path"],
            ratings_rows_by_key=ratings_rows_by_key,
        )
        _refresh_reliable_user_summaries(
            users_csv_path=outputs["reliable_users_csv_path"],
            edges_csv_path=outputs["reliable_user_collection_edges_csv_path"],
            selected_game_ids=selected_game_ids,
        )

    failure_count = sum(1 for row in progress.values() if row.get("fetch_status") == "failed")
    success_count = len(successful_usernames)
    metadata = {
        "dataset_name": "reliable_user_ratings_backfill",
        "observed_at_utc": observed_at_utc,
        "run_label": run_label,
        "target_user_count": len(target_usernames),
        "successful_backfill_user_count": success_count,
        "failed_backfill_user_count": failure_count,
        "remaining_user_count": max(len(target_usernames) - success_count, 0),
        "raw_snapshot_dir": str(raw_snapshot_dir),
        "processed_snapshot_dir": str(processed_snapshot_dir),
    }
    _write_text(outputs["metadata_path"], json.dumps(metadata, indent=2, ensure_ascii=True))
    _write_ratings_backfill_state(
        outputs["state_path"],
        progress=progress,
        target_user_count=len(target_usernames),
    )
    return ReliableUserRatingsBackfillArtifacts(metadata=metadata, outputs=outputs)


def is_established_user(
    summary: dict[str, Any],
    *,
    min_collection_items: int,
    min_selected_overlap_count: int,
) -> bool:
    if summary.get("collection_fetch_status") != "success":
        return False
    return (
        (summary.get("collection_item_count") or 0) >= min_collection_items
        and (summary.get("selected_game_overlap_count") or 0) >= min_selected_overlap_count
    )


def infer_next_start_rank_from_discovery_dir(discovery_dir: Path) -> int | None:
    if not discovery_dir.exists():
        return None
    ranks: list[int] = []
    for path in discovery_dir.iterdir():
        match = DISCOVERY_FILENAME_PATTERN.match(path.name)
        if match:
            ranks.append(int(match.group(1)))
    if not ranks:
        return None
    return max(ranks) + 1


def _discover_additional_candidates(
    client: BGGClient,
    *,
    ranked_games: list[RankedGame],
    start_rank: int,
    end_rank: int,
    existing_usernames: set[str],
    discovery_raw_dir: Path,
    ratingcomments_pages_per_game: int,
    ratingcomments_page_size: int,
    plays_pages_per_game: int,
    new_candidate_target: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    selected_games = [
        game
        for game in ranked_games
        if start_rank <= game.overall_rank <= end_rank
    ]
    rating_rows: list[dict[str, Any]] = []
    play_rows: list[dict[str, Any]] = []
    discovery_errors: list[dict[str, Any]] = []
    new_usernames: set[str] = set()
    next_start_rank: int | None = None

    for ranked_game in selected_games:
        for page in range(1, ratingcomments_pages_per_game + 1):
            try:
                xml_text = client.get_thing_ratingcomments(
                    ranked_game.bgg_id,
                    page=page,
                    page_size=ratingcomments_page_size,
                )
                _write_text(
                    discovery_raw_dir / f"ratingcomments_rank_{ranked_game.overall_rank:05d}_page_{page:03d}.xml",
                    xml_text,
                )
                rows = parse_rating_comment_users(
                    xml_text,
                    bgg_id=ranked_game.bgg_id,
                    game_name=ranked_game.name,
                    overall_rank=ranked_game.overall_rank,
                    page=page,
                )
                rating_rows.extend(rows)
                new_usernames.update(
                    row["username"]
                    for row in rows
                    if row["username"] not in existing_usernames
                )
            except Exception as exc:  # pragma: no cover
                logger.exception(
                    "Failed to collect rating comments for rank %s (%s), page %s.",
                    ranked_game.overall_rank,
                    ranked_game.name,
                    page,
                )
                discovery_errors.append(
                    {
                        "bgg_id": ranked_game.bgg_id,
                        "game_name": ranked_game.name,
                        "overall_rank": ranked_game.overall_rank,
                        "source_type": "rating_comment",
                        "page": page,
                        "error_message": str(exc),
                    }
                )

        for page in range(1, plays_pages_per_game + 1):
            try:
                xml_text = client.get_plays_for_item(ranked_game.bgg_id, page=page)
                _write_text(
                    discovery_raw_dir / f"plays_rank_{ranked_game.overall_rank:05d}_page_{page:03d}.xml",
                    xml_text,
                )
                rows = parse_play_users(
                    xml_text,
                    bgg_id=ranked_game.bgg_id,
                    game_name=ranked_game.name,
                    overall_rank=ranked_game.overall_rank,
                    page=page,
                )
                play_rows.extend(rows)
                new_usernames.update(
                    row["username"]
                    for row in rows
                    if row["username"] not in existing_usernames
                )
            except Exception as exc:  # pragma: no cover
                logger.exception(
                    "Failed to collect play logs for rank %s (%s), page %s.",
                    ranked_game.overall_rank,
                    ranked_game.name,
                    page,
                )
                discovery_errors.append(
                    {
                        "bgg_id": ranked_game.bgg_id,
                        "game_name": ranked_game.name,
                        "overall_rank": ranked_game.overall_rank,
                        "source_type": "play_player",
                        "page": page,
                        "error_message": str(exc),
                    }
                )

        logger.info(
            "Finished additional discovery for rank %s (%s). New candidate users in this batch so far: %s.",
            ranked_game.overall_rank,
            ranked_game.name,
            len(new_usernames),
        )
        if len(new_usernames) >= new_candidate_target:
            next_start_rank = ranked_game.overall_rank + 1
            logger.info(
                "Reached the new-candidate target (%s) after finishing rank %s (%s). "
                "A future discovery pass can resume at rank %s.",
                new_candidate_target,
                ranked_game.overall_rank,
                ranked_game.name,
                next_start_rank,
            )
            break

    if next_start_rank is None and selected_games:
        highest_rank = selected_games[-1].overall_rank
        if highest_rank < end_rank:
            next_start_rank = highest_rank + 1
    return {
        "rating_rows": rating_rows,
        "play_rows": play_rows,
        "discovery_errors": discovery_errors,
        "next_start_rank": next_start_rank,
    }


def _enrich_candidate_batch(
    client: BGGClient,
    candidates: list[dict[str, Any]],
    *,
    collections_raw_dir: Path,
    selected_game_ids: set[int],
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries: list[dict[str, Any]] = []
    user_errors: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates, start=1):
        username = candidate["username"]
        logger.info(
            "Fetching full collection for user %s (%s/%s in current batch).",
            username,
            index,
            len(candidates),
        )
        try:
            collection_xml = client.get_collection_for_user(username)
            _write_text(
                collections_raw_dir / f"{_user_file_stem(username)}_collection_all.xml",
                collection_xml,
            )
            collection_rows = parse_collection_items(
                collection_xml,
                username=username,
                source_label="collection_all",
            )
            summary = build_user_summary(
                candidate,
                collection_rows,
                selected_game_ids=selected_game_ids,
                status="success",
                error_message=None,
            )
            summaries.append(summary)
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to collect full collection for user %s.", username)
            failure_summary = build_user_summary(
                candidate,
                [],
                selected_game_ids=selected_game_ids,
                status="failed",
                error_message=str(exc),
            )
            summaries.append(failure_summary)
            user_errors.append({"username": username, "error_message": str(exc)})

    return summaries, user_errors


def _append_full_collection_edges(
    *,
    collections_raw_dir: Path,
    usernames: list[str],
    destination_csv_path: Path,
) -> None:
    rows: list[dict[str, Any]] = []
    for username in usernames:
        xml_path = collections_raw_dir / f"{_user_file_stem(username)}_collection_all.xml"
        if not xml_path.exists():
            continue
        try:
            parsed_rows = parse_collection_items(
                xml_path.read_text(encoding="utf-8"),
                username=username,
                source_label="collection_all",
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Skipping malformed saved collection XML for user %s while appending edges.",
                username,
            )
            continue
        rows.extend(parsed_rows)
    _append_csv_rows(destination_csv_path, rows, USER_COLLECTION_EDGE_FIELDNAMES)


def _sync_missing_full_collection_edges(
    *,
    collections_raw_dir: Path,
    summaries: list[dict[str, Any]],
    edges_csv_path: Path,
    logger: logging.Logger,
) -> list[str]:
    existing_usernames = {
        row.get("username")
        for row in _read_csv_dicts(edges_csv_path)
        if row.get("username")
    }
    missing_usernames = [
        summary["username"]
        for summary in summaries
        if summary.get("collection_fetch_status") == "success"
        and summary["username"] not in existing_usernames
        and (collections_raw_dir / f"{_user_file_stem(summary['username'])}_collection_all.xml").exists()
    ]
    if not missing_usernames:
        return []
    logger.info(
        "Synchronizing edge rows for %s successfully fetched users missing from the edge table.",
        len(missing_usernames),
    )
    _append_full_collection_edges(
        collections_raw_dir=collections_raw_dir,
        usernames=missing_usernames,
        destination_csv_path=edges_csv_path,
    )
    return missing_usernames


def _load_backfill_progress(csv_path: Path) -> dict[str, dict[str, Any]]:
    progress: dict[str, dict[str, Any]] = {}
    for row in _read_csv_dicts(csv_path):
        username = row.get("username")
        if not username:
            continue
        progress[username] = {
            "username": username,
            "fetch_status": row.get("fetch_status") or None,
            "rating_item_count": _maybe_int(row.get("rating_item_count")) or 0,
            "used_cached_xml": 1 if _maybe_bool(row.get("used_cached_xml")) else 0,
            "error_message": row.get("error_message") or None,
            "updated_at_utc": row.get("updated_at_utc") or None,
        }
    return progress


def _write_ratings_backfill_state(
    state_path: Path,
    *,
    progress: dict[str, dict[str, Any]],
    target_user_count: int,
) -> None:
    success_count = sum(1 for row in progress.values() if row.get("fetch_status") == "success")
    failure_count = sum(1 for row in progress.values() if row.get("fetch_status") == "failed")
    _write_text(
        state_path,
        json.dumps(
            {
                "target_user_count": target_user_count,
                "successful_backfill_user_count": success_count,
                "failed_backfill_user_count": failure_count,
                "remaining_user_count": max(target_user_count - success_count, 0),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=True,
        ),
    )


def _load_backfilled_rating_rows(
    *,
    collections_raw_dir: Path,
    usernames: list[str],
    logger: logging.Logger,
) -> dict[tuple[str, str], dict[str, Any]]:
    ratings_rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for username in usernames:
        xml_path = collections_raw_dir / f"{_user_file_stem(username)}_collection_rated_stats.xml"
        if not xml_path.exists():
            continue
        try:
            rated_rows = parse_collection_items(
                xml_path.read_text(encoding="utf-8"),
                username=username,
                source_label="collection_rated",
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "Skipping malformed saved rated collection XML for user %s while rebuilding edge rows.",
                username,
            )
            continue
        for row in rated_rows:
            bgg_id = row.get("bgg_id")
            if bgg_id is None:
                continue
            ratings_rows_by_key[(username, str(bgg_id))] = row
    return ratings_rows_by_key


def _merge_edge_row_with_rating_backfill(
    existing_row: dict[str, str],
    rated_row: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing_row)
    merged["from_rated_query"] = 1
    if existing_row.get("user_rating") in {None, ""} and rated_row.get("user_rating") is not None:
        merged["user_rating"] = rated_row["user_rating"]
    for field in USER_COLLECTION_EDGE_FIELDNAMES:
        if field in {"from_collection_all", "from_rated_query"}:
            continue
        if merged.get(field) in {None, ""} and rated_row.get(field) not in {None, ""}:
            merged[field] = rated_row[field]
    return merged


def _rewrite_edges_with_rating_backfill(
    *,
    edges_csv_path: Path,
    ratings_rows_by_key: dict[tuple[str, str], dict[str, Any]],
) -> None:
    temp_path = edges_csv_path.with_suffix(".tmp")
    remaining_keys = set(ratings_rows_by_key)

    with edges_csv_path.open("r", encoding="utf-8", newline="") as source_handle, temp_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as destination_handle:
        reader = csv.DictReader(source_handle)
        writer = csv.DictWriter(destination_handle, fieldnames=USER_COLLECTION_EDGE_FIELDNAMES)
        writer.writeheader()

        for row in reader:
            username = row.get("username") or ""
            bgg_id = row.get("bgg_id") or ""
            key = (username, bgg_id)
            if key in ratings_rows_by_key:
                writer.writerow(_normalize_csv_row(_merge_edge_row_with_rating_backfill(row, ratings_rows_by_key[key])))
                remaining_keys.discard(key)
            else:
                writer.writerow(row)

        for key in sorted(remaining_keys):
            writer.writerow(_normalize_csv_row(ratings_rows_by_key[key]))

    temp_path.replace(edges_csv_path)


def _recompute_summary_collection_metrics(
    *,
    edges_csv_path: Path,
    selected_game_ids: set[str],
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    with edges_csv_path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            username = row.get("username") or ""
            if not username:
                continue
            user_metrics = metrics.setdefault(
                username,
                {
                    "collection_item_count": 0,
                    "owned_count": 0,
                    "rated_count": 0,
                    "commented_count": 0,
                    "wishlist_count": 0,
                    "fortrade_count": 0,
                    "want_count": 0,
                    "wanttoplay_count": 0,
                    "wanttobuy_count": 0,
                    "prevowned_count": 0,
                    "preordered_count": 0,
                    "numplays_sum": 0,
                    "selected_game_overlap_count": 0,
                    "selected_owned_count": 0,
                    "selected_rated_count": 0,
                    "selected_commented_count": 0,
                    "selected_numplays_sum": 0,
                    "latest_lastmodified": None,
                },
            )
            user_metrics["collection_item_count"] += 1
            if row.get("own") == "1":
                user_metrics["owned_count"] += 1
            if row.get("user_rating") not in {None, ""}:
                user_metrics["rated_count"] += 1
            if row.get("comment") not in {None, ""}:
                user_metrics["commented_count"] += 1
            if row.get("wishlist") == "1":
                user_metrics["wishlist_count"] += 1
            if row.get("fortrade") == "1":
                user_metrics["fortrade_count"] += 1
            if row.get("want") == "1":
                user_metrics["want_count"] += 1
            if row.get("wanttoplay") == "1":
                user_metrics["wanttoplay_count"] += 1
            if row.get("wanttobuy") == "1":
                user_metrics["wanttobuy_count"] += 1
            if row.get("prevowned") == "1":
                user_metrics["prevowned_count"] += 1
            if row.get("preordered") == "1":
                user_metrics["preordered_count"] += 1
            user_metrics["numplays_sum"] += _maybe_int(row.get("numplays")) or 0

            lastmodified = row.get("lastmodified") or None
            if lastmodified and (
                user_metrics["latest_lastmodified"] is None or lastmodified > user_metrics["latest_lastmodified"]
            ):
                user_metrics["latest_lastmodified"] = lastmodified

            if (row.get("bgg_id") or "") in selected_game_ids:
                user_metrics["selected_game_overlap_count"] += 1
                if row.get("own") == "1":
                    user_metrics["selected_owned_count"] += 1
                if row.get("user_rating") not in {None, ""}:
                    user_metrics["selected_rated_count"] += 1
                if row.get("comment") not in {None, ""}:
                    user_metrics["selected_commented_count"] += 1
                user_metrics["selected_numplays_sum"] += _maybe_int(row.get("numplays")) or 0

    return metrics


def _refresh_reliable_user_summaries(
    *,
    users_csv_path: Path,
    edges_csv_path: Path,
    selected_game_ids: set[str],
) -> None:
    summary_rows = _read_csv_dicts(users_csv_path)
    metrics_by_user = _recompute_summary_collection_metrics(
        edges_csv_path=edges_csv_path,
        selected_game_ids=selected_game_ids,
    )

    refreshed_rows: list[dict[str, Any]] = []
    for row in summary_rows:
        username = row.get("username") or ""
        metrics = metrics_by_user.get(username, {})
        refreshed_row = dict(row)
        for field, value in metrics.items():
            refreshed_row[field] = value
        refreshed_rows.append(refreshed_row)

    _write_csv(users_csv_path, refreshed_rows, fieldnames=USER_SUMMARY_FIELDNAMES)


def _load_bootstrap_state(
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    bootstrap_run_label: str | None,
) -> BootstrapState:
    if not bootstrap_run_label:
        return BootstrapState(
            rating_rows=[],
            play_rows=[],
            user_summaries={},
            next_start_rank=None,
            full_edges_source_path=None,
        )

    processed_dir = processed_data_dir / "rank_range_users" / bootstrap_run_label
    raw_dir = raw_data_dir / "rank_range_users" / bootstrap_run_label

    rating_rows = _load_discovery_rows(
        processed_dir / "discovery_rating_comment_rows.csv",
        DISCOVERY_RATING_ROW_FIELDNAMES,
    )
    play_rows = _load_discovery_rows(
        processed_dir / "discovery_play_rows.csv",
        DISCOVERY_PLAY_ROW_FIELDNAMES,
    )
    user_summaries = {
        row["username"]: row
        for row in _load_user_summaries(processed_dir / "users.csv")
        if row.get("collection_fetch_status") == "success"
    }
    next_start_rank = infer_next_start_rank_from_discovery_dir(raw_dir / "discovery")
    full_edges_source_path = processed_dir / "user_collection_edges.csv"
    if not full_edges_source_path.exists():
        full_edges_source_path = None
    return BootstrapState(
        rating_rows=rating_rows,
        play_rows=play_rows,
        user_summaries=user_summaries,
        next_start_rank=next_start_rank,
        full_edges_source_path=full_edges_source_path,
    )


def _load_pipeline_state(outputs: dict[str, Path]) -> dict[str, Any]:
    state = json.loads(outputs["state_path"].read_text(encoding="utf-8"))
    return {
        "rating_rows": _load_discovery_rows(
            outputs["all_rating_rows_csv_path"],
            DISCOVERY_RATING_ROW_FIELDNAMES,
        ),
        "play_rows": _load_discovery_rows(
            outputs["all_play_rows_csv_path"],
            DISCOVERY_PLAY_ROW_FIELDNAMES,
        ),
        "user_summaries": {
            row["username"]: row
            for row in _load_user_summaries(outputs["all_user_summaries_csv_path"])
        },
        "next_start_rank": state.get("next_start_rank"),
        "discovery_errors": _read_csv_dicts(outputs["all_discovery_errors_csv_path"]),
        "user_errors": _read_csv_dicts(outputs["all_user_errors_csv_path"]),
    }


def _write_state(
    state_path: Path,
    *,
    next_start_rank: int | None,
    rating_rows: list[dict[str, Any]],
    play_rows: list[dict[str, Any]],
    user_summaries: dict[str, dict[str, Any]],
    discovery_errors: list[dict[str, Any]],
    user_errors: list[dict[str, Any]],
) -> None:
    _write_text(
        state_path,
        json.dumps(
            {
                "next_start_rank": next_start_rank,
                "rating_row_count": len(rating_rows),
                "play_row_count": len(play_rows),
                "user_summary_count": len(user_summaries),
                "discovery_error_count": len(discovery_errors),
                "user_error_count": len(user_errors),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=True,
        ),
    )


def _load_discovery_rows(csv_path: Path, fieldnames: list[str]) -> list[dict[str, Any]]:
    rows = _read_csv_dicts(csv_path)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed_row: dict[str, Any] = {}
        for field in fieldnames:
            value = row.get(field)
            if field in {"bgg_id", "overall_rank", "page", "play_id", "play_userid", "quantity", "length"}:
                parsed_row[field] = _maybe_int(value)
            elif field == "rating":
                parsed_row[field] = _maybe_float(value)
            elif field == "comment_has_text":
                parsed_row[field] = _maybe_bool(value)
            else:
                parsed_row[field] = value or None
        parsed.append(parsed_row)
    return parsed


def _load_user_summaries(csv_path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_dicts(csv_path)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append(
            {
                "username": row.get("username"),
                "collection_fetch_status": row.get("collection_fetch_status"),
                "error_message": row.get("error_message") or None,
                "discovery_count": _maybe_int(row.get("discovery_count")) or 0,
                "rating_comment_count": _maybe_int(row.get("rating_comment_count")) or 0,
                "play_player_count": _maybe_int(row.get("play_player_count")) or 0,
                "source_game_count": _maybe_int(row.get("source_game_count")) or 0,
                "source_games": _split_pipe_list(row.get("source_games")),
                "source_game_ranks": [
                    value
                    for value in (_maybe_int(item) for item in _split_pipe_list(row.get("source_game_ranks")))
                    if value is not None
                ],
                "source_types": _split_pipe_list(row.get("source_types")),
                "collection_item_count": _maybe_int(row.get("collection_item_count")) or 0,
                "owned_count": _maybe_int(row.get("owned_count")) or 0,
                "rated_count": _maybe_int(row.get("rated_count")) or 0,
                "commented_count": _maybe_int(row.get("commented_count")) or 0,
                "wishlist_count": _maybe_int(row.get("wishlist_count")) or 0,
                "fortrade_count": _maybe_int(row.get("fortrade_count")) or 0,
                "want_count": _maybe_int(row.get("want_count")) or 0,
                "wanttoplay_count": _maybe_int(row.get("wanttoplay_count")) or 0,
                "wanttobuy_count": _maybe_int(row.get("wanttobuy_count")) or 0,
                "prevowned_count": _maybe_int(row.get("prevowned_count")) or 0,
                "preordered_count": _maybe_int(row.get("preordered_count")) or 0,
                "numplays_sum": _maybe_int(row.get("numplays_sum")) or 0,
                "selected_game_overlap_count": _maybe_int(row.get("selected_game_overlap_count")) or 0,
                "selected_owned_count": _maybe_int(row.get("selected_owned_count")) or 0,
                "selected_rated_count": _maybe_int(row.get("selected_rated_count")) or 0,
                "selected_commented_count": _maybe_int(row.get("selected_commented_count")) or 0,
                "selected_numplays_sum": _maybe_int(row.get("selected_numplays_sum")) or 0,
                "latest_lastmodified": row.get("latest_lastmodified") or None,
            }
        )
    return parsed


def _read_csv_dicts(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        return [dict(row) for row in reader]


def _filter_csv_by_username(source_path: Path, destination_path: Path, usernames: set[str]) -> None:
    rows = _read_csv_dicts(source_path)
    filtered = [row for row in rows if row.get("username") in usernames]
    if rows:
        _write_csv(destination_path, filtered, fieldnames=list(rows[0].keys()))
    else:
        destination_path.write_text("", encoding="utf-8")


def _copy_or_initialize_edges(source_path: Path | None, destination_path: Path) -> None:
    if source_path is not None and source_path.exists():
        destination_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        return
    _write_csv(destination_path, [], fieldnames=USER_COLLECTION_EDGE_FIELDNAMES)


def _write_csv(csv_path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    normalized_rows = [_normalize_csv_row(row) for row in rows]
    if fieldnames is None:
        fieldnames = sorted({key for row in normalized_rows for key in row.keys()})
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow(row)


def _append_csv_rows(csv_path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    if not rows:
        return
    normalized_rows = [_normalize_csv_row(row) for row in rows]
    with csv_path.open("a", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        for row in normalized_rows:
            writer.writerow(row)


def _split_pipe_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _maybe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value))
    except ValueError:
        try:
            return int(float(str(value)))
        except ValueError:
            return None


def _maybe_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _maybe_bool(value: Any) -> bool | None:
    if value in {None, ""}:
        return None
    return str(value).strip().lower() in {"1", "true", "yes"}
