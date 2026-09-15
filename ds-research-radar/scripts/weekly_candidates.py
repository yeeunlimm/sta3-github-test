"""Build a fast, review-first weekly research candidate report from Atom/RSS feeds.

The script intentionally does not write to Notion or send Slack messages.  It
collects lightweight feed metadata, removes repeats, and writes a review queue.
Only a human-approved item should be read deeply and stored in Notion.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from deduplicate import identity_keys, unique_items

DEFAULT_KEYWORDS = {
    "language": {
        "llm", "language model", "nlp", "multilingual", "translation", "rag",
        "retrieval", "embedding", "search", "evaluation", "agent",
    },
    "climate": {
        "climate", "weather", "forecast", "geospatial", "satellite", "wildfire",
        "environment", "energy", "remote sensing", "earth",
    },
    "career": {
        "data scientist", "data engineer", "machine learning", "ai engineer",
        "data analyst", "intern", "new graduate",
    },
}
STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "your", "how",
    "new", "using", "use", "what", "ai", "llm", "data", "model", "models",
}


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse the common Atom/RSS date forms into UTC."""
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] in names and (child.text or "").strip():
            return clean_text(child.text)
    return ""


def feed_items(xml_text: str, source: str) -> list[dict[str, Any]]:
    """Extract title, link, date, and summary from an Atom or RSS document."""
    root = ET.fromstring(xml_text)
    records: list[dict[str, Any]] = []
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] not in {"item", "entry"}:
            continue
        title = child_text(entry, ("title",))
        summary = child_text(entry, ("description", "summary", "content"))
        published = child_text(entry, ("published", "updated", "pubDate", "date"))
        link = ""
        for child in entry.iter():
            if child.tag.rsplit("}", 1)[-1] == "link":
                link = child.attrib.get("href") or clean_text(child.text)
                if link:
                    break
        if title and link:
            records.append(
                {
                    "title": title,
                    "primary_source_url": link,
                    "published_at": published,
                    "summary": summary,
                    "source": source,
                }
            )
    return records


def candidate_domains(item: dict[str, Any]) -> list[str]:
    text = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    return [domain for domain, words in DEFAULT_KEYWORDS.items() if any(word in text for word in words)]


def fetch_feed(name: str, url: str, timeout_seconds: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "DS-Research-Radar/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return feed_items(response.read().decode("utf-8", errors="replace"), name)


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen_identity_keys": [], "last_successful_run_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def word_counts(items: list[dict[str, Any]]) -> Counter[str]:
    words = Counter()
    for item in items:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", f"{item['title']} {item.get('summary', '')}".casefold()):
            if word not in STOP_WORDS:
                words[word] += 1
    return words


def wordcloud_svg(counts: Counter[str], top_n: int = 30) -> str:
    """Render a dependency-free word cloud SVG for a small reviewed candidate set."""
    tokens = counts.most_common(top_n)
    if not tokens:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="160"><text x="20" y="80">No industry candidates this week</text></svg>'
    pieces = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="260" viewBox="0 0 900 260">']
    x, y = 24, 45
    maximum = tokens[0][1]
    for index, (word, count) in enumerate(tokens):
        size = 14 + round(22 * count / maximum)
        width = max(75, len(word) * (size // 2 + 2))
        if x + width > 875:
            x, y = 24, y + 52
        if y > 245:
            break
        color = ("#2563eb", "#0f766e", "#7c3aed", "#b45309")[index % 4]
        pieces.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" fill="{color}">{html.escape(word)}</text>')
        x += width
    pieces.append("</svg>")
    return "".join(pieces)


def build_report(
    feeds: dict[str, str],
    cache: dict[str, Any],
    now: datetime,
    industry_sources: set[str],
    timeout_seconds: int = 12,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch in parallel, filter to seven days, deduplicate, and prepare review-only output."""
    cutoff = now - timedelta(days=7)
    fetched: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, max(1, len(feeds)))) as pool:
        futures = {pool.submit(fetch_feed, name, url, timeout_seconds): name for name, url in feeds.items()}
        for future, name in ((future, futures[future]) for future in futures):
            try:
                fetched.extend(future.result())
            except Exception as error:  # A slow/broken source must not stop the weekly run.
                failures[name] = f"{type(error).__name__}: {error}"

    dated = []
    undated = 0
    for item in fetched:
        published = parse_timestamp(item["published_at"])
        if published is None:
            undated += 1
        elif published >= cutoff:
            item["published_at"] = published.isoformat()
            item["domains"] = candidate_domains(item)
            dated.append(item)

    unique, in_run_duplicates = unique_items(dated)
    seen = set(cache.get("seen_identity_keys", []))
    fresh, previous_duplicates = [], []
    for item in unique:
        if identity_keys(item) & seen:
            previous_duplicates.append(item)
        else:
            fresh.append(item)

    # A candidate needs a relevant domain; it is still explicitly marked for review.
    review_queue = [item for item in fresh if item["domains"]]
    industry_items = [item for item in review_queue if item["source"] in industry_sources]
    report = {
        "generated_at": now.isoformat(),
        "window_start": cutoff.isoformat(),
        "review_required": True,
        "notion_write_performed": False,
        "summary": {
            "fetched": len(fetched),
            "undated_skipped": undated,
            "older_than_7_days_skipped": len(fetched) - undated - len(dated),
            "in_run_duplicates_skipped": len(in_run_duplicates),
            "previously_seen_skipped": len(previous_duplicates),
            "relevance_filtered_out": len(fresh) - len(review_queue),
            "review_candidates": len(review_queue),
        },
        "source_failures": failures,
        "candidates": review_queue,
        "trend_candidates": sorted(word_counts(industry_items).items(), key=lambda pair: (-pair[1], pair[0]))[:15],
        "notes": [
            "Candidates are not automatically saved to Notion.",
            "No candidate is a valid outcome; do not add weak material to fill the report.",
            "Trend words are only a review cue, not a confirmed industry trend.",
        ],
    }
    new_cache = {
        "last_successful_run_at": now.isoformat(),
        "seen_identity_keys": sorted(seen | {key for item in unique for key in identity_keys(item)}),
    }
    return report, new_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build weekly DS research candidates from Atom/RSS feeds.")
    parser.add_argument("--feed", action="append", default=[], metavar="NAME=URL", help="repeat for each Atom/RSS feed")
    parser.add_argument("--industry-source", action="append", default=[], help="feed name included in the industry-only word cloud")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wordcloud", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=12)
    arguments = parser.parse_args(argv)
    feeds = dict(value.split("=", 1) for value in arguments.feed if "=" in value)
    if not feeds:
        parser.error("at least one --feed NAME=URL is required")
    now = datetime.now(UTC)
    report, new_cache = build_report(feeds, load_cache(arguments.cache), now, set(arguments.industry_source), arguments.timeout)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    arguments.cache.parent.mkdir(parents=True, exist_ok=True)
    arguments.cache.write_text(json.dumps(new_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    arguments.wordcloud.parent.mkdir(parents=True, exist_ok=True)
    industry = [item for item in report["candidates"] if item["source"] in set(arguments.industry_source)]
    arguments.wordcloud.write_text(wordcloud_svg(word_counts(industry)), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
