"""Conservative, explainable DS relevance scoring."""

from __future__ import annotations

WEIGHTS = {
    "ds_relevance": 30,
    "technical_impact": 25,
    "evidence_quality": 20,
    "industry_signal": 15,
    "novelty": 10,
}


def score(signals: dict[str, float | int | None]) -> int:
    """Score supplied 0–1 signals; missing evidence contributes zero."""
    total = 0.0
    for name, weight in WEIGHTS.items():
        value = signals.get(name) or 0
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
        total += value * weight
    return round(total)
