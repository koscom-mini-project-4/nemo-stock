"""터미널에서 네이버 뉴스 검색(search.naver.com)으로 특정 키워드의 뉴스를 딥 크롤링해
newsstock.db에 저장하고 AI로 분류하는 CLI.

경제 섹션 목록만 훑는 `POST /data/news/update`와 달리, 검색어로 전체 언론사 기사를
최신순으로 찾는다 — 코스닥/코스피 소형주처럼 경제 섹션 헤드라인에 잘 안 실리는 종목에
적합하다(`app/vendor/news_classifier/search_crawler.py` 참조, 2026-07-29 "아이씨에이치"
실사용 계기로 신설).

사용 예:
    cd backend
    ./.venv/bin/python -m app.cli.ingest_news_search --query 아이씨에이치 --days 8 --model gpt-5-nano
"""

from __future__ import annotations

import argparse
import uuid

from app.config import get_settings
from app.dao.base import AIUsageRecord
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import SqliteAIUsageRepository
from app.vendor.news_classifier import classifier as newsstock_classifier
from app.vendor.news_classifier import db as newsdb
from app.vendor.news_classifier.pipeline import classify_many
from app.vendor.news_classifier.search_crawler import crawl_search


def _progress(n: int, msg: str) -> None:
    print(f"[{n}] {msg}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="네이버 뉴스 검색으로 키워드 뉴스를 딥 크롤링하고 AI로 분류해 newsstock.db에 저장한다."
    )
    parser.add_argument("--query", required=True, help="검색어(제목/본문 어디든 포함된 기사를 찾는다)")
    parser.add_argument("--days", type=int, default=8, help="최근 며칠치까지 포함할지(기본 8)")
    parser.add_argument("--max-results", type=int, default=100, help="검토할 검색 결과 후보 최대 건수")
    parser.add_argument("--model", default=None, help="분류에 쓸 OpenAI 모델(기본: .env의 OPENAI_MODEL)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    settings = get_settings()

    engine = make_engine(settings.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    ai_usage_repo = SqliteAIUsageRepository(session_factory)

    def _record_usage(purpose, model, prompt_tokens, completion_tokens, total_tokens):
        ai_usage_repo.save(
            AIUsageRecord(
                id=str(uuid.uuid4()), purpose=purpose, model=model,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        )

    newsstock_classifier.set_usage_sink(_record_usage)

    conn = newsdb.connect(settings.newsstock_db_path)
    try:
        model = args.model or settings.openai_model
        collected = crawl_search(
            conn, args.query, days=args.days, max_results=args.max_results,
            workers=args.workers, progress=_progress,
        )
        print(f"수집: {len(collected)}건")

        pending = newsdb.pending_news(conn)
        print(f"AI 분류 대상(미분류 전체): {len(pending)}건, 모델={model}")
        if pending:
            classify_many(
                conn, pending, purge=False,
                progress=lambda i, n: _progress(i, f"분류 {i}/{n}"),
                model=model, api_key=settings.openai_api_key or "",
            )
            newsdb.mark_classified(conn, [n["url_hash"] for n in pending])
        print("완료")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
