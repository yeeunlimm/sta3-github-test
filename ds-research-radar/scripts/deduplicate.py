"""Research-item deduplication without external dependencies."""

from __future__ import annotations

import re
from typing import Any, Iterable


def normalize(value: str | None) -> str:
    """Make titles and URLs comparable without changing the original record."""
    return re.sub(r"\W+", "", (value or "").casefold())


def identity_keys(item: dict[str, Any]) -> set[str]:
    """Return stable keys ordered from source identifiers to title+organization."""
    keys = set()
    for field in ("primary_source_url", "doi", "arxiv_id"):
        value = normalize(str(item.get(field, "")))
        if value:
            keys.add(f"{field}:{value}")
    title = normalize(str(item.get("title", "")))
    organization = normalize(str(item.get("organization", "")))
    if title:
        keys.add(f"title_org:{title}:{organization}")
    return keys


def unique_items(items: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep first-seen records and return duplicates separately."""
    seen: set[str] = set()
    unique, duplicates = [], []
    for item in items:
        keys = identity_keys(item)
        if keys & seen:
            duplicates.append(item)
            continue
        seen.update(keys)
        unique.append(item)
    return unique, duplicates
