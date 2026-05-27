from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bgg_project.collectors.taxonomy import (
    CATEGORY_SUBTYPE,
    MECHANIC_SUBTYPE,
    TaxonomyFetchError,
    collect_taxonomy_snapshot,
    load_taxonomy_source,
    write_taxonomy_snapshot,
)
from bgg_project.config import load_settings
from bgg_project.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the BGG master lists of board game mechanics and categories "
            "from the public browse pages."
        )
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to the project settings YAML file.",
    )
    parser.add_argument(
        "--mechanics-url",
        default=None,
        help="Optional override for the mechanics browse URL.",
    )
    parser.add_argument(
        "--categories-url",
        default=None,
        help="Optional override for the categories browse URL.",
    )
    parser.add_argument(
        "--mechanics-html",
        default=None,
        help=(
            "Optional local HTML file for the mechanics browse page. "
            "Use this if BGG blocks scripted access."
        ),
    )
    parser.add_argument(
        "--categories-html",
        default=None,
        help=(
            "Optional local HTML file for the categories browse page. "
            "Use this if BGG blocks scripted access."
        ),
    )
    parser.add_argument(
        "--output-label",
        default=None,
        help="Optional folder label for this snapshot. Defaults to a UTC timestamp.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings(args.config)
    setup_logging(settings)
    logger = logging.getLogger("bgg_project.collect_taxonomy")

    collector_settings = settings["collection"]["taxonomy"]
    timeout_seconds = collector_settings["request_timeout_seconds"]
    mechanics_url = args.mechanics_url or collector_settings["mechanics_browse_url"]
    categories_url = args.categories_url or collector_settings["categories_browse_url"]

    mechanics_html_path = _resolve_optional_path(
        args.mechanics_html,
        settings["_meta"]["project_root"],
    ) or _resolve_existing_default_path(
        collector_settings.get("default_mechanics_html_path"),
        settings["_meta"]["project_root"],
    )
    categories_html_path = _resolve_optional_path(
        args.categories_html,
        settings["_meta"]["project_root"],
    ) or _resolve_existing_default_path(
        collector_settings.get("default_categories_html_path"),
        settings["_meta"]["project_root"],
    )

    if mechanics_html_path is not None:
        logger.info("Using local mechanics HTML: %s", mechanics_html_path)
    if categories_html_path is not None:
        logger.info("Using local categories HTML: %s", categories_html_path)

    try:
        mechanics_source = load_taxonomy_source(
            label="mechanics",
            subtype=MECHANIC_SUBTYPE,
            url=mechanics_url,
            html_path=mechanics_html_path,
            timeout_seconds=timeout_seconds,
        )
        categories_source = load_taxonomy_source(
            label="categories",
            subtype=CATEGORY_SUBTYPE,
            url=categories_url,
            html_path=categories_html_path,
            timeout_seconds=timeout_seconds,
        )
    except TaxonomyFetchError as error:
        logger.error("%s", error)
        logger.error(
            "Tip: open the browse page in your browser, save the page source, and rerun with "
            "--mechanics-html / --categories-html."
        )
        return 1

    artifacts = collect_taxonomy_snapshot(mechanics_source, categories_source)
    outputs = write_taxonomy_snapshot(
        artifacts,
        raw_data_dir=settings["paths"]["raw_data_dir"],
        processed_data_dir=settings["paths"]["processed_data_dir"],
        output_label=args.output_label,
    )

    logger.info("Mechanic count: %s", artifacts.snapshot["mechanic_count"])
    logger.info("Category count: %s", artifacts.snapshot["category_count"])
    logger.info("Snapshot JSON: %s", outputs["snapshot_json_path"])
    logger.info("Mechanics CSV: %s", outputs["mechanics_csv_path"])
    logger.info("Categories CSV: %s", outputs["categories_csv_path"])
    return 0


def _resolve_optional_path(value: str | None, project_root: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def _resolve_existing_default_path(value: str | None, project_root: Path) -> Path | None:
    if value is None:
        return None
    path = _resolve_optional_path(value, project_root)
    if path is not None and path.exists():
        return path
    return None


if __name__ == "__main__":
    raise SystemExit(main())
