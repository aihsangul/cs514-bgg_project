from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.hotness import parse_thing_items
from bgg_project.collectors.mechanics_top25 import RankedGame


@dataclass(slots=True)
class TopRankedGamesDetailsArtifacts:
    snapshot: dict[str, Any]
    thing_xml_batches: list[dict[str, Any]]


def collect_top_ranked_games_details_snapshot(
    client: BGGClient,
    ranked_games: list[RankedGame],
    *,
    max_games: int,
    thing_batch_size: int,
) -> TopRankedGamesDetailsArtifacts:
    if thing_batch_size > 20:
        raise ValueError("thing_batch_size must be 20 or less for BGG /thing requests.")

    selected_ranked_games = ranked_games[:max_games]
    detailed_games: list[dict[str, Any]] = []
    thing_xml_batches: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(_chunked(selected_ranked_games, thing_batch_size), start=1):
        item_ids = [game.bgg_id for game in batch]
        xml_text = client.get_things(item_ids, stats=True)
        thing_xml_batches.append(
            {"batch_index": batch_index, "item_ids": item_ids, "xml": xml_text}
        )
        thing_lookup = parse_thing_items(xml_text)

        for ranked_game in batch:
            thing = thing_lookup.get(ranked_game.bgg_id)
            if not thing:
                detailed_games.append(_build_missing_game_record(ranked_game))
                continue
            detailed_games.append(_build_game_record(ranked_game, thing))

    detailed_games.sort(key=lambda game: (game["overall_rank"], game["bgg_id"]))
    snapshot = {
        "dataset_name": "top_ranked_games_details",
        "collection_method": (
            "Collected detailed XML API /thing metadata for the top-ranked games "
            "listed in the BGG rank CSV."
        ),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_game_count": max_games,
        "collected_game_count": len(detailed_games),
        "games": detailed_games,
    }
    return TopRankedGamesDetailsArtifacts(snapshot=snapshot, thing_xml_batches=thing_xml_batches)


def write_top_ranked_games_details_snapshot(
    artifacts: TopRankedGamesDetailsArtifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "top_ranked_games_details" / timestamp
    processed_snapshot_dir = processed_data_dir / "top_ranked_games_details" / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    for batch in artifacts.thing_xml_batches:
        batch_path = raw_snapshot_dir / f"thing_batch_{batch['batch_index']:04d}.xml"
        batch_path.write_text(batch["xml"], encoding="utf-8")

    snapshot_json_path = processed_snapshot_dir / "top_ranked_games_details.json"
    snapshot_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    detailed_games_csv_path = processed_snapshot_dir / "top_ranked_games_details.csv"
    _write_csv(detailed_games_csv_path, artifacts.snapshot["games"])

    latest_dir = processed_data_dir / "top_ranked_games_details"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_csv_path = latest_dir / "latest.csv"
    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_csv(latest_csv_path, artifacts.snapshot["games"])

    metadata_path = processed_snapshot_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "output_label": timestamp,
                "observed_at_utc": artifacts.snapshot["observed_at_utc"],
                "requested_game_count": artifacts.snapshot["requested_game_count"],
                "collected_game_count": artifacts.snapshot["collected_game_count"],
                "thing_batch_count": len(artifacts.thing_xml_batches),
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
        "detailed_games_csv_path": detailed_games_csv_path,
        "latest_json_path": latest_json_path,
        "latest_csv_path": latest_csv_path,
        "metadata_path": metadata_path,
    }


def _build_game_record(ranked_game: RankedGame, thing: dict[str, Any]) -> dict[str, Any]:
    owned = _to_int(thing.get("owned"))
    wanting = _to_int(thing.get("wanting"))
    wishing = _to_int(thing.get("wishing"))
    users_rated = _to_int(thing.get("users_rated"))
    num_comments = _to_int(thing.get("num_comments"))
    total_interest = _safe_add(wanting, wishing)

    return {
        "bgg_id": ranked_game.bgg_id,
        "name": thing.get("primary_name") or ranked_game.name,
        "overall_rank": ranked_game.overall_rank,
        "average_rating_from_rank_csv": ranked_game.average_rating,
        "boardgame_rank": thing.get("boardgame_rank"),
        "year_published": thing.get("year_published"),
        "min_players": thing.get("min_players"),
        "max_players": thing.get("max_players"),
        "playing_time": thing.get("playing_time"),
        "min_playtime": thing.get("min_playtime"),
        "max_playtime": thing.get("max_playtime"),
        "min_age": thing.get("min_age"),
        "average_rating": thing.get("average_rating"),
        "bayes_average_rating": thing.get("bayes_average_rating"),
        "average_weight": thing.get("average_weight"),
        "owned": owned,
        "wanting": wanting,
        "wishing": wishing,
        "users_rated": users_rated,
        "num_comments": num_comments,
        "num_weights": thing.get("num_weights"),
        "wanting_plus_wishing": total_interest,
        "interest_to_owned_ratio": _safe_ratio(total_interest, owned),
        "comments_to_owned_ratio": _safe_ratio(num_comments, owned),
        "comments_to_users_rated_ratio": _safe_ratio(num_comments, users_rated),
        "categories": sorted(thing.get("categories", [])),
        "mechanics": sorted(thing.get("mechanics", [])),
        "designers": sorted(thing.get("designers", [])),
        "publishers": sorted(thing.get("publishers", [])),
        "families": sorted(thing.get("families", [])),
    }


def _build_missing_game_record(ranked_game: RankedGame) -> dict[str, Any]:
    return {
        "bgg_id": ranked_game.bgg_id,
        "name": ranked_game.name,
        "overall_rank": ranked_game.overall_rank,
        "average_rating_from_rank_csv": ranked_game.average_rating,
    }


def _chunked(values: list[RankedGame], chunk_size: int) -> list[list[RankedGame]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


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


def _safe_add(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


def _safe_ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return round(numerator / denominator, 6)


def _to_int(value: Any) -> int | None:
    if value in {None, "", "Not Ranked"}:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None
