from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


BASE_SITE_URL = "https://boardgamegeek.com"
MECHANIC_SUBTYPE = "boardgamemechanic"
CATEGORY_SUBTYPE = "boardgamecategory"
_SUPPORTED_SUBTYPES = {MECHANIC_SUBTYPE, CATEGORY_SUBTYPE}
_BROWSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class TaxonomyFetchError(RuntimeError):
    """Raised when a taxonomy browse page cannot be collected programmatically."""


@dataclass(slots=True)
class TaxonomySource:
    label: str
    subtype: str
    html: str
    source_kind: str
    source_reference: str


@dataclass(slots=True)
class TaxonomyArtifacts:
    snapshot: dict[str, Any]
    sources: dict[str, TaxonomySource]


class _BrowseTaxonomyParser(HTMLParser):
    def __init__(self, subtype: str) -> None:
        super().__init__(convert_charrefs=True)
        self.subtype = subtype
        self.records_by_id: dict[int, dict[str, Any]] = {}
        self._current_link: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")
        link_info = _extract_taxonomy_link(href, self.subtype)
        if link_info is None:
            return

        self._current_link = {**link_info, "text_parts": []}

    def handle_data(self, data: str) -> None:
        if self._current_link is not None:
            self._current_link["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_link is None:
            return

        name = _clean_text("".join(self._current_link["text_parts"]))
        if name:
            taxonomy_id = self._current_link["taxonomy_id"]
            self.records_by_id.setdefault(
                taxonomy_id,
                {
                    "taxonomy_type": self.subtype,
                    "taxonomy_id": taxonomy_id,
                    "name": name,
                    "slug": self._current_link["slug"],
                    "url": self._current_link["url"],
                },
            )

        self._current_link = None


def load_taxonomy_source(
    *,
    label: str,
    subtype: str,
    url: str,
    html_path: Path | None = None,
    timeout_seconds: int = 30,
) -> TaxonomySource:
    if html_path is not None:
        html = _read_html_file(html_path, label)
        return TaxonomySource(
            label=label,
            subtype=subtype,
            html=html,
            source_kind="local_file",
            source_reference=str(html_path),
        )

    scraper = _create_cloudscraper()
    try:
        response = scraper.get(
            url,
            headers=_BROWSE_HEADERS,
            timeout=timeout_seconds,
        )
    except requests.RequestException as error:
        raise TaxonomyFetchError(
            f"Could not fetch {label} from {url} with cloudscraper: {error}. "
            "If BGG remains inaccessible from this environment, save the page source "
            "in your browser and rerun with the local HTML file."
        ) from error
    html = response.text
    if response.status_code >= 400 or _looks_like_cloudflare_challenge(html):
        raise TaxonomyFetchError(
            f"Could not fetch {label} from {url}. "
            "BGG returned a blocked/challenge page even with cloudscraper. "
            "Save the page source in your browser and rerun with the local HTML file."
        )

    return TaxonomySource(
        label=label,
        subtype=subtype,
        html=html,
        source_kind="url",
        source_reference=url,
    )


def parse_taxonomy_html(html_text: str, subtype: str) -> list[dict[str, Any]]:
    if subtype not in _SUPPORTED_SUBTYPES:
        raise ValueError(f"Unsupported taxonomy subtype: {subtype}")

    parser = _BrowseTaxonomyParser(subtype)
    parser.feed(html_text)
    return sorted(
        parser.records_by_id.values(),
        key=lambda row: (row["name"].lower(), row["taxonomy_id"]),
    )


def collect_taxonomy_snapshot(
    mechanics_source: TaxonomySource,
    categories_source: TaxonomySource,
) -> TaxonomyArtifacts:
    mechanics = parse_taxonomy_html(mechanics_source.html, MECHANIC_SUBTYPE)
    categories = parse_taxonomy_html(categories_source.html, CATEGORY_SUBTYPE)
    observed_at = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "dataset_name": "taxonomy",
        "collection_method": (
            "Parsed the BGG browse pages for board game mechanics and categories."
        ),
        "observed_at_utc": observed_at,
        "mechanic_count": len(mechanics),
        "category_count": len(categories),
        "mechanics": mechanics,
        "categories": categories,
        "sources": {
            "mechanics": _source_to_metadata(mechanics_source),
            "categories": _source_to_metadata(categories_source),
        },
    }
    return TaxonomyArtifacts(
        snapshot=snapshot,
        sources={
            "mechanics": mechanics_source,
            "categories": categories_source,
        },
    )


