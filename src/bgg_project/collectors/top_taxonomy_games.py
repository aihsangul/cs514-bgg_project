from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

import requests

from bgg_project.bgg_client import BGGClient
from bgg_project.collectors.hotness import parse_thing_items


GEEKDO_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "bgg-project-academic-research/0.1",
}


@dataclass(slots=True)
class TaxonomyRecord:
    taxonomy_type: str
    taxonomy_id: int
    name: str
    slug: str | None
    url: str


@dataclass(slots=True)
class TopTaxonomyGamesArtifacts:
    snapshot: dict[str, Any]
    thing_xml_batches: list[dict[str, Any]]


class GeekdoLinkedItemsClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int = 30,
        use_environment_proxies: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.trust_env = use_environment_proxies
        self.session.headers.update(GEEKDO_HEADERS)

    def get_top_linked_items(
        self,
        taxonomy: TaxonomyRecord,
        *,
        top_n: int,
        sort: str,
    ) -> list[dict[str, Any]]:
        params = {
            "ajax": 1,
            "linkdata_index": "boardgame",
            "nosession": 1,
            "objectid": taxonomy.taxonomy_id,
            "objecttype": "property",
            "pageid": 1,
            "showcount": top_n,
            "sort": sort,
            "subtype": taxonomy.taxonomy_type,
        }
        url = f"{self.base_url}/geekitem/linkeditems"
        self.logger.info("Requesting linked items for %s (%s)", taxonomy.name, taxonomy.taxonomy_type)
        response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError(
                f"Unexpected linked-items payload for taxonomy {taxonomy.taxonomy_id}: {payload}"
            )
        return [item for item in items if isinstance(item, dict)]


def load_taxonomy_records_from_csv(csv_path: Path) -> list[TaxonomyRecord]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        records: list[TaxonomyRecord] = []
        for row in reader:
            taxonomy_id = _to_int(row.get("taxonomy_id"))
            taxonomy_type = _clean_text(row.get("taxonomy_type"))
            name = _clean_text(row.get("name"))
            url = _clean_text(row.get("url"))
            if taxonomy_id is None or taxonomy_type is None or name is None or url is None:
                continue
            records.append(
                TaxonomyRecord(
                    taxonomy_type=taxonomy_type,
                    taxonomy_id=taxonomy_id,
                    name=name,
                    slug=_clean_text(row.get("slug")),
                    url=url,
                )
            )
    return records


def collect_top_taxonomy_games_snapshot(
    geekdo_client: GeekdoLinkedItemsClient,
    thing_client: BGGClient,
    *,
    mechanics: list[TaxonomyRecord],
    categories: list[TaxonomyRecord],
    top_n_per_taxonomy: int,
    sort: str,
    thing_batch_size: int,
) -> TopTaxonomyGamesArtifacts:
    mechanic_rows = _collect_rows_for_taxonomies(
        geekdo_client,
        mechanics,
        top_n_per_taxonomy=top_n_per_taxonomy,
        sort=sort,
    )
    category_rows = _collect_rows_for_taxonomies(
        geekdo_client,
        categories,
        top_n_per_taxonomy=top_n_per_taxonomy,
        sort=sort,
    )

    selected_game_ids = sorted(
        {
            row["bgg_id"]
            for row in mechanic_rows + category_rows
            if row.get("bgg_id") is not None
        }
    )

    thing_xml_batches: list[dict[str, Any]] = []
    thing_lookup: dict[int, dict[str, Any]] = {}
    for batch_index, item_ids in enumerate(_chunked(selected_game_ids, thing_batch_size), start=1):
        xml_text = thing_client.get_things(item_ids, stats=True)
        thing_xml_batches.append(
            {"batch_index": batch_index, "item_ids": item_ids, "xml": xml_text}
        )
        thing_lookup.update(parse_thing_items(xml_text))

    enriched_mechanics = [_merge_linked_item_with_thing(row, thing_lookup) for row in mechanic_rows]
    enriched_categories = [_merge_linked_item_with_thing(row, thing_lookup) for row in category_rows]
    selected_games = _build_selected_games(enriched_mechanics + enriched_categories)

    snapshot = {
        "dataset_name": "top_taxonomy_games",
        "collection_method": (
            "Collected the top linked board games for each mechanic and category "
            "from BGG's linked-items endpoint, then enriched unique games with XML API /thing data."
        ),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "top_n_per_taxonomy": top_n_per_taxonomy,
        "sort": sort,
        "mechanic_count": len(mechanics),
        "category_count": len(categories),
        "mechanic_rows": enriched_mechanics,
        "category_rows": enriched_categories,
        "selected_game_count": len(selected_games),
        "selected_games": selected_games,
    }

    return TopTaxonomyGamesArtifacts(snapshot=snapshot, thing_xml_batches=thing_xml_batches)


