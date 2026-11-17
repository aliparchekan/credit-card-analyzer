"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class AppConfig(BaseModel):
    """Runtime settings for the analyzer."""

    input_dir: Path = Path("input")
    output_dir: Path = Path("output")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:30b-a3b"
    ollama_fallback_model: str = "qwen3:14b"
    request_timeout_seconds: int = Field(default=60, ge=1)
    classification_cache: Path = Path("output/classification_cache.json")
    low_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    cards_file: Path | None = None


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip("\"'")
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load simple top-level YAML key/value settings without extra deps."""
    data: dict[str, Any] = {}
    if not path.exists():
        return data

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"Invalid config line {line_number}: expected 'key: value'")
        key, value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid config line {line_number}: empty key")
        data[key] = _parse_scalar(value)
    return data


def load_config(config_path: str | Path = "config.example.yaml") -> AppConfig:
    """Load the analyzer configuration.

    The checked-in example config doubles as a usable default local config.
    """
    path = Path(config_path)
    try:
        raw = _load_simple_yaml(path)
        config = AppConfig(**raw)
    except (ValueError, ValidationError) as exc:
        raise SystemExit(f"Configuration error in {path}: {exc}") from exc

    if not config.classification_cache.is_absolute():
        config.classification_cache = config.output_dir / config.classification_cache.name
    return config

