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
    "그리고", "하지만", "이번", "기존", "관련", "대한", "통해", "위한", "있는", "하는",
    "합니다", "됩니다", "있습니다", "것을", "이것", "그것", "저것", "보다", "함께",
}
KOREAN_WORDCLOUD_STOP_WORDS = STOP_WORDS | {
    "기술", "결과", "방식", "기반", "제공", "활용", "분석", "연구", "서비스",
    "사용", "개선", "지원", "가능", "수준", "통해", "대상", "내용", "기사",
}
MALGUN_GOTHIC = Path("C:/Windows/Fonts/malgun.ttf")


def article_text(html_text: str, limit: int = 12000) -> str:
    """Extract a bounded, readable article body without adding a dependency."""
    without_noncontent = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\\1>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    blocks = re.findall(r"<(?:p|h[1-3]|li|blockquote)[^>]*>(.*?)</(?:p|h[1-3]|li|blockquote)>", without_noncontent, flags=re.IGNORECASE | re.DOTALL)
    text = " ".join(clean_text(block) for block in blocks if clean_text(block))
    return text[:limit] if text else clean_text(without_noncontent)[:limit]


def extractive_detail_draft(item: dict[str, Any]) -> str:
    """Make a source-grounded reading draft; semantic interpretation stays human-reviewed."""
    body = item.get("original_text", "")
    sentences = re.split(r"(?<=[.!?])\\s+", body)
    excerpt = " ".join(sentence for sentence in sentences if sentence)[:1200]
    if not excerpt:
        return "원문 본문을 추출하지 못했습니다. 링크를 직접 열어 확인하세요."
    return (
        f"원문 읽기 초안 — {excerpt}\n\n"
        "상세 요약 작성 시에는 주장·근거·수치·한계가 원문에 실제로 있는지 확인하고, "
        "확인되지 않은 해석은 추가하지 마세요."
    )


def summary_prompt(item: dict[str, Any]) -> str:
    """Package the original text for a model/Codex to create a factual long-form summary."""
    return (
        "아래 원문만 근거로 한국어 상세 요약을 작성하세요. "
        "(1) 무엇이 발표·연구되었는지 (2) 방법·제품 기능 (3) 수치 또는 근거 "
        "(4) 한계·미확인 사항 (5) DS 직무 의미 (6) Why now: 지금 중요한 이유 순으로 쓰고, "
        "원문에 없는 사실은 추측하지 마세요.\n\n"
        f"제목: {item['title']}\n출처: {item['primary_source_url']}\n원문: {item.get('original_text', '')}"
    )


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


