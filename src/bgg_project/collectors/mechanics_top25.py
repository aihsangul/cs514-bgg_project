from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.hotness import parse_thing_items


_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")

_ID_FIELD_ALIASES = {
    "id",
    "objectid",
    "itemid",
    "thingid",
    "gameid",
    "boardgameid",
}

_NAME_FIELD_ALIASES = {
    "name",
    "objectname",
    "primaryname",
    "gamename",
    "boardgamename",
}

_RANK_FIELD_ALIASES = {
    "rank",
    "bggrank",
    "overallrank",
    "boardgamerank",
}

_RATING_FIELD_ALIASES = {
    "average",
    "averagerating",
    "avgrating",
    "geekrating",
}


@dataclass(slots=True)
class RankedGame:
    bgg_id: int
    name: str | None
    overall_rank: int
    average_rating: float | None = None


@dataclass(slots=True)
class MechanicTop25Artifacts:
    snapshot: dict[str, Any]
    thing_xml_batches: list[dict[str, Any]]


def load_ranked_games_from_csv(csv_path: Path) -> list[RankedGame]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Rank CSV not found: {csv_path}. "
            "Place the BGG rank dump at the configured path or pass --rank-csv."
        )

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        header_map = {_normalize_header(name): name for name in reader.fieldnames if name}
        id_field = _resolve_field(header_map, _ID_FIELD_ALIASES, "id")
        name_field = _resolve_optional_field(header_map, _NAME_FIELD_ALIASES)
        rank_field = _resolve_field(header_map, _RANK_FIELD_ALIASES, "overall rank")
        rating_field = _resolve_optional_field(header_map, _RATING_FIELD_ALIASES)

        ranked_games: list[RankedGame] = []
        seen_ids: set[int] = set()
        for row in reader:
            game_id = _to_int(row.get(id_field))
            overall_rank = _to_int(row.get(rank_field))
            if game_id is None or overall_rank is None:
                continue
            if overall_rank <= 0:
                continue
            if game_id in seen_ids:
                continue

            seen_ids.add(game_id)
            ranked_games.append(
                RankedGame(
                    bgg_id=game_id,
                    name=_clean_text(row.get(name_field)) if name_field else None,
                    overall_rank=overall_rank,
                    average_rating=_to_float(row.get(rating_field)) if rating_field else None,
                )
            )

    ranked_games.sort(key=lambda game: (game.overall_rank, game.bgg_id))
    return ranked_games


def collect_mechanic_top25_snapshot(
    client: BGGClient,
    ranked_games: list[RankedGame],
    *,
    top_n_per_mechanic: int,
    thing_batch_size: int,
) -> MechanicTop25Artifacts:
    if thing_batch_size > 20:
        raise ValueError("thing_batch_size must be 20 or less for BGG /thing requests.")

    mechanic_top_games: dict[str, list[dict[str, Any]]] = {}
    selected_games: dict[int, dict[str, Any]] = {}
    thing_xml_batches: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(_chunked(ranked_games, thing_batch_size), start=1):
        item_ids = [game.bgg_id for game in batch]
        xml_text = client.get_things(item_ids, stats=True)
        thing_xml_batches.append(
            {"batch_index": batch_index, "item_ids": item_ids, "xml": xml_text}
        )
        thing_lookup = parse_thing_items(xml_text)

        for ranked_game in batch:
            thing = thing_lookup.get(ranked_game.bgg_id)
            if not thing:
                continue

            mechanics = sorted(thing.get("mechanics", []))
            if not mechanics:
                continue

            merged_record = _build_game_record(ranked_game, thing)
            qualifying_mechanics: list[str] | None = None

            for mechanic in mechanics:
                current = mechanic_top_games.setdefault(mechanic, [])
                if len(current) >= top_n_per_mechanic:
                    continue

                if qualifying_mechanics is None:
                    qualifying_mechanics = selected_games.setdefault(
                        ranked_game.bgg_id,
                        {**merged_record, "qualifying_mechanics": []},
                    )["qualifying_mechanics"]

                current.append(
                    {
                        **merged_record,
                        "mechanic": mechanic,
                        "mechanic_position": len(current) + 1,
                    }
                )
                if mechanic not in qualifying_mechanics:
                    qualifying_mechanics.append(mechanic)

    snapshot = _build_snapshot(
        ranked_games=ranked_games,
        top_n_per_mechanic=top_n_per_mechanic,
        mechanic_top_games=mechanic_top_games,
        selected_games=selected_games,
    )
    return MechanicTop25Artifacts(snapshot=snapshot, thing_xml_batches=thing_xml_batches)


