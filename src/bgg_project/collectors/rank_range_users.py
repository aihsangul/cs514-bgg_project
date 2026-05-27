from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.candidate_users import (
    _aggregate_candidate_users,
    parse_play_users,
    parse_rating_comment_users,
)
from bgg_project.collectors.mechanics_top25 import RankedGame


USER_SUMMARY_FIELDNAMES = [
    "username",
    "collection_fetch_status",
    "error_message",
    "discovery_count",
    "rating_comment_count",
    "play_player_count",
    "source_game_count",
    "source_games",
    "source_game_ranks",
    "source_types",
    "collection_item_count",
    "owned_count",
    "rated_count",
    "commented_count",
    "wishlist_count",
    "fortrade_count",
    "want_count",
    "wanttoplay_count",
    "wanttobuy_count",
    "prevowned_count",
    "preordered_count",
    "numplays_sum",
    "selected_game_overlap_count",
    "selected_owned_count",
    "selected_rated_count",
    "selected_commented_count",
    "selected_numplays_sum",
    "latest_lastmodified",
]

SELECTED_GAMES_FIELDNAMES = [
    "bgg_id",
    "name",
    "overall_rank",
    "average_rating_from_rank_csv",
]

CANDIDATE_USER_FIELDNAMES = [
    "username",
    "discovery_count",
    "rating_comment_count",
    "play_player_count",
    "source_games",
    "source_game_ranks",
    "source_types",
]

DISCOVERY_RATING_ROW_FIELDNAMES = [
    "username",
    "source_type",
    "bgg_id",
    "game_name",
    "overall_rank",
    "page",
    "rating",
    "comment_has_text",
]

DISCOVERY_PLAY_ROW_FIELDNAMES = [
    "username",
    "source_type",
    "bgg_id",
    "game_name",
    "overall_rank",
    "page",
    "play_id",
    "play_userid",
    "play_date",
    "quantity",
    "length",
]

USER_COLLECTION_EDGE_FIELDNAMES = [
    "username",
    "bgg_id",
    "game_name",
    "year_published",
    "collid",
    "objecttype",
    "subtype",
    "from_collection_all",
    "from_rated_query",
    "own",
    "prevowned",
    "fortrade",
    "want",
    "wanttoplay",
    "wanttobuy",
    "wishlist",
    "wishlistpriority",
    "preordered",
    "lastmodified",
    "user_rating",
    "numplays",
    "comment",
    "thumbnail",
    "image",
]

DISCOVERY_ERROR_FIELDNAMES = ["bgg_id", "game_name", "overall_rank", "source_type", "page", "error_message"]
USER_ERROR_FIELDNAMES = ["username", "error_message"]


class CollectionResponseError(RuntimeError):
    """Raised when the XML API returns a logical collection error document."""


@dataclass(slots=True)
class DetailedUserExtractionArtifacts:
    metadata: dict[str, Any]
    outputs: dict[str, Path]


@dataclass(slots=True)
class DiscoveryResult:
    rating_rows: list[dict[str, Any]]
    play_rows: list[dict[str, Any]]
    discovery_errors: list[dict[str, Any]]
    processed_games: list[RankedGame]
    discovery_stop_rank: int | None
    next_start_rank: int | None
    threshold_reached: bool


def select_ranked_games_in_range(
    ranked_games: list[RankedGame],
    *,
    start_rank: int,
    end_rank: int,
) -> list[RankedGame]:
    if start_rank < 1:
        raise ValueError("start_rank must be 1 or greater.")
    if end_rank < start_rank:
        raise ValueError("end_rank must be greater than or equal to start_rank.")
    return [
        game
        for game in ranked_games
        if start_rank <= game.overall_rank <= end_rank
    ]


