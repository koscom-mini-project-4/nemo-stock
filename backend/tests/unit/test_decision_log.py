"""필터형 노드(logic.if_else / logic.rank / risk.stop_loss)의 판단(meta.decisions) 로그 테스트.

"테스트 실행" 디버그 패널이 각 노드의 통과/탈락 근거를 보여줄 수 있도록, 이 노드들이
context.meta.decisions[node_id][symbol] = {"pass": bool, "reason": str} 형태로 판단 근거를
기록하는지 검증한다.
"""

from __future__ import annotations

from datetime import datetime

from app.nodes import load_all_nodes
from app.nodes.base import NodeContext, create_node

load_all_nodes()


def _ctx(symbols: dict[str, dict]) -> NodeContext:
    ctx = NodeContext(run_id="r1", mode="test", timestamp=datetime(2026, 6, 30))
    for symbol, data in symbols.items():
        ctx.symbols[symbol] = dict(data)
    return ctx


def test_if_else_decision_pass_and_fail():
    node = create_node("logic.if_else", "if1", {"expr": "price > 100"})
    out = node.execute(_ctx({"A": {"price": 150}, "B": {"price": 50}}))

    assert "A" in out.symbols and "B" not in out.symbols
    decisions = out.meta["decisions"]["if1"]
    assert decisions["A"]["pass"] is True
    assert "price > 100" in decisions["A"]["reason"]
    assert decisions["B"]["pass"] is False


def test_if_else_decision_records_eval_error():
    node = create_node("logic.if_else", "if1", {"expr": "missing_key > 1"})
    out = node.execute(_ctx({"A": {"price": 100}}))

    assert "A" not in out.symbols
    decision = out.meta["decisions"]["if1"]["A"]
    assert decision["pass"] is False
    assert "평가 오류" in decision["reason"]


def test_rank_decision_top_and_out_of_range():
    node = create_node("logic.rank", "rank1", {"key": "score", "top_n": 1, "order": "desc"})
    out = node.execute(_ctx({"A": {"score": 10}, "B": {"score": 5}, "C": {}}))

    decisions = out.meta["decisions"]["rank1"]
    assert decisions["A"]["pass"] is True
    assert "상위 1/1" in decisions["A"]["reason"]
    assert decisions["B"]["pass"] is False
    assert "순위 밖" in decisions["B"]["reason"]
    assert decisions["C"]["pass"] is False
    assert "값 없음" in decisions["C"]["reason"]


def test_stop_loss_decision_triggered_and_not_held():
    node = create_node("risk.stop_loss", "sl1", {"loss_pct": 5.0})
    out = node.execute(
        _ctx(
            {
                "A": {"held_qty": 10, "held_avg_price": 100.0, "price": 90.0},  # -10% 손실 → 손절
                "B": {"held_qty": 0, "held_avg_price": 0.0, "price": 90.0},  # 미보유
            }
        )
    )

    decisions = out.meta["decisions"]["sl1"]
    assert "A" in out.symbols
    assert decisions["A"]["pass"] is True
    assert "손실률" in decisions["A"]["reason"]
    assert "B" not in out.symbols
    assert decisions["B"]["pass"] is False
    assert "보유 없음" in decisions["B"]["reason"]
