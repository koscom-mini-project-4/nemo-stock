"""관리자 페이지 "분석된 뉴스"/"미분석 뉴스" 섹션(§0-12)이 쓰는 db.py::count_pending/
list_analyzed_news + api.py::NewsTrader.pending_news/pending_count/analyzed_news에 대한
유닛 테스트.
"""

from __future__ import annotations

from app.vendor.news_classifier import db
from app.vendor.news_classifier.api import NewsTrader
from app.vendor.news_classifier.config import Settings


def _seed_pending(conn, url_hash: str, title: str, published_at: str) -> None:
    """크롤링만 되고 아직 분류 안 된(classified=0) 기사."""
    db.mark_crawled(
        conn,
        [
            {
                "url_hash": url_hash, "url": f"https://example.com/{url_hash}", "title": title,
                "content": "본문", "summary": "요약", "published_at": published_at,
            }
        ],
    )


def _seed_analyzed(conn, url_hash: str, title: str, published_at: str, *, stock=None, sector=None, macro=None) -> int:
    """크롤링 + 분류까지 끝난(classified=1) 기사. 종목/섹터/거시 중 여러 개를 리스트로 줄 수 있다."""
    _seed_pending(conn, url_hash, title, published_at)
    cluster_id = db.create_cluster(conn, title, published_at, 0.5)
    records = []
    stocks = stock if isinstance(stock, list) else ([stock] if stock else [None])
    for s in stocks:
        records.append(
            {
                "제목": title, "종목": s, "섹터": sector, "거시지표": macro,
                "날짜": published_at, "스트렝스": 0.5, "클러스터id": cluster_id, "대표제목": title,
            }
        )
    db.save_classifications(conn, url_hash, records)
    db.mark_classified(conn, [url_hash])
    return cluster_id


def test_count_pending_only_counts_unclassified():
    conn = db.connect(":memory:")
    _seed_pending(conn, "p1", "미분석 기사1", "2026-07-28 09:00:00")
    _seed_pending(conn, "p2", "미분석 기사2", "2026-07-28 10:00:00")
    _seed_analyzed(conn, "a1", "분석된 기사", "2026-07-28 11:00:00", stock="삼성전자")

    assert db.count_pending(conn) == 2


def test_pending_news_returns_unclassified_oldest_first():
    conn = db.connect(":memory:")
    _seed_pending(conn, "p1", "나중 기사", "2026-07-28 12:00:00")
    _seed_pending(conn, "p2", "먼저 기사", "2026-07-28 09:00:00")
    _seed_analyzed(conn, "a1", "분석됨", "2026-07-28 10:00:00", stock="삼성전자")

    items = db.pending_news(conn)
    assert [i["title"] for i in items] == ["먼저 기사", "나중 기사"]


def test_list_analyzed_news_collapses_multi_entity_article_into_one_row():
    """여러 종목/섹터가 걸린 기사 하나는 한 행으로 접히고, stocks/sectors는 리스트가 된다."""
    conn = db.connect(":memory:")
    _seed_analyzed(
        conn, "a1", "삼성전자·SK하이닉스 반도체 동반 강세", "2026-07-28 09:00:00",
        stock=["삼성전자", "SK하이닉스"], sector="반도체 및 반도체 장비",
    )

    rows = db.list_analyzed_news(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["url_hash"] == "a1"
    assert set(row["stocks"]) == {"삼성전자", "SK하이닉스"}
    assert row["sectors"] == ["반도체 및 반도체 장비"]
    assert row["macros"] == []


def test_list_analyzed_news_ordered_newest_first_and_respects_limit():
    conn = db.connect(":memory:")
    _seed_analyzed(conn, "a1", "오래된 기사", "2026-07-26 09:00:00", stock="삼성전자")
    _seed_analyzed(conn, "a2", "최신 기사", "2026-07-28 09:00:00", stock="삼성전자")

    rows = db.list_analyzed_news(conn, limit=1)
    assert len(rows) == 1
    assert rows[0]["title"] == "최신 기사"


def test_news_trader_pending_and_analyzed_methods_delegate_to_db():
    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False))
    _seed_pending(trader.conn, "p1", "미분석", "2026-07-28 09:00:00")
    _seed_analyzed(trader.conn, "a1", "분석됨", "2026-07-28 10:00:00", stock="삼성전자")

    assert trader.pending_count() == 1
    assert [i["title"] for i in trader.pending_news()] == ["미분석"]
    assert [i["title"] for i in trader.analyzed_news()] == ["분석됨"]
    trader.close()