def parse_collection_items(
    xml_text: str,
    *,
    username: str,
    source_label: str,
) -> list[dict[str, Any]]:
    root = ET.fromstring(_sanitize_xml_text(xml_text))
    if root.tag == "errors":
        message = "; ".join(
            _clean_text(error.findtext("message")) or "Unknown BGG collection error"
            for error in root.findall("error")
        )
        raise CollectionResponseError(message or "Unknown BGG collection error")

    rows: list[dict[str, Any]] = []
    for item in root.findall("item"):
        status = item.find("status")
        rating_element = item.find("stats/rating")
        comment_element = item.find("comment")

        rows.append(
            {
                "username": username,
                "bgg_id": _to_int(item.attrib.get("objectid")),
                "collid": _to_int(item.attrib.get("collid")),
                "objecttype": _clean_text(item.attrib.get("objecttype")),
                "subtype": _clean_text(item.attrib.get("subtype")),
                "game_name": _clean_text(item.findtext("name")),
                "year_published": _to_int(item.findtext("yearpublished")),
                "thumbnail": _clean_text(item.findtext("thumbnail")),
                "image": _clean_text(item.findtext("image")),
                "own": _to_int(status.attrib.get("own")) if status is not None else None,
                "prevowned": _to_int(status.attrib.get("prevowned")) if status is not None else None,
                "fortrade": _to_int(status.attrib.get("fortrade")) if status is not None else None,
                "want": _to_int(status.attrib.get("want")) if status is not None else None,
                "wanttoplay": _to_int(status.attrib.get("wanttoplay")) if status is not None else None,
                "wanttobuy": _to_int(status.attrib.get("wanttobuy")) if status is not None else None,
                "wishlist": _to_int(status.attrib.get("wishlist")) if status is not None else None,
                "wishlistpriority": _to_int(status.attrib.get("wishlistpriority")) if status is not None else None,
                "preordered": _to_int(status.attrib.get("preordered")) if status is not None else None,
                "lastmodified": _clean_text(status.attrib.get("lastmodified")) if status is not None else None,
                "user_rating": _parse_user_rating(rating_element.attrib.get("value")) if rating_element is not None else None,
                "numplays": _to_int(item.findtext("numplays")),
                "comment": None,
                "from_collection_all": 1 if source_label == "collection_all" else 0,
                "from_rated_query": 1 if source_label == "collection_rated" else 0,
            }
        )

    return rows


def merge_collection_rows(*row_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, int | None], dict[str, Any]] = {}

    for rows in row_groups:
        for row in rows:
            key = (row["username"], row["bgg_id"])
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(row)
                continue

            existing["from_collection_all"] = max(existing.get("from_collection_all", 0), row.get("from_collection_all", 0))
            existing["from_rated_query"] = max(existing.get("from_rated_query", 0), row.get("from_rated_query", 0))

            for field in USER_COLLECTION_EDGE_FIELDNAMES:
                if field in {"from_collection_all", "from_rated_query"}:
                    continue
                if existing.get(field) in {None, ""} and row.get(field) not in {None, ""}:
                    existing[field] = row[field]

            if existing.get("user_rating") is None and row.get("user_rating") is not None:
                existing["user_rating"] = row["user_rating"]
            if existing.get("comment") is None and row.get("comment") is not None:
                existing["comment"] = row["comment"]
            if existing.get("numplays") is None and row.get("numplays") is not None:
                existing["numplays"] = row["numplays"]

    return sorted(
        merged.values(),
        key=lambda row: (
            row["username"].lower(),
            row["bgg_id"] if row["bgg_id"] is not None else 10**12,
            (row.get("game_name") or "").lower(),
        ),
    )


def build_user_summary(
    candidate_user: dict[str, Any],
    collection_rows: list[dict[str, Any]],
    *,
    selected_game_ids: set[int],
    status: str = "success",
    error_message: str | None = None,
) -> dict[str, Any]:
    latest_lastmodified = max(
        (row["lastmodified"] for row in collection_rows if row.get("lastmodified")),
        default=None,
    )

    selected_rows = [
        row for row in collection_rows if row.get("bgg_id") in selected_game_ids
    ]
    return {
        "username": candidate_user["username"],
        "collection_fetch_status": status,
        "error_message": error_message,
        "discovery_count": candidate_user.get("discovery_count", 0),
        "rating_comment_count": candidate_user.get("rating_comment_count", 0),
        "play_player_count": candidate_user.get("play_player_count", 0),
        "source_game_count": len(candidate_user.get("source_games", [])),
        "source_games": list(candidate_user.get("source_games", [])),
        "source_game_ranks": list(candidate_user.get("source_game_ranks", [])),
        "source_types": list(candidate_user.get("source_types", [])),
        "collection_item_count": len(collection_rows),
        "owned_count": _count_rows(collection_rows, "own"),
        "rated_count": sum(1 for row in collection_rows if row.get("user_rating") is not None),
        "commented_count": sum(1 for row in collection_rows if row.get("comment")),
        "wishlist_count": _count_rows(collection_rows, "wishlist"),
        "fortrade_count": _count_rows(collection_rows, "fortrade"),
        "want_count": _count_rows(collection_rows, "want"),
        "wanttoplay_count": _count_rows(collection_rows, "wanttoplay"),
        "wanttobuy_count": _count_rows(collection_rows, "wanttobuy"),
        "prevowned_count": _count_rows(collection_rows, "prevowned"),
        "preordered_count": _count_rows(collection_rows, "preordered"),
        "numplays_sum": sum(row.get("numplays") or 0 for row in collection_rows),
        "selected_game_overlap_count": len(selected_rows),
        "selected_owned_count": _count_rows(selected_rows, "own"),
        "selected_rated_count": sum(1 for row in selected_rows if row.get("user_rating") is not None),
        "selected_commented_count": sum(1 for row in selected_rows if row.get("comment")),
        "selected_numplays_sum": sum(row.get("numplays") or 0 for row in selected_rows),
        "latest_lastmodified": latest_lastmodified,
    }


