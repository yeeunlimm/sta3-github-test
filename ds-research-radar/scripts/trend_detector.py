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


def classify_trend(signals: dict[str, int]) -> str:
    """Classify a topic only when both volume and source diversity support it."""
    previous = signals["previous_total"]
    current = signals["current_total"]
    current_breadth = signals["current_breadth"]

    if previous == 0 and current >= 3 and current_breadth >= 2:
        return "Emerging"
    if previous >= 3 and current < previous * 0.6:
        return "Cooling"
    if previous >= 3 and current >= previous * 1.3 and current_breadth >= 2:
        return "Growing"
    if previous >= 4 and current >= 4 and current_breadth >= 2:
        return "Established"
    return "Unclear"


def classify_topics(comparison: dict[str, dict[str, int]]) -> dict[str, str]:
    """Classify every topic from an already-computed comparison."""
    return {topic: classify_trend(signals) for topic, signals in comparison.items()}