def write_taxonomy_snapshot(
    artifacts: TaxonomyArtifacts,
    *,
    raw_data_dir: Path,
    processed_data_dir: Path,
    output_label: str | None = None,
) -> dict[str, Path]:
    timestamp = output_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_snapshot_dir = raw_data_dir / "taxonomy" / timestamp
    processed_snapshot_dir = processed_data_dir / "taxonomy" / timestamp
    raw_snapshot_dir.mkdir(parents=True, exist_ok=True)
    processed_snapshot_dir.mkdir(parents=True, exist_ok=True)

    mechanics_html_path = raw_snapshot_dir / "mechanics_source.html"
    categories_html_path = raw_snapshot_dir / "categories_source.html"
    mechanics_html_path.write_text(artifacts.sources["mechanics"].html, encoding="utf-8")
    categories_html_path.write_text(artifacts.sources["categories"].html, encoding="utf-8")

    snapshot_json_path = processed_snapshot_dir / "taxonomy.json"
    snapshot_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    mechanics_csv_path = processed_snapshot_dir / "mechanics.csv"
    categories_csv_path = processed_snapshot_dir / "categories.csv"
    _write_csv(mechanics_csv_path, artifacts.snapshot["mechanics"])
    _write_csv(categories_csv_path, artifacts.snapshot["categories"])

    metadata_path = processed_snapshot_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "output_label": timestamp,
                "observed_at_utc": artifacts.snapshot["observed_at_utc"],
                "mechanic_count": artifacts.snapshot["mechanic_count"],
                "category_count": artifacts.snapshot["category_count"],
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    latest_dir = processed_data_dir / "taxonomy"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_json_path = latest_dir / "latest.json"
    latest_mechanics_csv_path = latest_dir / "latest_mechanics.csv"
    latest_categories_csv_path = latest_dir / "latest_categories.csv"
    latest_json_path.write_text(
        json.dumps(artifacts.snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _write_csv(latest_mechanics_csv_path, artifacts.snapshot["mechanics"])
    _write_csv(latest_categories_csv_path, artifacts.snapshot["categories"])

    return {
        "raw_snapshot_dir": raw_snapshot_dir,
        "processed_snapshot_dir": processed_snapshot_dir,
        "mechanics_html_path": mechanics_html_path,
        "categories_html_path": categories_html_path,
        "snapshot_json_path": snapshot_json_path,
        "mechanics_csv_path": mechanics_csv_path,
        "categories_csv_path": categories_csv_path,
        "metadata_path": metadata_path,
        "latest_json_path": latest_json_path,
        "latest_mechanics_csv_path": latest_mechanics_csv_path,
        "latest_categories_csv_path": latest_categories_csv_path,
    }


def _source_to_metadata(source: TaxonomySource) -> dict[str, Any]:
    return {
        "label": source.label,
        "subtype": source.subtype,
        "source_kind": source.source_kind,
        "source_reference": source.source_reference,
    }


def _read_html_file(html_path: Path, label: str) -> str:
    if not html_path.exists():
        raise TaxonomyFetchError(
            f"The local {label} HTML file does not exist: {html_path}. "
            "Use a real saved page-source file, not the example placeholder path."
        )

    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return html_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise TaxonomyFetchError(
        f"Could not decode the local {label} HTML file: {html_path}. "
        "Try saving the page source again from the browser using standard text encoding."
    )


def _create_cloudscraper() -> requests.Session:
    try:
        cloudscraper_module = importlib.import_module("cloudscraper")
    except ModuleNotFoundError as error:
        raise TaxonomyFetchError(
            "cloudscraper is required for live taxonomy collection. "
            "Install the project dependencies again so the new package is available, "
            "or rerun the collector with locally saved HTML files."
        ) from error
    scraper = cloudscraper_module.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False,
        }
    )
    scraper.trust_env = False
    return scraper


def _write_csv(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _extract_taxonomy_link(href: str | None, subtype: str) -> dict[str, Any] | None:
    if not href:
        return None

    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc and "boardgamegeek.com" not in parsed.netloc:
        return None

    path = parsed.path.strip("/")
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] != subtype or not parts[1].isdigit():
        return None

    taxonomy_id = int(parts[1])
    slug = parts[2] if len(parts) >= 3 else None
    url = f"{BASE_SITE_URL}/{subtype}/{taxonomy_id}"
    if slug:
        url = f"{url}/{slug}"

    return {
        "taxonomy_id": taxonomy_id,
        "slug": slug,
        "url": url,
    }


def _looks_like_cloudflare_challenge(html_text: str) -> bool:
    normalized = html_text.lower()
    markers = (
        "just a moment",
        "/cdn-cgi/challenge-platform",
        "attention required!",
        "cf-chl",
        "cloudflare",
    )
    marker_hits = sum(marker in normalized for marker in markers)
    return marker_hits >= 2


def _clean_text(value: str) -> str | None:
    stripped = " ".join(value.split()).strip()
    return stripped or None
