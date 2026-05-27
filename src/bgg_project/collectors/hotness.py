from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from bgg_project.bgg_client import BGGClient


def _to_int(value: str | None) -> int | None:
    if value in {None, "", "Not Ranked"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value in {None, "", "Not Ranked"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _text_attr(node: ET.Element | None, attribute: str = "value") -> str | None:
    if node is None:
        return None
    return node.attrib.get(attribute)


def _chunked(values: list[int], chunk_size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), chunk_size):
        yield values[index : index + chunk_size]


def parse_hot_items(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []

    for item in root.findall("item"):
        items.append(
            {
                "bgg_id": _to_int(item.attrib.get("id")),
                "hot_rank": _to_int(item.attrib.get("rank")),
                "name": _text_attr(item.find("name")),
                "year_published": _to_int(_text_attr(item.find("yearpublished"))),
                "thumbnail": _text_attr(item.find("thumbnail")),
            }
        )

    return items


def parse_thing_items(xml_text: str) -> dict[int, dict[str, Any]]:
    root = ET.fromstring(xml_text)
    thing_lookup: dict[int, dict[str, Any]] = {}

    for item in root.findall("item"):
        item_id = _to_int(item.attrib.get("id"))
        if item_id is None:
            continue

        name = None
        for candidate in item.findall("name"):
            if candidate.attrib.get("type") == "primary":
                name = candidate.attrib.get("value")
                break
        if name is None:
            name = _text_attr(item.find("name"))

        links: dict[str, list[str]] = {}
        for link in item.findall("link"):
            link_type = link.attrib.get("type")
            link_value = link.attrib.get("value")
            if not link_type or not link_value:
                continue
            links.setdefault(link_type, []).append(link_value)

        ratings = item.find("statistics/ratings")
        boardgame_rank = None
        if ratings is not None:
            for rank_node in ratings.findall("ranks/rank"):
                if rank_node.attrib.get("name") == "boardgame":
                    boardgame_rank = _to_int(rank_node.attrib.get("value"))
                    break

        thing_lookup[item_id] = {
            "bgg_id": item_id,
            "primary_name": name,
            "year_published": _to_int(_text_attr(item.find("yearpublished"))),
            "min_players": _to_int(_text_attr(item.find("minplayers"))),
            "max_players": _to_int(_text_attr(item.find("maxplayers"))),
            "playing_time": _to_int(_text_attr(item.find("playingtime"))),
            "min_playtime": _to_int(_text_attr(item.find("minplaytime"))),
            "max_playtime": _to_int(_text_attr(item.find("maxplaytime"))),
            "min_age": _to_int(_text_attr(item.find("minage"))),
            "thumbnail": _text_attr(item.find("thumbnail")),
            "image": _text_attr(item.find("image")),
            "description": (item.findtext("description") or "").strip() or None,
            "users_rated": _to_int(_text_attr(ratings.find("usersrated")) if ratings is not None else None),
            "average_rating": _to_float(
                _text_attr(ratings.find("average")) if ratings is not None else None
            ),
            "bayes_average_rating": _to_float(
                _text_attr(ratings.find("bayesaverage")) if ratings is not None else None
            ),
            "average_weight": _to_float(
                _text_attr(ratings.find("averageweight")) if ratings is not None else None
            ),
            "owned": _to_int(_text_attr(ratings.find("owned")) if ratings is not None else None),
            "wanting": _to_int(_text_attr(ratings.find("wanting")) if ratings is not None else None),
            "wishing": _to_int(_text_attr(ratings.find("wishing")) if ratings is not None else None),
            "num_comments": _to_int(
                _text_attr(ratings.find("numcomments")) if ratings is not None else None
            ),
            "num_weights": _to_int(
                _text_attr(ratings.find("numweights")) if ratings is not None else None
            ),
            "boardgame_rank": boardgame_rank,
            "categories": links.get("boardgamecategory", []),
            "mechanics": links.get("boardgamemechanic", []),
            "designers": links.get("boardgamedesigner", []),
            "publishers": links.get("boardgamepublisher", []),
            "families": links.get("boardgamefamily", []),
        }

    return thing_lookup


def merge_hot_and_thing_data(
    hot_items: list[dict[str, Any]],
    thing_lookup: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for hot_item in hot_items:
        bgg_id = hot_item["bgg_id"]
        details = thing_lookup.get(bgg_id, {})
        merged.append({**details, **hot_item})
    return merged


@dataclass(slots=True)
class SnapshotArtifacts:
    snapshot: dict[str, Any]
    hot_xml: str
    thing_xml_batches: list[dict[str, Any]]


def collect_hotness_snapshot(
    client: BGGClient,
    *,
    item_type: str,
    max_items: int,
    enrich_with_thing_stats: bool,
    thing_batch_size: int,
) -> SnapshotArtifacts:
    observed_at = datetime.now(timezone.utc)
    hot_xml = client.get_hot_items(item_type)
    hot_items = parse_hot_items(hot_xml)[:max_items]

    thing_xml_batches: list[dict[str, Any]] = []
    thing_lookup: dict[int, dict[str, Any]] = {}

    if enrich_with_thing_stats:
        item_ids = [item["bgg_id"] for item in hot_items if item.get("bgg_id") is not None]
        for chunk in _chunked(item_ids, thing_batch_size):
            xml_text = client.get_things(chunk, stats=True)
            thing_xml_batches.append({"item_ids": chunk, "xml": xml_text})
            thing_lookup.update(parse_thing_items(xml_text))

    items = merge_hot_and_thing_data(hot_items, thing_lookup)
    snapshot = {
        "dataset_name": "weekly_hotness",
        "collection_method": "BGG XML API hot endpoint used as a weekly hotness proxy.",
        "observed_at_utc": observed_at.isoformat(),
        "item_type": item_type,
        "enriched_with_thing_stats": enrich_with_thing_stats,
        "record_count": len(items),
        "items": items,
    }

    return SnapshotArtifacts(
        snapshot=snapshot,
        hot_xml=hot_xml,
        thing_xml_batches=thing_xml_batches,
    )


def write_hotness_snapshot(
    artifacts: SnapshotArtifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    item_type: str,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "hotness" / item_type / timestamp
    processed_snapshot_dir = processed_data_dir / "hotness" / item_type / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    hot_xml_path = raw_snapshot_dir / "hot.xml"
    hot_xml_path.write_text(artifacts.hot_xml, encoding="utf-8")

    for batch_number, batch in enumerate(artifacts.thing_xml_batches, start=1):
        batch_path = raw_snapshot_dir / f"thing_batch_{batch_number:02d}.xml"
        batch_path.write_text(batch["xml"], encoding="utf-8")

    json_path = processed_snapshot_dir / "weekly_hotness.json"
    json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    csv_path = processed_snapshot_dir / "weekly_hotness.csv"
    _write_items_csv(csv_path, artifacts.snapshot["items"])

    latest_dir = processed_data_dir / "hotness" / item_type
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_csv_path = latest_dir / "latest.csv"
    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_items_csv(latest_csv_path, artifacts.snapshot["items"])

    metadata_path = processed_snapshot_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "output_label": timestamp,
                "observed_at_utc": artifacts.snapshot["observed_at_utc"],
                "record_count": artifacts.snapshot["record_count"],
                "item_type": item_type,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    return {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "hot_xml_path": hot_xml_path,
        "json_path": json_path,
        "csv_path": csv_path,
        "metadata_path": metadata_path,
        "latest_json_path": latest_json_path,
        "latest_csv_path": latest_csv_path,
    }


def _write_items_csv(csv_path: Path, items: list[dict[str, Any]]) -> None:
    rows = [_flatten_item_for_csv(item) for item in items]
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _flatten_item_for_csv(item: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, list):
            flattened[key] = " | ".join(str(entry) for entry in value)
        else:
            flattened[key] = value
    return flattened
