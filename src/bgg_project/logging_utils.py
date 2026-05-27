from __future__ import annotations

import logging.config
from pathlib import Path
from typing import Any

import yaml


def setup_logging(settings: dict[str, Any]) -> None:
    """Load logging configuration and resolve file paths against the project root."""
    project_root: Path = settings["_meta"]["project_root"]
    config_path: Path = settings["logging"]["config_path"]

    with config_path.open("r", encoding="utf-8") as file_handle:
        config: dict[str, Any] = yaml.safe_load(file_handle) or {}

    for handler in config.get("handlers", {}).values():
        filename = handler.get("filename")
        if filename:
            log_path = Path(filename)
            if not log_path.is_absolute():
                log_path = project_root / log_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler["filename"] = str(log_path)

    logging.config.dictConfig(config)