def write_top_taxonomy_games_snapshot(
    artifacts: TopTaxonomyGamesArtifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "top_taxonomy_games" / timestamp
    processed_snapshot_dir = processed_data_dir / "top_taxonomy_games" / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    for batch in artifacts.thing_xml_batches:
        batch_path = raw_snapshot_dir / f"thing_batch_{batch['batch_index']:03d}.xml"
        batch_path.write_text(batch["xml"], encoding="utf-8")

    snapshot_json_path = processed_snapshot_dir / "top_taxonomy_games.json"
    snapshot_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    mechanics_csv_path = processed_snapshot_dir / "mechanic_top_games.csv"
    categories_csv_path = processed_snapshot_dir / "category_top_games.csv"
    selected_games_csv_path = processed_snapshot_dir / "selected_games.csv"
    _write_csv(mechanics_csv_path, artifacts.snapshot["mechanic_rows"])
    _write_csv(categories_csv_path, artifacts.snapshot["category_rows"])
    _write_csv(selected_games_csv_path, artifacts.snapshot["selected_games"])

    latest_dir = processed_data_dir / "top_taxonomy_games"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_mechanics_csv_path = latest_dir / "latest_mechanics.csv"
    latest_categories_csv_path = latest_dir / "latest_categories.csv"
    latest_selected_games_csv_path = latest_dir / "latest_selected_games.csv"
    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_csv(latest_mechanics_csv_path, artifacts.snapshot["mechanic_rows"])
    _write_csv(latest_categories_csv_path, artifacts.snapshot["category_rows"])
    _write_csv(latest_selected_games_csv_path, artifacts.snapshot["selected_games"])

    return {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "snapshot_json_path": snapshot_json_path,
        "mechanics_csv_path": mechanics_csv_path,
        "categories_csv_path": categories_csv_path,
        "selected_games_csv_path": selected_games_csv_path,
        "latest_json_path": latest_json_path,
        "latest_mechanics_csv_path": latest_mechanics_csv_path,
        "latest_categories_csv_path": latest_categories_csv_path,
        "latest_selected_games_csv_path": latest_selected_games_csv_path,
    }


def _collect_rows_for_taxonomies(
    geekdo_client: GeekdoLinkedItemsClient,
    taxonomies: list[TaxonomyRecord],
    *,
    top_n_per_taxonomy: int,
    sort: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for taxonomy in taxonomies:
        linked_items = geekdo_client.get_top_linked_items(
            taxonomy,
            top_n=top_n_per_taxonomy,
            sort=sort,
        )
        if not linked_items:
            rows.append(_empty_taxonomy_row(taxonomy))
            continue
        for position, item in enumerate(linked_items, start=1):
            rows.append(_build_linked_item_row(taxonomy, item, position))
    return rows


def _build_linked_item_row(
    taxonomy: TaxonomyRecord,
    item: dict[str, Any],
    position: int,
) -> dict[str, Any]:
    return {
        "taxonomy_type": taxonomy.taxonomy_type,
        "taxonomy_id": taxonomy.taxonomy_id,
        "taxonomy_name": taxonomy.name,
        "taxonomy_slug": taxonomy.slug,
        "taxonomy_url": taxonomy.url,
        "taxonomy_position": position,
        "bgg_id": _to_int(item.get("objectid")),
        "name": _clean_text(item.get("name")),
        "linked_item_rank": _to_int(item.get("rank")),
        "year_published": _to_int(item.get("yearpublished")),
        "average_rating_from_linkeditems": _to_float(item.get("average")),
        "average_weight_from_linkeditems": _to_float(item.get("avgweight")),
        "users_rated_from_linkeditems": _to_int(item.get("usersrated")),
        "owned_from_linkeditems": _to_int(item.get("numowned")),
        "num_comments_from_linkeditems": _to_int(item.get("numcomments")),
        "href": _clean_text(item.get("href")),
        "thumbnail": _extract_nested_value(item, "images", "thumb"),
        "micro_thumbnail": _extract_nested_value(item, "images", "micro"),
    }


def _empty_taxonomy_row(taxonomy: TaxonomyRecord) -> dict[str, Any]:
    return {
        "taxonomy_type": taxonomy.taxonomy_type,
        "taxonomy_id": taxonomy.taxonomy_id,
        "taxonomy_name": taxonomy.name,
        "taxonomy_slug": taxonomy.slug,
        "taxonomy_url": taxonomy.url,
        "taxonomy_position": None,
        "bgg_id": None,
        "name": None,
    }


def _merge_linked_item_with_thing(
    row: dict[str, Any],
    thing_lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    bgg_id = row.get("bgg_id")
    if not isinstance(bgg_id, int):
        return row

    thing = thing_lookup.get(bgg_id, {})
    merged = dict(row)
    merged.update(
        {
            "boardgame_rank": thing.get("boardgame_rank"),
            "year_published": thing.get("year_published") or row.get("year_published"),
            "min_players": thing.get("min_players"),
            "max_players": thing.get("max_players"),
            "playing_time": thing.get("playing_time"),
            "average_rating": thing.get("average_rating"),
            "bayes_average_rating": thing.get("bayes_average_rating"),
            "average_weight": thing.get("average_weight"),
            "owned": thing.get("owned"),
            "wanting": thing.get("wanting"),
            "wishing": thing.get("wishing"),
            "users_rated": thing.get("users_rated"),
            "num_comments": thing.get("num_comments"),
            "categories": sorted(thing.get("categories", [])),
            "mechanics": sorted(thing.get("mechanics", [])),
            "designers": sorted(thing.get("designers", [])),
            "publishers": sorted(thing.get("publishers", [])),
        }
    )
    return merged


def _build_selected_games(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_games: dict[int, dict[str, Any]] = {}
    for row in rows:
        bgg_id = row.get("bgg_id")
        if not isinstance(bgg_id, int):
            continue

        game = selected_games.setdefault(
            bgg_id,
            {
                "bgg_id": bgg_id,
                "name": row.get("name"),
                "boardgame_rank": row.get("boardgame_rank"),
                "year_published": row.get("year_published"),
                "min_players": row.get("min_players"),
                "max_players": row.get("max_players"),
                "playing_time": row.get("playing_time"),
                "average_rating": row.get("average_rating"),
                "bayes_average_rating": row.get("bayes_average_rating"),
                "average_weight": row.get("average_weight"),
                "owned": row.get("owned"),
                "wanting": row.get("wanting"),
                "wishing": row.get("wishing"),
                "users_rated": row.get("users_rated"),
                "num_comments": row.get("num_comments"),
                "categories": row.get("categories", []),
                "mechanics": row.get("mechanics", []),
                "designers": row.get("designers", []),
                "publishers": row.get("publishers", []),
                "qualifying_mechanics": [],
                "qualifying_categories": [],
            },
        )
        taxonomy_name = row.get("taxonomy_name")
        taxonomy_type = row.get("taxonomy_type")
        if taxonomy_type == "boardgamemechanic" and taxonomy_name and taxonomy_name not in game["qualifying_mechanics"]:
            game["qualifying_mechanics"].append(taxonomy_name)
        if taxonomy_type == "boardgamecategory" and taxonomy_name and taxonomy_name not in game["qualifying_categories"]:
            game["qualifying_categories"].append(taxonomy_name)

    return sorted(
        selected_games.values(),
        key=lambda game: (
            _sort_key(game.get("boardgame_rank")),
            str(game.get("name") or ""),
            game["bgg_id"],
        ),
    )


def _sort_key(value: int | None) -> int:
    return value if value is not None else 10**9


def _extract_nested_value(item: dict[str, Any], outer_key: str, inner_key: str) -> Any:
    nested = item.get(outer_key)
    if not isinstance(nested, dict):
        return None
    return nested.get(inner_key)


def _chunked(values: list[int], chunk_size: int) -> list[list[int]]:
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


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
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
