"""Compare collected research signals by topic and period."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SIGNAL_TYPES = {"Paper", "Model", "Company", "Event", "Job", "Data Release"}


def aggregate_signals(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count distinct source-backed signal types for each topic."""
    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        item_type = item.get("type")
        if item_type not in SIGNAL_TYPES or not item.get("primary_source_url"):
            continue
        for topic in item.get("topics", []):
            result[topic][item_type] += 1
    return {topic: dict(counts) for topic, counts in result.items()}


def compare_topics(
    previous_items: Iterable[dict[str, Any]], current_items: Iterable[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Return source-backed signal totals and type breadth for every topic."""
    previous = aggregate_signals(previous_items)
    current = aggregate_signals(current_items)
    comparison = {}
    for topic in sorted(previous.keys() | current.keys()):
        previous_counts = previous.get(topic, {})
        current_counts = current.get(topic, {})
        comparison[topic] = {
            "previous_total": sum(previous_counts.values()),
            "current_total": sum(current_counts.values()),
            "previous_breadth": len(previous_counts),
            "current_breadth": len(current_counts),
        }
    return comparison
