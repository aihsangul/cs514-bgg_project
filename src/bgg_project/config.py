from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SettingsError(RuntimeError):
    """Raised when project configuration is incomplete or invalid."""


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SettingsError(f"Config file does not exist: {path}")
    with path.open("r", encoding="utf-8") as file_handle:
        data = yaml.safe_load(file_handle) or {}
    if not isinstance(data, dict):
        raise SettingsError(f"Config file must contain a mapping: {path}")
    return data


def load_settings(config_path: str | Path | None = None) -> dict[str, Any]:
    load_dotenv(PROJECT_ROOT / ".env")

    config_file = _resolve_path(config_path or "config/settings.yaml")
    settings = _load_yaml(config_file)

    settings.setdefault("project", {})
    settings.setdefault("paths", {})
    settings.setdefault("api", {})
    settings.setdefault("logging", {})
    settings.setdefault("collection", {})

    settings["_meta"] = {
        "project_root": PROJECT_ROOT,
        "config_file": config_file,
    }

    resolved_paths: dict[str, Path] = {}
    for key, value in settings["paths"].items():
        resolved_paths[key] = _resolve_path(value)
    settings["paths"] = resolved_paths

    logging_config_path = settings["logging"].get("config_path", "config/logging.yaml")
    settings["logging"]["config_path"] = _resolve_path(logging_config_path)

    return settings


def get_api_token(settings: dict[str, Any]) -> str:
    env_var = settings["api"].get("token_env_var", "BGG_API_TOKEN")
    token = os.getenv(env_var, "").strip()
    if not token:
        raise SettingsError(
            f"Missing API token. Set the {env_var} value in the local .env file."
        )
    return token
