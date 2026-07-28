"""대표 전략 템플릿 — 대시보드 "템플릿으로 시작하기"에서 즉시 생성 가능.

app/workflow/graph.py::WorkflowGraph.to_dict()와 동일한 모양(nodes/edges)을 그대로
쓴다. AIGenerateView.vue의 예시 아이디어(뉴스 긍정+상승/이평선 돌파+손절/RSI 과매도+
목표수익)와 겹치지 않게, 이번에 추가한 새 노드(momentum/rsi/rank/equal_weight/
max_position/stop_loss)를 실제로 쓰는 조합으로 구성한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowTemplate:
    id: str
    name: str
    description: str
    graph: dict


def _node(node_id: str, node_type: str, params: dict) -> dict:
    return {"id": node_id, "type": node_type, "params": params}


def _edge(from_: str, to: str, branch: str | None = None) -> dict:
    edge = {"from": from_, "to": to}
    if branch:
        edge["branch"] = branch
    return edge


def _ma_cross_template() -> WorkflowTemplate:
    graph = {
        "nodes": [
            _node("s1", "scheduler.interval", {"interval_sec": 60, "universe": "005930,000660"}),
            _node("p1", "data.price", {}),
            _node("ma1", "indicator.moving_average", {"window": 20}),
            _node("if1", "logic.if_else", {"expr": "price > ma_20"}),
            _node("buy1", "execution.market_order", {"side": "buy", "qty": 1}),
        ],
        "edges": [
            _edge("s1", "p1"),
            _edge("p1", "ma1"),
            _edge("ma1", "if1"),
            _edge("if1", "buy1", "true"),
        ],
    }
    return WorkflowTemplate(
        id="tmpl_ma_cross",
        name="이동평균 상향 돌파 매수",
        description="20일 이동평균선보다 현재가가 높으면(상향 돌파 상태) 매수합니다.",
        graph=graph,
    )


def _rsi_reversion_template() -> WorkflowTemplate:
    graph = {
        "nodes": [
            _node("s1", "scheduler.interval", {"interval_sec": 60, "universe": "005930,000660"}),
            _node("p1", "data.price", {}),
            _node("rsi1", "indicator.rsi", {"period": 14}),
            _node("if_buy", "logic.if_else", {"expr": "rsi_14 < 30"}),
            _node("buy1", "execution.market_order", {"side": "buy", "qty": 1}),
        ],
        "edges": [
            _edge("s1", "p1"),
            _edge("p1", "rsi1"),
            _edge("rsi1", "if_buy"),
            _edge("if_buy", "buy1", "true"),
        ],
    }
    return WorkflowTemplate(
        id="tmpl_rsi_reversion",
        name="RSI 과매도 매수",
        description="RSI(14)가 30 밑으로 떨어져 과매도 구간에 진입하면 매수합니다.",
        graph=graph,
    )


def _momentum_topn_template() -> WorkflowTemplate:
    graph = {
        "nodes": [
            _node(
                "s1",
                "scheduler.interval",
                {"interval_sec": 60, "universe": "005930,000660,035420,035720,051910"},
            ),
            _node("p1", "data.price", {}),
            _node("mom1", "indicator.momentum", {"period": 20}),
            _node("rank1", "logic.rank", {"key": "momentum_20", "top_n": 2, "order": "desc"}),
            _node("port1", "portfolio.equal_weight", {"allocation_ratio": 0.9}),
            _node("risk1", "risk.max_position", {"max_weight": 0.4}),
            _node("buy1", "execution.market_order", {"side": "buy", "qty": 1}),
        ],
        "edges": [
            _edge("s1", "p1"),
            _edge("p1", "mom1"),
            _edge("mom1", "rank1"),
            _edge("rank1", "port1"),
            _edge("port1", "risk1"),
            _edge("risk1", "buy1"),
        ],
    }
    return WorkflowTemplate(
        id="tmpl_momentum_topn",
        name="모멘텀 상위 종목 분산 매수",
        description="20거래일 수익률 상위 2개 종목을 골라 현금을 균등 배분해 매수합니다(종목당 비중 40% 상한).",
        graph=graph,
    )


def _stop_loss_template() -> WorkflowTemplate:
    graph = {
        "nodes": [
            _node("s1", "scheduler.interval", {"interval_sec": 60, "universe": "005930,000660"}),
            _node("p1", "data.price", {}),
            _node("risk1", "risk.stop_loss", {"loss_pct": 5.0}),
            _node("sell1", "execution.market_order", {"side": "sell", "qty": 1}),
        ],
        "edges": [
            _edge("s1", "p1"),
            _edge("p1", "risk1"),
            _edge("risk1", "sell1"),
        ],
    }
    return WorkflowTemplate(
        id="tmpl_stop_loss",
        name="보유 종목 손절",
        description="보유 중인 종목이 평단가 대비 5% 이상 손실이면 매도합니다.",
        graph=graph,
    )


def get_templates() -> list[WorkflowTemplate]:
    return [
        _ma_cross_template(),
        _rsi_reversion_template(),
        _momentum_topn_template(),
        _stop_loss_template(),
    ]
