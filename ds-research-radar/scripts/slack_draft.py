"""Create a compact Slack-ready draft without sending any message."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def one_or_two_lines(value: str, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentence for sentence in sentences[:2] if sentence)[:limit]


def slack_draft(report: dict[str, Any], per_domain: int = 2) -> str:
    """Format only approved items; external delivery remains a separate, explicit action."""
    grouped: dict[str, list[dict[str, Any]]] = {"language": [], "climate": [], "career": [], "industry": []}
    for item in report.get("candidates", []):
        if item.get("review_status") != "approved":
            continue
        domains = item.get("domains", [])
        bucket = next((domain for domain in ("language", "climate", "career") if domain in domains), "industry")
        grouped[bucket].append(item)

    labels = {"language": "Language", "climate": "Climate", "career": "Career", "industry": "Industry"}
    lines = [f"📡 *DS Research Radar | {report.get('generated_at', '')[:10]}*", ""]
    for bucket in ("language", "climate", "industry", "career"):
        items = grouped[bucket][:per_domain]
        if not items:
            continue
        lines.append(f"*{labels[bucket]}*")
        for item in items:
            lines.append(f"• <{item['primary_source_url']}|{item['title']}>")
            lines.append(f"  {one_or_two_lines(item.get('summary', '원문 요약을 확인하세요.'))}")
        lines.append("")
    approved = sum(item.get("review_status") == "approved" for item in report.get("candidates", []))
    if approved == 0:
        lines.append("이번 수집에서 Slack으로 보낼 승인 자료가 없습니다.")
    else:
        lines.append("전체 상세 분석은 Notion에서 확인합니다. 이 초안은 아직 Slack으로 전송되지 않았습니다.")
    return "\n".join(lines).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Slack draft from an approved DS Research Radar report.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-domain", type=int, default=2)
    arguments = parser.parse_args(argv)
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(slack_draft(report, arguments.per_domain), encoding="utf-8")
    print(f"Drafted {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
