"""매매 조건 프리셋 시스템(app/nodes/conditions.py) 단위 테스트."""

from __future__ import annotations

from datetime import datetime

from app.nodes.base import NodeContext
from app.nodes.conditions import (
    CUSTOM_KEY,
    PASS_PRESET,
    Preset,
    apply_condition,
    condition_params,
    resolve_condition,
)

PRESETS = [
    Preset("leader", "주도 (≥ 0.5)", "이상", 0.5),
    Preset("weak", "약세 (≤ -0.3)", "이하", -0.3),
    PASS_PRESET,
]


class _FakeNode:
    def __init__(self, params):
        self.node_id = "n1"
        self.params = params

    def get_param(self, key, default=None):
        return self.params.get(key, default)


def test_condition_params_shape():
    schema = condition_params(PRESETS, "leader")
    cond = schema[0]
    assert cond["key"] == "condition"
    assert cond["options"] == ["leader", "weak", "pass", CUSTOM_KEY]
    assert cond["option_labels"][-1] == "직접 설정(연산자·기준값 입력)"
    # 연산자/기준값은 custom일 때만 노출(show_if)
    assert schema[1]["show_if"] == {"param": "condition", "equals": CUSTOM_KEY}
    assert schema[2]["show_if"] == {"param": "condition", "equals": CUSTOM_KEY}


def test_resolve_preset():
    assert resolve_condition(_FakeNode({"condition": "leader"}), PRESETS, "x") == ("이상", 0.5, "x")


def test_resolve_custom():
    node = _FakeNode({"condition": "custom", "operator": "미만", "threshold": 2.0})
    assert resolve_condition(node, PRESETS, "x") == ("미만", 2.0, "x")


def test_resolve_pass_is_none():
    assert resolve_condition(_FakeNode({"condition": "pass"}), PRESETS, "x") is None


def test_preset_field_override():
    presets = [Preset("ovs", "해외", "미만", 0.0, field="overseas")]
    assert resolve_condition(_FakeNode({"condition": "ovs"}), presets, "domestic") == ("미만", 0.0, "overseas")


def _ctx(symbols):
    return NodeContext(run_id="r", mode="test", timestamp=datetime(2026, 7, 19), symbols=symbols)


def test_apply_condition_filters_by_field():
    out = _ctx({"A": {"v": 0.8}, "B": {"v": 0.1}, "C": {"v": None}})
    apply_condition(_FakeNode({"condition": "leader"}), out, PRESETS, "v")
    assert set(out.symbols) == {"A"}  # 0.8≥0.5 통과, 0.1·None 탈락
    assert out.meta["filtered_out"]["n1"] == ["B", "C"] or set(out.meta["filtered_out"]["n1"]) == {"B", "C"}


def test_apply_condition_pass_keeps_all():
    out = _ctx({"A": {"v": -9.0}, "B": {"v": 9.0}})
    apply_condition(_FakeNode({"condition": "pass"}), out, PRESETS, "v")
    assert set(out.symbols) == {"A", "B"}  # 필터 안 함


def test_apply_condition_records_decisions():
    """nemo-stock 통합 시 추가한 부분(fork 원본에는 없음): 다른 필터형 노드(if_else/rank/
    stop_loss/indicator.base)와 동일한 meta.decisions 공통 포맷으로 판단 근거를 남긴다."""
    out = _ctx({"A": {"v": 0.8}, "B": {"v": 0.1}, "C": {"v": None}})
    apply_condition(_FakeNode({"condition": "leader"}), out, PRESETS, "v")

    decisions = out.meta["decisions"]["n1"]
    assert decisions["A"]["pass"] is True
    assert decisions["B"]["pass"] is False
    assert decisions["C"]["pass"] is False
    assert "값 없음" in decisions["C"]["reason"]