def build_failed_user_summary(
    candidate_user: dict[str, Any],
    *,
    error_message: str,
) -> dict[str, Any]:
    return build_user_summary(
        candidate_user,
        [],
        selected_game_ids=set(),
        status="failed",
        error_message=error_message,
    )


def run_rank_range_user_extraction(
    client: BGGClient,
    ranked_games: list[RankedGame],
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    start_rank: int,
    end_rank: int,
    ratingcomments_pages_per_game: int,
    ratingcomments_page_size: int,
    plays_pages_per_game: int,
    max_users: int | None = None,
    output_label: str | None = None,
    logger: logging.Logger | None = None,
) -> DetailedUserExtractionArtifacts:
    log = logger or logging.getLogger(__name__)
    observed_at_utc = datetime.now(timezone.utc).isoformat()
    label = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    selected_games = select_ranked_games_in_range(
        ranked_games,
        start_rank=start_rank,
        end_rank=end_rank,
    )
    selected_game_ids = {game.bgg_id for game in selected_games}

    raw_snapshot_dir = raw_data_dir / "rank_range_users" / label
    processed_snapshot_dir = processed_data_dir / "rank_range_users" / label
    discovery_raw_dir = raw_snapshot_dir / "discovery"
    collections_raw_dir = raw_snapshot_dir / "collections"
    discovery_raw_dir.mkdir(parents=True, exist_ok=True)
    collections_raw_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "selected_games_csv_path": processed_snapshot_dir / "selected_games.csv",
        "candidate_users_csv_path": processed_snapshot_dir / "candidate_users.csv",
        "rating_rows_csv_path": processed_snapshot_dir / "discovery_rating_comment_rows.csv",
        "play_rows_csv_path": processed_snapshot_dir / "discovery_play_rows.csv",
        "users_csv_path": processed_snapshot_dir / "users.csv",
        "edges_csv_path": processed_snapshot_dir / "user_collection_edges.csv",
        "discovery_errors_csv_path": processed_snapshot_dir / "discovery_errors.csv",
        "user_errors_csv_path": processed_snapshot_dir / "user_errors.csv",
        "metadata_path": processed_snapshot_dir / "metadata.json",
        "checkpoint_path": processed_snapshot_dir / "resume_checkpoint.json",
        "latest_path": processed_data_dir / "rank_range_users" / "latest.json",
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

    discovery = _collect_candidate_users_by_game(
        client,
        selected_games,
        discovery_raw_dir=discovery_raw_dir,
        ratingcomments_pages_per_game=ratingcomments_pages_per_game,
        ratingcomments_page_size=ratingcomments_page_size,
        plays_pages_per_game=plays_pages_per_game,
        max_users=max_users,
        logger=log,
    )

    candidate_users = _aggregate_candidate_users(discovery.rating_rows + discovery.play_rows)

    _write_csv(outputs["candidate_users_csv_path"], candidate_users, fieldnames=CANDIDATE_USER_FIELDNAMES)
    _write_csv(outputs["rating_rows_csv_path"], discovery.rating_rows, fieldnames=DISCOVERY_RATING_ROW_FIELDNAMES)
    _write_csv(outputs["play_rows_csv_path"], discovery.play_rows, fieldnames=DISCOVERY_PLAY_ROW_FIELDNAMES)
    _write_csv(outputs["discovery_errors_csv_path"], discovery.discovery_errors, fieldnames=DISCOVERY_ERROR_FIELDNAMES)

    _write_csv(outputs["users_csv_path"], [], fieldnames=USER_SUMMARY_FIELDNAMES)
    _write_csv(outputs["edges_csv_path"], [], fieldnames=USER_COLLECTION_EDGE_FIELDNAMES)
    _write_csv(outputs["user_errors_csv_path"], [], fieldnames=USER_ERROR_FIELDNAMES)

    successful_user_count = 0
    failed_user_count = 0
    edge_count = 0

    for index, candidate_user in enumerate(candidate_users, start=1):
        username = candidate_user["username"]
        user_file_stem = _user_file_stem(username)
        log.info(
            "Collecting collection details for user %s (%s/%s).",
            username,
            index,
            len(candidate_users),
        )
        try:
            all_xml = client.get_collection_for_user(username)
            rated_xml = client.get_collection_for_user(username, rated=True)
            _write_text(collections_raw_dir / f"{user_file_stem}_collection_all.xml", all_xml)
            _write_text(collections_raw_dir / f"{user_file_stem}_collection_rated.xml", rated_xml)

            all_rows = parse_collection_items(
                all_xml,
                username=username,
                source_label="collection_all",
            )
            rated_rows = parse_collection_items(
                rated_xml,
                username=username,
                source_label="collection_rated",
            )
            merged_rows = merge_collection_rows(all_rows, rated_rows)
            summary_row = build_user_summary(
                candidate_user,
                merged_rows,
                selected_game_ids=selected_game_ids,
            )
            _append_csv_rows(outputs["users_csv_path"], [summary_row], USER_SUMMARY_FIELDNAMES)
            _append_csv_rows(outputs["edges_csv_path"], merged_rows, USER_COLLECTION_EDGE_FIELDNAMES)
            successful_user_count += 1
            edge_count += len(merged_rows)
        except Exception as exc:  # pragma: no cover - exercised indirectly
            message = str(exc)
            log.exception("Failed to collect details for user %s.", username)
            failed_user_count += 1
            _append_csv_rows(
                outputs["users_csv_path"],
                [build_failed_user_summary(candidate_user, error_message=message)],
                USER_SUMMARY_FIELDNAMES,
            )
            _append_csv_rows(
                outputs["user_errors_csv_path"],
                [{"username": username, "error_message": message}],
                USER_ERROR_FIELDNAMES,
            )

    metadata = {
        "dataset_name": "rank_range_users",
        "collection_method": (
            "Discovered usernames from item-level rating comments and play logs for "
            "games in the selected rank range, then collected each user's full and "
            "rated collection snapshots."
        ),
        "observed_at_utc": observed_at_utc,
        "output_label": label,
        "start_rank": start_rank,
        "end_rank": end_rank,
        "selected_game_count": len(selected_games),
        "processed_game_count": len(discovery.processed_games),
        "processed_game_end_rank": discovery.discovery_stop_rank,
        "next_start_rank": discovery.next_start_rank,
        "user_limit_threshold": max_users,
        "user_limit_reached": discovery.threshold_reached,
        "candidate_user_count": len(candidate_users),
        "successful_user_count": successful_user_count,
        "failed_user_count": failed_user_count,
        "max_users": max_users,
        "rating_comment_row_count": len(discovery.rating_rows),
        "play_row_count": len(discovery.play_rows),
        "discovery_error_count": len(discovery.discovery_errors),
        "user_collection_edge_count": edge_count,
        "raw_snapshot_dir": str(raw_snapshot_dir),
        "processed_snapshot_dir": str(processed_snapshot_dir),
    }
    _write_text(outputs["metadata_path"], json.dumps(metadata, indent=2, ensure_ascii=True))
    _write_text(
        outputs["checkpoint_path"],
        json.dumps(
            {
                "output_label": label,
                "start_rank": start_rank,
                "end_rank": end_rank,
                "processed_game_end_rank": discovery.discovery_stop_rank,
                "next_start_rank": discovery.next_start_rank,
                "user_limit_threshold": max_users,
                "user_limit_reached": discovery.threshold_reached,
                "candidate_user_count": len(candidate_users),
            },
            indent=2,
            ensure_ascii=True,
        ),
    )
    _write_text(outputs["latest_path"], json.dumps(metadata, indent=2, ensure_ascii=True))
    return DetailedUserExtractionArtifacts(metadata=metadata, outputs=outputs)