def fetch_article(item: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    """Read an original only after it passed the lightweight candidate filters."""
    request = urllib.request.Request(item["primary_source_url"], headers={"User-Agent": "DS-Research-Radar/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        text = response.read().decode("utf-8", errors="replace")
    enriched = dict(item)
    enriched["original_text"] = article_text(text)
    enriched["original_read_status"] = "read"
    enriched["detail_summary_draft"] = extractive_detail_draft(enriched)
    enriched["detail_summary_prompt"] = summary_prompt(enriched)
    enriched["review_status"] = "pending_human_confirmation"
    enriched["notion_eligibility"] = "approved_only"
    return enriched


def enrich_originals(candidates: list[dict[str, Any]], timeout_seconds: int, limit: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Fetch only top candidate originals in parallel; a failed article does not stop the run."""
    selected = candidates[:limit]
    failures: dict[str, str] = {}
    enriched_by_url: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, max(1, len(selected)))) as pool:
        futures = {pool.submit(fetch_article, item, timeout_seconds): item for item in selected}
        for future, item in ((future, futures[future]) for future in futures):
            try:
                enriched_by_url[item["primary_source_url"]] = future.result()
            except Exception as error:
                failed = dict(item)
                failed["original_read_status"] = "failed"
                failed["review_status"] = "pending_human_confirmation"
                failed["notion_eligibility"] = "approved_only"
                enriched_by_url[item["primary_source_url"]] = failed
                failures[item["primary_source_url"]] = f"{type(error).__name__}: {error}"
    return [enriched_by_url.get(item["primary_source_url"], item) for item in candidates], failures


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen_identity_keys": [], "last_successful_run_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def load_approved_urls(path: Path | None) -> set[str]:
    """Read the human decision file; absence means no item is approved yet."""
    if path is None or not path.exists():
        return set()
    value = json.loads(path.read_text(encoding="utf-8"))
    return set(value.get("approved_urls", []))


def load_decisions(path: Path | None, approved_urls: set[str]) -> dict[str, dict[str, Any]]:
    """Load the human review ledger; older approval files remain supported."""
    decisions: dict[str, dict[str, Any]] = {url: {"status": "approved"} for url in approved_urls}
    if path is None or not path.exists():
        return decisions
    value = json.loads(path.read_text(encoding="utf-8"))
    for url, decision in value.get("decisions", {}).items():
        if isinstance(decision, dict):
            decisions[url] = decision
    return decisions


def load_watchlist_terms(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    return [str(term) for term in value.get("terms", []) if str(term).strip()]


def actionability(item: dict[str, Any], decision: dict[str, Any]) -> tuple[int | None, list[str]]:
    """Score portfolio practicality only from explicit human-verified facts."""
    checks = (
        ("code_available", 30, "코드 공개"),
        ("public_data", 30, "공개 데이터"),
        ("modest_compute", 20, "개인 규모 연산 가능"),
        ("accessible_license", 10, "접근 가능한 라이선스"),
        ("portfolio_fit", 10, "포트폴리오 주제로 적합"),
    )
    provided = [check for check in checks if check[0] in decision]
    if not provided:
        return None, ["실행 가능성은 코드·데이터·연산 조건을 확인한 뒤 평가"]
    score = sum(weight for key, weight, _ in provided if decision.get(key) is True)
    notes = [label for key, _, label in provided if decision.get(key) is True]
    return score, notes or ["확인된 실행 조건이 부족함"]


def watchlist_matches(item: dict[str, Any], terms: list[str]) -> list[str]:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    return [term for term in terms if term.casefold() in haystack]


def possible_event_clusters(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suggest—not merge—similar headlines, so the human can keep distinct events separate."""
    clusters: list[dict[str, Any]] = []
    token_sets = [set(re.findall(r"[a-z0-9]{4,}", item.get("title", "").casefold())) for item in items]
    for left, item in enumerate(items):
        related = [item]
        for right in range(left + 1, len(items)):
            if item.get("domains") != items[right].get("domains"):
                continue
            union = token_sets[left] | token_sets[right]
            similarity = len(token_sets[left] & token_sets[right]) / len(union) if union else 0
            if similarity >= 0.5:
                related.append(items[right])
        if len(related) > 1:
            urls = sorted(member["primary_source_url"] for member in related)
            if not any(cluster["urls"] == urls for cluster in clusters):
                clusters.append({
                    "suggested_event": item["title"],
                    "urls": urls,
                    "reason": "제목 핵심어가 겹쳐 같은 사건일 가능성이 있음; 자동 병합하지 않음",
                })
    return clusters


def word_counts(items: list[dict[str, Any]]) -> Counter[str]:
    words = Counter()
    for item in items:
        for word in re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9_-]{1,}", f"{item['title']} {item.get('summary', '')}".casefold()):
            # Lightweight Korean fallback when a morphological analyzer is unavailable.
            word = re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|와|과|도|만|까지)$", "", word)
            if word not in STOP_WORDS:
                words[word] += 1
    return words


def korean_word_counts(items: list[dict[str, Any]]) -> Counter[str]:
    """Count meaningful Korean nouns with Kiwi; keep an English fallback for mixed titles."""
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return word_counts(items)

    kiwi = Kiwi()
    words = Counter()
    for item in items:
        text = f"{item['title']} {item.get('summary', '')}"
        for token in kiwi.tokenize(text):
            word = token.form.casefold()
            if token.tag.startswith("N") and len(word) > 1 and word not in KOREAN_WORDCLOUD_STOP_WORDS:
                words[word] += 1
        # Kiwi is intentionally noun-first. Keep useful English product names in a mixed-language feed.
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text.casefold()):
            if word not in KOREAN_WORDCLOUD_STOP_WORDS:
                words[word] += 1
    return words


def write_wordcloud_png(counts: Counter[str], output_path: Path) -> None:
    """Write a Korean PNG word cloud using the same flow as the workshop notebook."""
    from PIL import Image, ImageDraw, ImageFont
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not counts:
        image = Image.new("RGB", (1200, 600), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(MALGUN_GOTHIC), 34) if MALGUN_GOTHIC.exists() else ImageFont.load_default()
        draw.text((80, 270), "이번 주 승인된 Industry 자료가 없습니다", font=font, fill="#334155")
        image.save(output_path, format="PNG")
        return
    # Rebuild text from the noun frequencies so WordCloud can use its familiar
    # generate_from_text() API while preserving Kiwi's Korean noun filtering.
    text_for_wc = " ".join(word for word, count in counts.items() for _ in range(count))
    cloud = WordCloud(
        font_path=str(MALGUN_GOTHIC) if MALGUN_GOTHIC.exists() else None,
        background_color="lightgrey",
        width=800,
        height=800,
        colormap="viridis",
        prefer_horizontal=0.85,
        random_state=42,
        collocations=False,
    )
    my_cloud = cloud.generate_from_text(text_for_wc)
    fig, axis = plt.subplots(figsize=(10, 10))
    axis.imshow(my_cloud)
    axis.axis("off")
    fig.savefig(output_path, format="png", bbox_inches="tight", pad_inches=0.1, dpi=120)
    plt.close(fig)


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
        pieces.append(f'<text x="{x}" y="{y}" font-family="Malgun Gothic, Arial, sans-serif" font-size="{size}" fill="{color}">{html.escape(word)}</text>')
        x += width
    pieces.append("</svg>")
    return "".join(pieces)


def build_report(
    feeds: dict[str, str],
    cache: dict[str, Any],
    now: datetime,
    industry_sources: set[str],
    timeout_seconds: int = 12,
    read_originals: bool = True,
    detail_limit: int = 8,
    approved_urls: set[str] | None = None,
    decisions: dict[str, dict[str, Any]] | None = None,
    watchlist_terms: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect quickly, then read originals only for the filtered review queue."""
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
    approved_urls = approved_urls or set()
    decisions = decisions or {}
    watchlist_terms = watchlist_terms or []
    for item in review_queue:
        decision = decisions.get(item["primary_source_url"], {})
        status = decision.get("status", "approved" if item["primary_source_url"] in approved_urls else "pending_human_confirmation")
        item["review_status"] = status if status in {"approved", "rejected", "later"} else "pending_human_confirmation"
        item["human_decision_reason"] = decision.get("reason", "")
        item["actionability_score"], item["actionability_evidence"] = actionability(item, decision)
        item["watchlist_matches"] = watchlist_matches(item, watchlist_terms)
        item["notion_eligibility"] = "approved_only"
    article_failures: dict[str, str] = {}
    if read_originals:
        review_queue, article_failures = enrich_originals(review_queue, timeout_seconds, detail_limit)
    for item in review_queue:
        decision = decisions.get(item["primary_source_url"], {})
        status = decision.get("status", "approved" if item["primary_source_url"] in approved_urls else "pending_human_confirmation")
        item["review_status"] = status if status in {"approved", "rejected", "later"} else "pending_human_confirmation"
        item["human_decision_reason"] = decision.get("reason", "")
        item["actionability_score"], item["actionability_evidence"] = actionability(item, decision)
        item["watchlist_matches"] = watchlist_matches(item, watchlist_terms)
        item["notion_eligibility"] = "approved_only"
    industry_items = [
        item for item in review_queue
        if item["source"] in industry_sources
        and item.get("original_read_status") == "read"
        and item["review_status"] == "approved"
    ]
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
            "originals_read": sum(item.get("original_read_status") == "read" for item in review_queue),
            "original_read_failures": len(article_failures),
            "human_approved": sum(item["review_status"] == "approved" for item in review_queue),
        },
        "source_failures": failures,
        "original_read_failures": article_failures,
        "candidates": review_queue,
        "possible_event_clusters": possible_event_clusters(review_queue),
        "trend_candidates": sorted(word_counts(industry_items).items(), key=lambda pair: (-pair[1], pair[0]))[:15],
        "notes": [
            "Candidates are not automatically saved to Notion; only a human-approved item can be stored.",
            "No candidate is a valid outcome; do not add weak material to fill the report.",
            "Trend words use only original-read Industry & Product Signals candidates and remain a review cue, not a confirmed industry trend.",
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
    parser.add_argument("--detail-limit", type=int, default=8, help="maximum filtered candidates whose originals are read")
    parser.add_argument("--skip-original-read", action="store_true", help="create a fast metadata-only report")
    parser.add_argument("--approval-file", type=Path, help="JSON file containing {\"approved_urls\": [\"https://...\"]}")
    parser.add_argument("--decision-file", type=Path, help="JSON review ledger with status, reason, and actionability evidence")
    parser.add_argument("--watchlist-file", type=Path, help="JSON file containing {\"terms\": [\"ECMWF\", \"LLM evaluation\"]}")
    arguments = parser.parse_args(argv)
    feeds = dict(value.split("=", 1) for value in arguments.feed if "=" in value)
    if not feeds:
        parser.error("at least one --feed NAME=URL is required")
    now = datetime.now(UTC)
    approved_urls = load_approved_urls(arguments.approval_file)
    report, new_cache = build_report(
        feeds,
        load_cache(arguments.cache),
        now,
        set(arguments.industry_source),
        arguments.timeout,
        read_originals=not arguments.skip_original_read,
        detail_limit=arguments.detail_limit,
        approved_urls=approved_urls,
        decisions=load_decisions(arguments.decision_file, approved_urls),
        watchlist_terms=load_watchlist_terms(arguments.watchlist_file),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    arguments.cache.parent.mkdir(parents=True, exist_ok=True)
    arguments.cache.write_text(json.dumps(new_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    arguments.wordcloud.parent.mkdir(parents=True, exist_ok=True)
    industry = [
        item for item in report["candidates"]
        if item["source"] in set(arguments.industry_source)
        and item.get("original_read_status") == "read"
        and item["review_status"] == "approved"
    ]
    write_wordcloud_png(korean_word_counts(industry), arguments.wordcloud)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
