"""naver_economy_news.json 로더."""

from __future__ import annotations

import json
from pathlib import Path

from config import NEWS_JSON_PATH
from schemas import NewsRecord


def load_news(path: Path = NEWS_JSON_PATH) -> list[NewsRecord]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    records = [
        NewsRecord(
            url_hash=item["url_hash"],
            url=item["url"],
            title=item["title"],
            content=item.get("content", ""),
            summary=item.get("summary", ""),
            published_at=item["published_at"],
        )
        for item in raw
    ]
    records.sort(key=lambda r: r.published_at)
    return records


def load_recent_news(limit: int, path: Path = NEWS_JSON_PATH) -> list[NewsRecord]:
    """가장 최근 뉴스 limit건을 시간순(과거->최근)으로 반환. 클러스터링은 시간순 처리가 전제."""
    records = load_news(path)
    return records[-limit:] if limit < len(records) else records