def write_mechanic_top25_snapshot(
    artifacts: MechanicTop25Artifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "mechanics_top25" / timestamp
    processed_snapshot_dir = processed_data_dir / "mechanics_top25" / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    for batch in artifacts.thing_xml_batches:
        batch_path = raw_snapshot_dir / f"thing_batch_{batch['batch_index']:04d}.xml"
        batch_path.write_text(batch["xml"], encoding="utf-8")

    snapshot_json_path = processed_snapshot_dir / "mechanic_top25.json"
    snapshot_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    mechanic_rows = [
        row
        for mechanic in sorted(artifacts.snapshot["mechanics"].keys())
        for row in artifacts.snapshot["mechanics"][mechanic]
    ]
    mechanic_rows_csv_path = processed_snapshot_dir / "mechanic_top25_rows.csv"
    _write_csv(mechanic_rows_csv_path, mechanic_rows)

    selected_games_csv_path = processed_snapshot_dir / "selected_games.csv"
    _write_csv(
        selected_games_csv_path,
        artifacts.snapshot["selected_games"],
    )

    latest_dir = processed_data_dir / "mechanics_top25"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_rows_csv_path = latest_dir / "latest_rows.csv"
    latest_selected_csv_path = latest_dir / "latest_selected_games.csv"

    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_csv(latest_rows_csv_path, mechanic_rows)
    _write_csv(latest_selected_csv_path, artifacts.snapshot["selected_games"])

    return {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "snapshot_json_path": snapshot_json_path,
        "mechanic_rows_csv_path": mechanic_rows_csv_path,
        "selected_games_csv_path": selected_games_csv_path,
        "latest_json_path": latest_json_path,
        "latest_rows_csv_path": latest_rows_csv_path,
        "latest_selected_csv_path": latest_selected_csv_path,
    }


def _build_snapshot(
    *,
    ranked_games: list[RankedGame],
    top_n_per_mechanic: int,
    mechanic_top_games: dict[str, list[dict[str, Any]]],
    selected_games: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).isoformat()
    ordered_mechanics = {
        mechanic: games
        for mechanic, games in sorted(
            mechanic_top_games.items(),
            key=lambda item: (item[0].lower(), item[0]),
        )
    }
    ordered_selected_games = sorted(
        (
            {
                **game,
                "qualifying_mechanics": sorted(game["qualifying_mechanics"]),
            }
            for game in selected_games.values()
        ),
        key=lambda game: (game["overall_rank"], game["bgg_id"]),
    )

    return {
        "dataset_name": "mechanic_top25",
        "collection_method": (
            "Computed from a ranked games CSV plus XML API /thing metadata. "
            "Each mechanic receives the first N games encountered in global rank order."
        ),
        "observed_at_utc": observed_at,
        "top_n_per_mechanic": top_n_per_mechanic,
        "scanned_ranked_games": len(ranked_games),
        "mechanic_count": len(ordered_mechanics),
        "selected_game_count": len(ordered_selected_games),
        "mechanics": ordered_mechanics,
        "selected_games": ordered_selected_games,
    }


def _build_game_record(ranked_game: RankedGame, thing: dict[str, Any]) -> dict[str, Any]:
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
        "average_rating": thing.get("average_rating"),
        "bayes_average_rating": thing.get("bayes_average_rating"),
        "average_weight": thing.get("average_weight"),
        "owned": thing.get("owned"),
        "wanting": thing.get("wanting"),
        "wishing": thing.get("wishing"),
        "num_comments": thing.get("num_comments"),
        "categories": sorted(thing.get("categories", [])),
        "mechanics": sorted(thing.get("mechanics", [])),
        "designers": sorted(thing.get("designers", [])),
        "publishers": sorted(thing.get("publishers", [])),
    }


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


def _chunked(values: list[RankedGame], chunk_size: int) -> list[list[RankedGame]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def _normalize_header(value: str) -> str:
    return _NORMALIZE_PATTERN.sub("", value.lower())


def _resolve_field(
    normalized_header_map: dict[str, str],
    aliases: set[str],
    description: str,
) -> str:
    field_name = _resolve_optional_field(normalized_header_map, aliases)
    if field_name is None:
        raise ValueError(
            f"Could not identify the {description} column in the rank CSV. "
            f"Available columns: {sorted(normalized_header_map.values())}"
        )
    return field_name


def _resolve_optional_field(
    normalized_header_map: dict[str, str],
    aliases: set[str],
) -> str | None:
    for alias in aliases:
        if alias in normalized_header_map:
            return normalized_header_map[alias]
    return None


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
