"""nemo-stock 통합 시 추가한 클러스터↔종목/섹터/거시 상호 탐색 기능(§0-7)에 대한 회귀 테스트.

db.py::cluster_tags/cluster_stats(확장), api.py::NewsTrader.clusters_for_key/keys_in_range —
VENDOR_NOTES.md에 기록된 수정 사항.
"""

from __future__ import annotations

from app.vendor.news_classifier import db
from app.vendor.news_classifier.api import NewsTrader
from app.vendor.news_classifier.config import Settings


def _seed(conn) -> tuple[int, int]:
    cluster_a = db.create_cluster(conn, "삼성전자 HBM 수주", "2026-07-28 09:00:00", 0.8)
    db.save_news(
        conn,
        {"url_hash": "a1", "url": "u1", "title": "삼성전자 HBM 수주", "published_at": "2026-07-28 09:00:00"},
        cluster_a,
    )
    db.save_classifications(
        conn,
        "a1",
        [
            {
                "제목": "삼성전자 HBM 수주", "종목": "삼성전자", "섹터": "반도체", "거시지표": None,
                "날짜": "2026-07-28 09:00:00", "스트렝스": 0.8, "클러스터id": cluster_a,
                "대표제목": "삼성전자 HBM 수주",
            }
        ],
    )

    cluster_b = db.create_cluster(conn, "반도체 업황 우려", "2026-07-27 10:00:00", -0.5)
    db.save_news(
        conn,
        {"url_hash": "b1", "url": "u2", "title": "반도체 업황 우려", "published_at": "2026-07-27 10:00:00"},
        cluster_b,
    )
    db.save_classifications(
        conn,
        "b1",
        [
            {
                "제목": "반도체 업황 우려", "종목": None, "섹터": "반도체", "거시지표": "금리",
                "날짜": "2026-07-27 10:00:00", "스트렝스": -0.5, "클러스터id": cluster_b,
                "대표제목": "반도체 업황 우려",
            }
        ],
    )
    return cluster_a, cluster_b


def test_cluster_tags_returns_linked_keys_deduped_and_without_nulls():
    conn = db.connect(":memory:")
    cluster_a, cluster_b = _seed(conn)

    assert db.cluster_tags(conn, cluster_a) == {"종목": ["삼성전자"], "섹터": ["반도체"], "거시지표": []}
    assert db.cluster_tags(conn, cluster_b) == {"종목": [], "섹터": ["반도체"], "거시지표": ["금리"]}


def test_cluster_stats_embeds_tags_per_cluster():
    conn = db.connect(":memory:")
    _seed(conn)

    rows = db.cluster_stats(conn, "2026-07-27 00:00:00", "2026-07-28 23:59:59")
    by_title = {r["representative_title"]: r for r in rows}

    assert by_title["삼성전자 HBM 수주"]["종목"] == ["삼성전자"]
    assert by_title["반도체 업황 우려"]["거시지표"] == ["금리"]


def test_news_trader_clusters_for_key_finds_clusters_by_sector():
    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False))
    _seed(trader.conn)

    rows = trader.clusters_for_key("B", "반도체", "2026-07-27 00:00:00", "2026-07-28 23:59:59")

    assert {r["cluster_id"] for r in rows} == {1, 2}  # 두 클러스터 다 섹터=반도체로 연결됨
    trader.close()


def test_news_trader_clusters_for_key_by_stock_finds_only_matching_cluster():
    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False))
    cluster_a, _cluster_b = _seed(trader.conn)

    rows = trader.clusters_for_key("A", "삼성전자", "2026-07-27 00:00:00", "2026-07-28 23:59:59")

    assert [r["cluster_id"] for r in rows] == [cluster_a]
    trader.close()


def test_news_trader_keys_in_range_lists_distinct_keys_for_group():
    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False))
    _seed(trader.conn)

    assert trader.keys_in_range("B", "2026-07-27 00:00:00", "2026-07-28 23:59:59") == ["반도체"]
    assert trader.keys_in_range("A", "2026-07-27 00:00:00", "2026-07-28 23:59:59") == ["삼성전자"]
    assert trader.keys_in_range("C", "2026-07-27 00:00:00", "2026-07-28 23:59:59") == ["금리"]
    trader.close()