def _collect_candidate_users_by_game(
    client: BGGClient,
    selected_games: list[RankedGame],
    *,
    discovery_raw_dir: Path,
    ratingcomments_pages_per_game: int,
    ratingcomments_page_size: int,
    plays_pages_per_game: int,
    max_users: int | None,
    logger: logging.Logger,
) -> DiscoveryResult:
    rating_rows: list[dict[str, Any]] = []
    play_rows: list[dict[str, Any]] = []
    discovery_errors: list[dict[str, Any]] = []
    processed_games: list[RankedGame] = []
    discovery_stop_rank: int | None = None
    next_start_rank: int | None = None
    threshold_reached = False

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
                rating_rows.extend(
                    parse_rating_comment_users(
                        xml_text,
                        bgg_id=ranked_game.bgg_id,
                        game_name=ranked_game.name,
                        overall_rank=ranked_game.overall_rank,
                        page=page,
                    )
                )
            except Exception as exc:  # pragma: no cover - exercised indirectly
                message = str(exc)
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
                        "error_message": message,
                    }
                )

        for page in range(1, plays_pages_per_game + 1):
            try:
                xml_text = client.get_plays_for_item(ranked_game.bgg_id, page=page)
                _write_text(
                    discovery_raw_dir / f"plays_rank_{ranked_game.overall_rank:05d}_page_{page:03d}.xml",
                    xml_text,
                )
                play_rows.extend(
                    parse_play_users(
                        xml_text,
                        bgg_id=ranked_game.bgg_id,
                        game_name=ranked_game.name,
                        overall_rank=ranked_game.overall_rank,
                        page=page,
                    )
                )
            except Exception as exc:  # pragma: no cover - exercised indirectly
                message = str(exc)
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
                        "error_message": message,
                    }
                )

        processed_games.append(ranked_game)
        current_unique_users = len(_aggregate_candidate_users(rating_rows + play_rows))
        logger.info(
            "Finished discovery for rank %s (%s). Unique candidate users so far: %s.",
            ranked_game.overall_rank,
            ranked_game.name,
            current_unique_users,
        )

        if max_users is not None and current_unique_users >= max_users:
            threshold_reached = True
            discovery_stop_rank = ranked_game.overall_rank
            next_start_rank = ranked_game.overall_rank + 1
            logger.info(
                "Reached the user threshold (%s) after finishing rank %s (%s). "
                "A future run can resume at rank %s.",
                max_users,
                ranked_game.overall_rank,
                ranked_game.name,
                next_start_rank,
            )
            break

    if discovery_stop_rank is None and processed_games:
        discovery_stop_rank = processed_games[-1].overall_rank
        if discovery_stop_rank < selected_games[-1].overall_rank:
            next_start_rank = discovery_stop_rank + 1

    return DiscoveryResult(
        rating_rows=rating_rows,
        play_rows=play_rows,
        discovery_errors=discovery_errors,
        processed_games=processed_games,
        discovery_stop_rank=discovery_stop_rank,
        next_start_rank=next_start_rank,
        threshold_reached=threshold_reached,
    )


