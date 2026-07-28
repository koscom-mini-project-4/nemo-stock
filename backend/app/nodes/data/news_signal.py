"""뉴스 신호 노드(종합 판단용) — 계산 + 매매 조건을 자체 내장한 필터 노드.

수집 시점에 계산되어 쌓인 뉴스 충격량(NewsSignalRecord)을 섹터·기간으로 집계한 지표를
컨텍스트에 실은 뒤, **노드가 직접 '살지 말지'를 판단(필터)**한다. 별도 IF 노드가 필요 없고,
노드를 직렬로 이으면 AND가 된다.

조건은 초보자도 쉽게 고를 수 있도록 노드마다 **큐레이션된 프리셋**(사람이 읽는 라벨)을 제공한다.
'직접 설정'을 고르면 연산자/기준값을 직접 입력할 수 있다(app/nodes/conditions.py).

지표는 섹터/시장 단위라 컨텍스트의 모든 종목 데이터에 동일 값을 stamp하고 meta.news_signals에도
남긴다(디버그/관전용). 조건 판정은 그 stamp된 값으로 이뤄진다.
"""

from __future__ import annotations

from datetime import timedelta

from app.ai.news_classify import EVENT_TYPES
from app.dao.base import NewsSignalRepository
from app.news_signals.sectors import SECTORS
from app.news_signals.themes import ALL_THEMES

# 섹터 선택 파라미터(필수형/선택형). 선택형은 '전체(시장)' = 빈 문자열.
_SECTOR_REQUIRED: NodeParam = {
    "key": "sector", "type": "select", "label": "섹터", "required": True, "default": "반도체",
    "options": SECTORS, "group": "calc", "hint": "표준 섹터에서 선택",
}
_SECTOR_OPTIONAL: NodeParam = {
    "key": "sector", "type": "select", "label": "섹터", "required": False, "default": "",
    "options": ["", *SECTORS], "option_labels": ["전체(시장)", *SECTORS],
    "group": "calc", "hint": "비우면(전체) 시장 전체",
}
from app.news_signals.aggregate import (
    buzz_zscore,
    event_density,
    macro_risk_density,
    macro_sentiment_index,
    momentum_change,
    sector_linked_impact,
    sector_momentum,
    sentiment_ratio,
    symbol_direct_impact,
    symbol_news_stats,
    theme_zscore,
)
from app.nodes.base import Node, NodeContext, NodeParam, register_node
from app.nodes.conditions import PASS_PRESET, Preset, apply_condition, condition_params


def _repo(providers: dict) -> NewsSignalRepository:
    repo = providers.get("news_signal_repo")
    if not isinstance(repo, NewsSignalRepository):
        raise RuntimeError("뉴스 신호 노드 실행에는 news_signal_repo provider가 필요합니다.")
    return repo


def _stamp(out: NodeContext, key: str, value: object) -> None:
    """모든 종목 데이터와 meta.news_signals에 지표값을 기록한다."""
    for data in out.symbols.values():
        data[key] = value
    out.meta.setdefault("news_signals", {})[key] = value


