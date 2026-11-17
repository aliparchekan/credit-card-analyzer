"""Transaction classification using rules first and local Ollama as fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from pydantic import BaseModel, ValidationError

from .config import AppConfig
from .rules import CATEGORIES, is_valid_category, match_rule
from .utils import normalize_merchant, read_json, write_json


class Classification(BaseModel):
    """A transaction classification with confidence and explanation."""

    category: str
    confidence: float
    reason: str


def _other(reason: str) -> Classification:
    return Classification(category="Other", confidence=0.0, reason=reason)


def _classification_from_dict(data: dict[str, Any]) -> Classification:
    result = Classification(**data)
    if not is_valid_category(result.category):
        raise ValueError(f"Invalid category: {result.category}")
    confidence = max(0.0, min(1.0, float(result.confidence)))
    reason = str(result.reason).strip()[:300] or "No reason provided"
    return Classification(category=result.category, confidence=confidence, reason=reason)


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    """Load the merchant classification cache."""
    raw = read_json(path, default={})
    return raw if isinstance(raw, dict) else {}


def save_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    """Persist the merchant classification cache."""
    write_json(path, cache)


def _build_prompt(description: str) -> str:
    category_list = "\n".join(f"- {category}" for category in CATEGORIES)
    return (
        "Classify this credit card transaction into exactly one allowed category.\n"
        "Return JSON only with this exact shape: "
        '{"category":"...", "confidence":0.0, "reason":"..."}\n'
        "Do not include markdown, prose, comments, or extra keys.\n\n"
        f"Allowed categories:\n{category_list}\n\n"
        f"Transaction description: {description!r}\n"
    )


def _parse_ollama_response(text: str) -> Classification:
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Ollama returned JSON that is not an object")
    return _classification_from_dict(data)


def _call_ollama_once(description: str, model: str, config: AppConfig) -> Classification:
    url = config.ollama_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": _build_prompt(description),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    response = requests.post(url, json=payload, timeout=config.request_timeout_seconds)
    response.raise_for_status()
    body = response.json()
    generated = body.get("response")
    if not isinstance(generated, str) or not generated.strip():
        raise ValueError("Ollama response did not contain generated JSON text")
    return _parse_ollama_response(generated)


def classify_with_ollama(description: str, config: AppConfig) -> Classification:
    """Classify an unknown merchant through the local Ollama API."""
    errors: list[str] = []
    for model in (config.ollama_model, config.ollama_fallback_model):
        if not model:
            continue
        try:
            result = _call_ollama_once(description, model, config)
            return Classification(
                category=result.category,
                confidence=result.confidence,
                reason=f"Ollama {model}: {result.reason}",
            )
        except (requests.RequestException, ValueError, ValidationError, json.JSONDecodeError) as exc:
            errors.append(f"{model}: {exc}")
    return _other("Ollama classification failed; " + " | ".join(errors))


def classify_description(
    description: str,
    config: AppConfig,
    cache: dict[str, dict[str, Any]],
) -> Classification:
    """Classify one transaction description using rules, cache, then Ollama."""
    rule_match = match_rule(description)
    if rule_match:
        return Classification(
            category=rule_match.category,
            confidence=rule_match.confidence,
            reason=rule_match.reason,
        )

    key = normalize_merchant(description)
    cached = cache.get(key)
    if isinstance(cached, dict):
        try:
            result = _classification_from_dict(cached)
            return Classification(
                category=result.category,
                confidence=result.confidence,
                reason=f"Cached: {result.reason}",
            )
        except (ValidationError, ValueError, TypeError):
            cache.pop(key, None)

    result = classify_with_ollama(description, config)
    cache[key] = result.model_dump()
    return result


def classify_transactions(df: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    """Add category, confidence, reason, and review flags to transactions."""
    if df.empty:
        for column in ("merchant_key", "category", "confidence", "reason", "review_needed"):
            df[column] = []
        return df

    cache = load_cache(config.classification_cache)
    classifications = [
        classify_description(str(description), config, cache)
        for description in df["description"].fillna("")
    ]
    save_cache(config.classification_cache, cache)

    enriched = df.copy()
    enriched["merchant_key"] = enriched["description"].apply(normalize_merchant)
    enriched["category"] = [item.category for item in classifications]
    enriched["confidence"] = [item.confidence for item in classifications]
    enriched["reason"] = [item.reason for item in classifications]
    enriched["review_needed"] = (
        (enriched["confidence"] < config.low_confidence_threshold)
        | (enriched["category"] == "Other")
    )
    return enriched

