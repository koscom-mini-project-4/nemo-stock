from __future__ import annotations

from datetime import datetime

from app.broker.dummy import DummyOrderExecutionProvider
from app.dao.base import DisclosureRecord, NewsRecord
from app.dao.memory.repositories import (
    InMemoryAIScoreCacheRepository,
    InMemoryDisclosureRepository,
    InMemoryNewsRepository,
)
from app.market_data.dummy import DummyMarketDataProvider
from app.nodes import load_all_nodes
from app.workflow.engine import WorkflowEngine
from app.workflow.events import InMemoryEventBus
from app.workflow.graph import WorkflowGraph
from tests.unit.ai_test_doubles import FakeAIClient

load_all_nodes()


def _news_sentiment_graph(threshold_expr: str) -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.news", "params": {"limit": 2}},
            {"id": "n4", "type": "ai.sentiment_score", "params": {"source": "news"}},
            {"id": "n5", "type": "logic.if_else", "params": {"expr": threshold_expr}},
            {"id": "n6", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
            {"from": "n4", "to": "n5"},
            {"from": "n5", "to": "n6"},
        ],
    }


def _run(graph_dict: dict, extra_providers: dict):
    graph = WorkflowGraph.from_dict(graph_dict)
    engine = WorkflowEngine(InMemoryEventBus())
    market_data = DummyMarketDataProvider(seed_prices={"005930": 70000}, seed=1)
    broker = DummyOrderExecutionProvider(initial_cash=100_000_000)
    return engine.execute(
        workflow_id="wf1", graph=graph, mode="test", market_data=market_data, broker=broker,
        extra_providers=extra_providers,
    )


def test_news_sentiment_positive_leads_to_buy():
    news_repo = InMemoryNewsRepository()
    news_repo.save_many(
        [NewsRecord(id="news-1", symbol="005930", title="실적 서프라이즈", body="영업이익 급증", published_at=datetime.now())]
    )
    cache_repo = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": 80, "summary": "매우 긍정적"}])

    result = _run(
        _news_sentiment_graph("sentiment_score > 50"),
        extra_providers={"ai_client": ai_client, "ai_score_cache_repo": cache_repo, "news_repo": news_repo, "disclosure_repo": InMemoryDisclosureRepository()},
    )

    assert result.status == "success"
    final = result.final_context
    assert final.symbols["005930"]["order_status"] == "filled"
    assert final.symbols["005930"]["sentiment_score"] == 80.0


def test_news_sentiment_negative_blocks_buy():
    news_repo = InMemoryNewsRepository()
    news_repo.save_many(
        [NewsRecord(id="news-2", symbol="005930", title="실적 부진", body="영업손실 확대", published_at=datetime.now())]
    )
    cache_repo = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": -60, "summary": "매우 부정적"}])

    result = _run(
        _news_sentiment_graph("sentiment_score > 50"),
        extra_providers={"ai_client": ai_client, "ai_score_cache_repo": cache_repo, "news_repo": news_repo, "disclosure_repo": InMemoryDisclosureRepository()},
    )

    assert result.status == "success"
    assert result.final_context.symbols == {}  # if_else에서 탈락


def test_disclosure_node_feeds_sentiment_score_with_cache_reuse():
    disclosure_repo = InMemoryDisclosureRepository()
    disclosure_repo.save_many(
        [
            DisclosureRecord(
                id="rcept-1", symbol="005930", corp_name="삼성전자",
                report_nm="유상증자결정", rcept_dt=datetime.now().date(),
            )
        ]
    )
    cache_repo = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": -20, "summary": "희석 우려"}])

    graph_dict = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.disclosure", "params": {"limit": 1}},
            {"id": "n3", "type": "ai.sentiment_score", "params": {"source": "disclosure"}},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }
    extra = {
        "ai_client": ai_client, "ai_score_cache_repo": cache_repo,
        "news_repo": InMemoryNewsRepository(), "disclosure_repo": disclosure_repo,
    }

    result1 = _run(graph_dict, extra)
    assert result1.final_context.symbols["005930"]["sentiment_score"] == -20.0
    assert len(ai_client.calls) == 1

    # 동일 공시로 재실행 시 캐시가 재사용되어 AI가 다시 호출되지 않아야 한다.
    result2 = _run(graph_dict, extra)
    assert result2.final_context.symbols["005930"]["sentiment_score"] == -20.0
    assert len(ai_client.calls) == 1


def test_sentiment_node_without_source_data_sets_none():
    cache_repo = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[])
    result = _run(
        _news_sentiment_graph("sentiment_score is not None and sentiment_score > 50"),
        extra_providers={
            "ai_client": ai_client, "ai_score_cache_repo": cache_repo,
            "news_repo": InMemoryNewsRepository(), "disclosure_repo": InMemoryDisclosureRepository(),
        },
    )
    assert result.status == "success"
    assert result.final_context.symbols == {}
    assert len(ai_client.calls) == 0