@register_node
class SectorMomentumNode(Node):
    type = "data.sector_momentum"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "섹터 모멘텀 지수"
    description = "최근 N일 특정 섹터 뉴스들의 충격량 평균(주도 여부)을 계산하고, 조건을 만족하는 종목만 통과."
    example = "예: '주도 섹터 (모멘텀 ≥ 0.5)' 선택 시, 반도체 모멘텀이 0.5 이상일 때만 매수 진행"
    condition_field = "sector_momentum"
    condition_presets = [
        Preset("leader", "주도 섹터 (모멘텀 ≥ 0.5)", "이상", 0.5),
        Preset("strong", "강한 주도 (≥ 1.0)", "이상", 1.0),
        Preset("mild", "완만한 강세 (≥ 0.2)", "이상", 0.2),
        Preset("weak", "약세 섹터 (≤ -0.3)", "이하", -0.3),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        _SECTOR_REQUIRED,
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 7,
         "required": False, "group": "calc", "hint": "주간=7"},
        *condition_params(condition_presets, "leader"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        sector = str(self.get_param("sector", "")).strip()
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "sector_momentum", sector_momentum(signals, sector, out.timestamp, window_days=window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class MacroRiskNode(Node):
    type = "data.macro_risk"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "매크로 공포 지수"
    description = "최근 N일 매크로/지정학 리스크 뉴스의 도배율(%)을 계산. 킬스위치(공포 국면 회피)로 사용."
    example = "예: '공포 국면 (≥ 40%)' 선택 시, 리스크 뉴스 비율이 40% 이상일 때만 통과(전량 매도 등)"
    condition_field = "macro_risk_density"
    condition_presets = [
        Preset("fear", "공포 국면 (≥ 40%)", "이상", 40.0),
        Preset("caution", "경계 (≥ 25%)", "이상", 25.0),
        Preset("calm", "안정 (< 15%)", "미만", 15.0),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 3,
         "required": False, "group": "calc", "hint": "단기=3"},
        *condition_params(condition_presets, "fear"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        window = int(self.get_param("window_days", 3))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "macro_risk_density", macro_risk_density(signals, out.timestamp, window_days=window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class ThemeZScoreNode(Node):
    type = "data.theme_zscore"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "테마 쏠림 Z-Score"
    description = "특정 테마가 평소 대비 얼마나 비정상적으로 많이 언급되는지의 통계량으로 급등 테마를 포착."
    example = "예: '테마 급등 (Z ≥ 1.5)' 선택 시, HBM 테마가 평소 대비 급증할 때만 매수"
    condition_field = "theme_zscore"
    condition_presets = [
        Preset("spike", "테마 급등 (Z ≥ 1.5)", "이상", 1.5),
        Preset("strong_spike", "강한 급등 (≥ 2.0)", "이상", 2.0),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "theme", "type": "select", "label": "테마", "required": True, "default": "HBM",
         "options": ALL_THEMES, "group": "calc", "hint": "미리 정의된 투자 테마에서 선택"},
        {"key": "lookback_days", "type": "number", "label": "기준 기간(일)", "default": 20,
         "required": False, "group": "calc", "hint": "일평균·표준편차 산정 기간"},
        *condition_params(condition_presets, "spike"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        theme = str(self.get_param("theme", "")).strip()
        lookback = int(self.get_param("lookback_days", 20))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=lookback + 1))
        _stamp(out, "theme_zscore", theme_zscore(signals, theme, out.timestamp, lookback_days=lookback))
        _stamp(out, "theme_mentions_today", sum(
            1 for s in signals if s.published_at.date() == out.timestamp.date() and theme in (s.themes or [])
        ))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class SentimentRatioNode(Node):
    type = "data.sentiment_ratio"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "감성 우위도(Bull-Bear)"
    description = "최근 N일 뉴스의 (호재−악재)/전체 비율(-1~+1). 가중치 무시한 순수 방향 투표로 판단."
    example = "예: '호재 우세 (≥ 0.3)' 선택 시, 다수 뉴스가 호재로 쏠릴 때만 매수. 섹터 비우면 시장 전체."
    condition_field = "sentiment_ratio"
    condition_presets = [
        Preset("bullish", "호재 우세 (≥ 0.3)", "이상", 0.3),
        Preset("strong_bull", "강한 호재 우세 (≥ 0.6)", "이상", 0.6),
        Preset("bearish", "악재 우세 (≤ -0.3)", "이하", -0.3),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        _SECTOR_OPTIONAL,
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 7,
         "required": False, "group": "calc", "hint": "주간=7"},
        *condition_params(condition_presets, "bullish"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        sector = str(self.get_param("sector", "")).strip() or None
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "sentiment_ratio", sentiment_ratio(signals, out.timestamp, sector, window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class SymbolNewsScoreNode(Node):
    type = "data.symbol_news_score"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "종목 뉴스 점수"
    description = "이 종목에 직접 붙은 뉴스의 base_impact 평균(종목별로 다른 값)으로 종목별 압력을 판단."
    example = "예: '긍정 뉴스 압력 (≥ 0.5)' 선택 시, 그 종목 뉴스가 우호적인 종목만 통과"
    condition_field = "symbol_news_score"
    condition_presets = [
        Preset("positive", "긍정 뉴스 압력 (≥ 0.5)", "이상", 0.5),
        Preset("strong", "강한 긍정 (≥ 1.0)", "이상", 1.0),
        Preset("negative", "부정 뉴스 압력 (≤ -0.5)", "이하", -0.5),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 7,
         "required": False, "group": "calc", "hint": "주간=7"},
        *condition_params(condition_presets, "positive"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        for symbol, data in out.symbols.items():
            score, count = symbol_news_stats(signals, symbol, out.timestamp, window_days=window)
            data["symbol_news_score"] = score
            data["symbol_news_count"] = count
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class SymbolDirectImpactNode(Node):
    type = "data.symbol_direct_impact"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "종목 직접 영향 지표"
    description = (
        "이 종목에 직접 꽂힌 뉴스의 충격량을 -1~+1로 정규화한 지표. "
        "이벤트 종류가 달라도 같은 척도로 '얼마나 강한 뉴스가 직접 붙었는가'를 판단한다."
    )
    example = "예: '직접 영향 강함 (≥ 0.5)' 선택 시, SK하이닉스에 강한 호재 뉴스가 직접 붙은 경우만 통과"
    condition_field = "symbol_direct_impact"
    condition_presets = [
        Preset("very_strong", "매우 강한 직접 호재 (≥ 0.7)", "이상", 0.7),
        Preset("strong", "강한 직접 호재 (≥ 0.5)", "이상", 0.5),
        Preset("moderate", "보통 이상 직접 호재 (≥ 0.3)", "이상", 0.3),
        Preset("negative", "직접 악재 (≤ -0.3)", "이하", -0.3),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 7,
         "required": False, "group": "calc", "hint": "주간=7"},
        *condition_params(condition_presets, "strong"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        for symbol, data in out.symbols.items():
            data["symbol_direct_impact"] = symbol_direct_impact(
                signals, symbol, out.timestamp, window_days=window
            )
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class SectorLinkedImpactNode(Node):
    type = "data.sector_linked_impact"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "업종 연관 영향 지표"
    description = (
        "그 업종을 실제로 움직이는 뉴스(섹터 영향 플래그가 켜진 뉴스)만 모아 평균 충격량을 "
        "-1~+1로 정규화한 지표. 섹터 모멘텀과 달리 무관한 뉴스로 값이 희석되지 않는다."
    )
    example = "예: 섹터=반도체 + '업종 우호적 (≥ 0.3)' → 반도체 업종 뉴스가 긍정적일 때만 통과"
    condition_field = "sector_linked_impact"
    condition_presets = [
        Preset("very_strong", "매우 강한 업종 호재 (≥ 0.7)", "이상", 0.7),
        Preset("strong", "강한 업종 호재 (≥ 0.5)", "이상", 0.5),
        Preset("moderate", "업종 우호적 (≥ 0.3)", "이상", 0.3),
        Preset("negative", "업종 악재 (≤ -0.3)", "이하", -0.3),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        _SECTOR_REQUIRED,
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 7,
         "required": False, "group": "calc", "hint": "주간=7"},
        *condition_params(condition_presets, "moderate"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        sector = str(self.get_param("sector", "")).strip()
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "sector_linked_impact",
               sector_linked_impact(signals, sector, out.timestamp, window_days=window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class MacroSentimentNode(Node):
    type = "data.macro_sentiment"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "거시 심리 지수(Risk-on/off)"
    description = "뉴스 1건당 평균 국내/해외 영향 점수. 양수=우호적, 음수=위험회피. 매크로 필터로 사용."
    example = "예: '국내 우호적 (≥ 0)' 선택 시, 국내 매크로 심리가 우호적일 때만 매수 진행"
    condition_field = "domestic_macro_index"
    condition_presets = [
        Preset("dom_ok", "국내 우호적 (≥ 0)", "이상", 0.0, field="domestic_macro_index"),
        Preset("dom_risk", "국내 위험회피 (< 0)", "미만", 0.0, field="domestic_macro_index"),
        Preset("ovs_risk", "해외 위험회피 (< 0)", "미만", 0.0, field="overseas_macro_index"),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 5,
         "required": False, "group": "calc", "hint": "단기=5"},
        *condition_params(condition_presets, "dom_ok"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        window = int(self.get_param("window_days", 5))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "domestic_macro_index", macro_sentiment_index(signals, out.timestamp, "domestic", window))
        _stamp(out, "overseas_macro_index", macro_sentiment_index(signals, out.timestamp, "overseas", window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class MomentumChangeNode(Node):
    type = "data.sector_momentum_change"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "섹터 모멘텀 가속도"
    description = "최근 구간 모멘텀 − 직전 구간 모멘텀. 양수=가열(추세 강화), 음수=냉각으로 추세 방향을 판단."
    example = "예: '가열 중 (> 0)' 선택 시, 섹터가 달아오르는 국면일 때만 매수"
    condition_field = "sector_momentum_change"
    condition_presets = [
        Preset("heating", "가열 중 (> 0)", "초과", 0.0),
        Preset("strong_heat", "강한 가열 (≥ 0.3)", "이상", 0.3),
        Preset("cooling", "냉각 중 (< 0)", "미만", 0.0),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        _SECTOR_REQUIRED,
        {"key": "window_days", "type": "number", "label": "구간 길이(일)", "default": 7,
         "required": False, "group": "calc", "hint": "각 구간 7일"},
        *condition_params(condition_presets, "heating"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        sector = str(self.get_param("sector", "")).strip()
        window = int(self.get_param("window_days", 7))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window * 2))
        _stamp(out, "sector_momentum_change", momentum_change(signals, sector, out.timestamp, window_days=window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class SectorBuzzNode(Node):
    type = "data.sector_buzz"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "뉴스 버즈 Z-Score"
    description = "방향 무관, 뉴스량이 평소 대비 급증했는지(관심 급증=변동성 전조)를 판단. 섹터 비우면 시장 전체."
    example = "예: '관심 급증 (Z ≥ 2.0)' 선택 시, 뉴스량이 평소 대비 크게 튈 때만 통과"
    condition_field = "buzz_zscore"
    condition_presets = [
        Preset("surge", "관심 급증 (Z ≥ 2.0)", "이상", 2.0),
        Preset("rising", "관심 증가 (≥ 1.0)", "이상", 1.0),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        _SECTOR_OPTIONAL,
        {"key": "lookback_days", "type": "number", "label": "기준 기간(일)", "default": 20,
         "required": False, "group": "calc", "hint": "일평균·표준편차 산정 기간"},
        *condition_params(condition_presets, "surge"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        sector = str(self.get_param("sector", "")).strip() or None
        lookback = int(self.get_param("lookback_days", 20))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=lookback + 1))
        _stamp(out, "buzz_zscore", buzz_zscore(signals, out.timestamp, sector, lookback_days=lookback))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out


@register_node
class EventDensityNode(Node):
    type = "data.event_density"
    category = "data"
    subcategory = "뉴스신호"
    display_name = "이벤트 밀도(국면)"
    description = "특정 성격 이벤트가 뉴스 흐름을 얼마나 지배하는지(%). M&A 붐/실적 시즌/정책 국면 탐지."
    example = "예: 이벤트=M&A_Investment + '이벤트 우세 (≥ 30%)' → M&A 붐 국면일 때만 통과"
    condition_field = "event_density"
    condition_presets = [
        Preset("dominant", "이벤트 우세 (≥ 30%)", "이상", 30.0),
        Preset("strong", "강한 우세 (≥ 50%)", "이상", 50.0),
        PASS_PRESET,
    ]
    param_schema: list[NodeParam] = [
        {"key": "event_type", "type": "select", "label": "이벤트 성격", "required": True,
         "options": list(EVENT_TYPES), "group": "calc", "hint": "탐지할 이벤트 Enum"},
        {"key": "window_days", "type": "number", "label": "기간(일)", "default": 3,
         "required": False, "group": "calc", "hint": "단기=3"},
        *condition_params(condition_presets, "dominant"),
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        repo = _repo(providers)
        event_type = str(self.get_param("event_type", "")).strip()
        window = int(self.get_param("window_days", 3))
        out = context.clone()
        signals = repo.list_since(out.timestamp - timedelta(days=window))
        _stamp(out, "event_density", event_density(signals, out.timestamp, (event_type,), window))
        apply_condition(self, out, self.condition_presets, self.condition_field)
        return out