def _count_rows(rows: list[dict[str, Any]], field_name: str) -> int:
    return sum(1 for row in rows if row.get(field_name) == 1)


def _write_csv(
    csv_path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    normalized_rows = [_normalize_csv_row(row) for row in rows]
    if fieldnames is None:
        fieldnames = sorted({key for row in normalized_rows for key in row.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow(row)


def _append_csv_rows(
    csv_path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    if not rows:
        return
    normalized_rows = [_normalize_csv_row(row) for row in rows]
    with csv_path.open("a", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        for row in normalized_rows:
            writer.writerow(row)


def _normalize_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, list):
            normalized[key] = " | ".join(str(entry) for entry in value)
        else:
            normalized[key] = value
    return normalized


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _user_file_stem(username: str) -> str:
    safe_prefix = "".join(
        character if character.isalnum() else "_"
        for character in username.lower()
    ).strip("_")[:40]
    digest = hashlib.sha1(username.encode("utf-8")).hexdigest()[:12]
    if safe_prefix:
        return f"{safe_prefix}_{digest}"
    return digest


def _parse_user_rating(value: Any) -> float | None:
    if value in {None, "", "N/A"}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _sanitize_xml_text(value: str) -> str:
    allowed_control_chars = {"\t", "\n", "\r"}
    return "".join(
        character
        for character in value
        if (
            character in allowed_control_chars
            or ord(character) >= 0x20
        )
    )


def _to_int(value: Any) -> int | None:
    if value in {None, "", "N/A", "Not Ranked"}:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None
