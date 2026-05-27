from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.mechanics_top25 import RankedGame, load_ranked_games_from_csv


@dataclass(slots=True)
class CandidateUsersArtifacts:
    snapshot: dict[str, Any]
    ratingcomments_xml_pages: list[dict[str, Any]]
    plays_xml_pages: list[dict[str, Any]]


def parse_rating_comment_users(
    xml_text: str,
    *,
    bgg_id: int,
    game_name: str | None,
    overall_rank: int,
    page: int,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []

    for comment in root.findall(".//comments/comment"):
        username = _clean_text(comment.attrib.get("username"))
        if not username:
            continue
        rating = _to_float(comment.attrib.get("rating"))
        value = _clean_text(comment.attrib.get("value"))
        rows.append(
            {
                "username": username,
                "source_type": "rating_comment",
                "bgg_id": bgg_id,
                "game_name": game_name,
                "overall_rank": overall_rank,
                "page": page,
                "rating": rating,
                "comment_has_text": bool(value),
            }
        )

    return rows


def parse_play_users(
    xml_text: str,
    *,
    bgg_id: int,
    game_name: str | None,
    overall_rank: int,
    page: int,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []

    for play in root.findall("play"):
        play_id = _to_int(play.attrib.get("id"))
        play_userid = _to_int(play.attrib.get("userid"))
        play_date = _clean_text(play.attrib.get("date"))
        quantity = _to_int(play.attrib.get("quantity"))
        length = _to_int(play.attrib.get("length"))

        usernames_seen: set[str] = set()
        for player in play.findall("players/player"):
            username = _clean_text(player.attrib.get("username"))
            if not username or username in usernames_seen:
                continue
            usernames_seen.add(username)
            rows.append(
                {
                    "username": username,
                    "source_type": "play_player",
                    "bgg_id": bgg_id,
                    "game_name": game_name,
                    "overall_rank": overall_rank,
                    "page": page,
                    "play_id": play_id,
                    "play_userid": play_userid,
                    "play_date": play_date,
                    "quantity": quantity,
                    "length": length,
                }
            )

    return rows


def collect_candidate_users_snapshot(
    client: BGGClient,
    ranked_games: list[RankedGame],
    *,
    top_ranked_games: int,
    ratingcomments_pages_per_game: int,
    ratingcomments_page_size: int,
    plays_pages_per_game: int,
) -> CandidateUsersArtifacts:
    selected_games = ranked_games[:top_ranked_games]
    rating_rows: list[dict[str, Any]] = []
    play_rows: list[dict[str, Any]] = []
    ratingcomments_xml_pages: list[dict[str, Any]] = []
    plays_xml_pages: list[dict[str, Any]] = []

    for ranked_game in selected_games:
        for page in range(1, ratingcomments_pages_per_game + 1):
            xml_text = client.get_thing_ratingcomments(
                ranked_game.bgg_id,
                page=page,
                page_size=ratingcomments_page_size,
            )
            ratingcomments_xml_pages.append(
                {
                    "bgg_id": ranked_game.bgg_id,
                    "game_name": ranked_game.name,
                    "overall_rank": ranked_game.overall_rank,
                    "page": page,
                    "xml": xml_text,
                }
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

        for page in range(1, plays_pages_per_game + 1):
            xml_text = client.get_plays_for_item(ranked_game.bgg_id, page=page)
            plays_xml_pages.append(
                {
                    "bgg_id": ranked_game.bgg_id,
                    "game_name": ranked_game.name,
                    "overall_rank": ranked_game.overall_rank,
                    "page": page,
                    "xml": xml_text,
                }
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

    aggregated_users = _aggregate_candidate_users(rating_rows + play_rows)
    snapshot = {
        "dataset_name": "candidate_users",
        "collection_method": (
            "Discovered candidate usernames from item-level rating comments and play logs "
            "for the selected top-ranked games."
        ),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "top_ranked_games": top_ranked_games,
        "selected_games": [
            {
                "bgg_id": game.bgg_id,
                "name": game.name,
                "overall_rank": game.overall_rank,
            }
            for game in selected_games
        ],
        "rating_comment_rows": rating_rows,
        "play_rows": play_rows,
        "candidate_users": aggregated_users,
        "candidate_user_count": len(aggregated_users),
    }
    return CandidateUsersArtifacts(
        snapshot=snapshot,
        ratingcomments_xml_pages=ratingcomments_xml_pages,
        plays_xml_pages=plays_xml_pages,
    )


def write_candidate_users_snapshot(
    artifacts: CandidateUsersArtifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "user_candidates" / timestamp
    processed_snapshot_dir = processed_data_dir / "user_candidates" / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    for page_info in artifacts.ratingcomments_xml_pages:
        path = raw_snapshot_dir / (
            f"ratingcomments_rank_{page_info['overall_rank']:02d}_page_{page_info['page']:02d}.xml"
        )
        path.write_text(page_info["xml"], encoding="utf-8")

    for page_info in artifacts.plays_xml_pages:
        path = raw_snapshot_dir / (
            f"plays_rank_{page_info['overall_rank']:02d}_page_{page_info['page']:02d}.xml"
        )
        path.write_text(page_info["xml"], encoding="utf-8")

    snapshot_json_path = processed_snapshot_dir / "candidate_users.json"
    snapshot_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    candidate_users_csv_path = processed_snapshot_dir / "candidate_users.csv"
    rating_rows_csv_path = processed_snapshot_dir / "rating_comment_rows.csv"
    play_rows_csv_path = processed_snapshot_dir / "play_rows.csv"
    _write_csv(candidate_users_csv_path, artifacts.snapshot["candidate_users"])
    _write_csv(rating_rows_csv_path, artifacts.snapshot["rating_comment_rows"])
    _write_csv(play_rows_csv_path, artifacts.snapshot["play_rows"])

    latest_dir = processed_data_dir / "user_candidates"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_users_csv_path = latest_dir / "latest_users.csv"
    latest_rating_rows_csv_path = latest_dir / "latest_rating_rows.csv"
    latest_play_rows_csv_path = latest_dir / "latest_play_rows.csv"
    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_csv(latest_users_csv_path, artifacts.snapshot["candidate_users"])
    _write_csv(latest_rating_rows_csv_path, artifacts.snapshot["rating_comment_rows"])
    _write_csv(latest_play_rows_csv_path, artifacts.snapshot["play_rows"])

    metadata_path = processed_snapshot_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "output_label": timestamp,
                "observed_at_utc": artifacts.snapshot["observed_at_utc"],
                "top_ranked_games": artifacts.snapshot["top_ranked_games"],
                "candidate_user_count": artifacts.snapshot["candidate_user_count"],
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    return {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "snapshot_json_path": snapshot_json_path,
        "candidate_users_csv_path": candidate_users_csv_path,
        "rating_rows_csv_path": rating_rows_csv_path,
        "play_rows_csv_path": play_rows_csv_path,
        "latest_json_path": latest_json_path,
        "latest_users_csv_path": latest_users_csv_path,
        "latest_rating_rows_csv_path": latest_rating_rows_csv_path,
        "latest_play_rows_csv_path": latest_play_rows_csv_path,
        "metadata_path": metadata_path,
    }


def _aggregate_candidate_users(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}

    for row in rows:
        username = row["username"]
        entry = aggregated.setdefault(
            username,
            {
                "username": username,
                "discovery_count": 0,
                "rating_comment_count": 0,
                "play_player_count": 0,
                "source_games": [],
                "source_game_ranks": [],
                "source_types": [],
            },
        )
        entry["discovery_count"] += 1
        source_type = row["source_type"]
        if source_type == "rating_comment":
            entry["rating_comment_count"] += 1
        elif source_type == "play_player":
            entry["play_player_count"] += 1
        if row["game_name"] and row["game_name"] not in entry["source_games"]:
            entry["source_games"].append(row["game_name"])
        if row["overall_rank"] not in entry["source_game_ranks"]:
            entry["source_game_ranks"].append(row["overall_rank"])
        if source_type not in entry["source_types"]:
            entry["source_types"].append(source_type)

    return sorted(
        aggregated.values(),
        key=lambda row: (
            -row["discovery_count"],
            -row["rating_comment_count"],
            -row["play_player_count"],
            row["username"].lower(),
        ),
    )


def _write_csv(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    flattened_rows = [_flatten_row(row) for row in rows]
    fieldnames = sorted({key for row in flattened_rows for key in row.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in flattened_rows:
            writer.writerow(row)


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, list):
            flattened[key] = " | ".join(str(entry) for entry in value)
        else:
            flattened[key] = value
    return flattened


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _to_int(value: Any) -> int | None:
    if value in {None, "", "Not Ranked"}:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
