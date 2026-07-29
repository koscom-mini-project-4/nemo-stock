"""뉴스 기반 종목/섹터/거시경제 신호 노드.

app/vendor/news_classifier(koscom-mini-project-4/newsstock-lib를 vendor)의 NewsTrader를
감싼다. NewsTrader는 조회 시점에 스스로 "크롤링(네이버 경제뉴스) → AI 분류 → 클러스터 반영"을
수행한 뒤(마지막 갱신 후 30분 이내면 건너뜀) A/B/C(종목/섹터/거시) 영향 지표를 계산해
t(호재)/n(중립)/f(악재) 판정을 돌려준다. 우리 NewsRepository/ai.sentiment_score와는 완전히
별개의 독립 파이프라인(자체 SQLite DB, app/config.py의 newsstock_db_path)이다.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from app.market_data.symbol_master import get_symbol_name
from app.nodes.base import Node, NodeContext, NodeParam, register_node
from app.vendor.news_classifier import NewsTrader
from app.workflow.graph import NodeDef

AXIS_METHOD = {"종목": "stock", "섹터": "sector", "거시경제": "macro"}


def resolve_news_signal_clusters(
    node: NodeDef, symbol: str, start_date: date, end_date: date, news_trader_factory: Callable[..., NewsTrader]
) -> list[dict]:
    """ai.news_signal 노드 파라미터로 축/키를 결정해 [start_date, end_date] 구간을 커버하는
    뉴스 클러스터 원본 리스트(대표제목/최초발생날짜/클러스터id/count/strength 등)를 반환한다.

    `app/api/routers/backtest.py`(차트 뉴스 마커)와 `app/api/routers/ai.py`(AI 설명 근거
    selection)가 공유한다 — 둘 다 "이 워크플로가 실제로 어떤 뉴스를 참고했는가"를 같은 방식
    으로 계산해야 하므로 분기하지 않는다. node가 ai.news_signal이 아니거나 키를 결정할 수
    없으면 빈 리스트.
    """
    if node.type != "ai.news_signal":
        return []

    axis = str(node.params.get("axis", "종목"))
    key = str(node.params.get("key", "") or "")
    if axis == "종목" and not key:
        key = get_symbol_name(symbol) or ""
    if not key:
        return []

    period_days = int(node.params.get("period_days", 7) or 7)
    threshold = float(node.params.get("threshold", 0.1) or 0.1)
    decay_base = float(node.params.get("decay_base", 0.3) or 0.3)
    include_zero = bool(node.params.get("include_zero", True))
    decay_from = str(node.params.get("decay_from", "end") or "end")
    method_name = AXIS_METHOD.get(axis, "stock")

    # 노드는 매 거래일 start=그날, period=period_days(그날부터 앞으로 period_days)로 조회한다.
    # [start_date, end_date] 전체를 한 번에 커버하려면 start=start_date, period=
    # (구간 길이 + 노드의 조회기간)으로 넓혀서 조회하면 각 거래일이 봤을 구간의 합집합을
    # 충분히 덮는다(경계 며칠 정도 더 넓게 잡히는 건 무해하다).
    span_days = (end_date - start_date).days + period_days

    trader = news_trader_factory(
        auto_update=False, threshold=threshold, decay_base=decay_base,
        include_zero=include_zero, decay_from=decay_from,
    )
    try:
        result = getattr(trader, method_name)(key, start=start_date.isoformat(), period=span_days)
    finally:
        trader.close()

    return result.get("클러스터", []) or []


def _passes(pass_when: str, verdict: str) -> bool:
    if pass_when == "호재(t)":
        return verdict == "t"
    if pass_when == "악재(f)":
        return verdict == "f"
    return verdict != "n"  # "중립 아님"


def _top_cluster(result: dict) -> dict | None:
    """판정에 가장 큰 영향을 준 클러스터(|점수|가 최대인 것)를 찾는다.

    trader.stock/sector/macro()가 돌려주는 result["클러스터"]는 각 클러스터의 대표제목·점수를
    담고 있다(README 예시 참조) — 평균을 이루는 개별 근거를 그대로 재사용할 뿐 추가 조회는
    필요 없다.
    """
    clusters = result.get("클러스터") or []
    if not clusters:
        return None
    return max(clusters, key=lambda c: abs(c.get("점수", 0.0) or 0.0))


@register_node
class NewsSignalNode(Node):
    type = "ai.news_signal"
    category = "ai"
    subcategory = "뉴스"
    display_name = "뉴스 신호(종목/섹터/거시)"
    description = (
        "뉴스 기반으로 종목/섹터/거시경제 중 하나(params.axis)의 실행 시점(context.timestamp, "
        "백테스트에서는 그날 날짜) 기준 최근 params.period_days일 영향 지표를 계산해 "
        "symbols[code]에 news_verdict('t'=호재/'n'=중립/'f'=악재), "
        "news_score(평균 점수), news_cluster_count(근거 클러스터 수), "
        "news_true(bool, verdict=='t'), news_top_topic(이 판정에 |점수|가 가장 큰 영향을 준 "
        "뉴스 클러스터의 대표제목)/news_top_topic_score(그 클러스터의 기여 점수)를 채운다 — "
        "어떤 주제가 판정을 좌우했는지 확인할 수 있다. axis='종목'이고 params.key가 비어 있으면 "
        "종목코드를 app/market_data/symbol_master.py로 한글 종목명 자동 변환해 조회한다(매핑이 "
        "없는 코드는 판정 불가로 탈락). axis='섹터'/'거시경제'는 params.key에 이름을 직접 "
        "지정해야 한다(예: '반도체 및 반도체 장비', '증권'). params.pass_when 기준으로 조건을 "
        "만족하는 종목만 통과시키는 필터형 노드다(logic.if_else 내장). params.auto_update=true"
        "(기본)면 조회 시 자동으로 크롤링+AI 분류를 트리거한다(라이브러리 자체가 마지막 갱신 "
        "후 30분 이내면 건너뛰어 비용을 제한함); false면 이미 적재된 데이터만 읽고 네트워크/AI "
        "호출을 하지 않는다 — 이 경우 크롤링은 POST /data/news/update로 별도 트리거해야 한다. "
        "params.threshold/decay_base/include_zero/decay_from은 NewsTrader의 지표 계산식을 "
        "그대로 조절한다(각 기본값은 라이브러리 기본값과 동일). 통과/탈락 근거는 meta.decisions에 "
        "기록된다."
    )
    example = "삼성전자 관련 뉴스가 최근 7일간 호재(t)로 판정될 때"
    param_schema: list[NodeParam] = [
        {
            "key": "axis",
            "type": "select",
            "label": "축",
            "default": "종목",
            "required": True,
            "options": ["종목", "섹터", "거시경제"],
            "group": "calc",
        },
        {
            "key": "key",
            "type": "string",
            "label": "이름(섹터/거시경제용)",
            "default": "",
            "required": False,
            "group": "calc",
            "hint": "섹터/거시경제일 때 이름 지정(예: '반도체 및 반도체 장비', '증권'). 종목 축은 "
            "비워두면 종목코드→한글명 자동 매핑을 사용",
        },
        {"key": "period_days", "type": "number", "label": "조회 기간(일)", "default": 7, "required": True, "group": "calc"},
        {
            "key": "auto_update",
            "type": "boolean",
            "label": "자동 갱신(크롤링+AI 분류)",
            "default": True,
            "required": False,
            "group": "calc",
            "hint": "끄면 이미 적재된 데이터만 조회한다. 크롤링은 POST /data/news/update로 별도 트리거 가능",
        },
        {
            "key": "pass_when",
            "type": "select",
            "label": "통과 조건",
            "default": "호재(t)",
            "required": True,
            "options": ["호재(t)", "악재(f)", "중립 아님"],
            "group": "condition",
        },
        {
            "key": "threshold",
            "type": "number",
            "label": "t/f 판정 경계",
            "default": 0.1,
            "required": False,
            "group": "calc",
            "hint": "평균 점수가 이 값 이상이면 t(호재), -이 값 이하면 f(악재)",
        },
        {
            "key": "decay_base",
            "type": "number",
            "label": "최신성 감쇠 계수",
            "default": 0.3,
            "required": False,
            "group": "calc",
            "hint": "클수록 오래된 클러스터의 영향을 더 깎는다",
        },
        {
            "key": "include_zero",
            "type": "boolean",
            "label": "중립(strength=0) 클러스터 포함",
            "default": True,
            "required": False,
            "group": "calc",
            "hint": "끄면 강도 0인 클러스터를 평균 분모에서 제외",
        },
        {
            "key": "decay_from",
            "type": "select",
            "label": "최신성 기준일",
            "default": "end",
            "required": False,
            "options": ["end", "start", "now"],
            "option_labels": ["조회 구간 끝", "조회 구간 시작", "현재 시각"],
            "group": "calc",
            "hint": "감쇠(d)를 조회 구간의 끝/시작/현재 중 어디부터 셀지",
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        factory = providers.get("news_trader_factory")
        if not callable(factory):
            raise RuntimeError("ai.news_signal 노드 실행에는 news_trader_factory provider가 필요합니다.")
        factory_fn: Callable[..., NewsTrader] = factory  # type: ignore[assignment]

        axis = str(self.get_param("axis", "종목"))
        key_param = str(self.get_param("key", "") or "")
        period_days = int(self.get_param("period_days", 7))
        auto_update = bool(self.get_param("auto_update", True))
        pass_when = str(self.get_param("pass_when", "호재(t)"))
        threshold = float(self.get_param("threshold", 0.1))
        decay_base = float(self.get_param("decay_base", 0.3))
        include_zero = bool(self.get_param("include_zero", True))
        decay_from = str(self.get_param("decay_from", "end"))
        method_name = AXIS_METHOD.get(axis, "stock")
        # context.timestamp 기준으로 조회해야 백테스트(과거 날짜로 리플레이)에서 그날 시점의
        # 뉴스 창을 본다. start를 안 주면 라이브러리가 항상 "실제 오늘"을 기준으로 계산해
        # 백테스트의 각 거래일이 전부 동일한(가장 최근) 결과를 받는 문제가 생긴다.
        start_date = context.timestamp.date().isoformat()

        out = context.clone()
        passed: dict[str, dict] = {}
        failed: list[str] = []
        decisions: dict[str, dict] = {}

        trader = factory_fn(
            auto_update=auto_update,
            threshold=threshold,
            decay_base=decay_base,
            include_zero=include_zero,
            decay_from=decay_from,
        )
        try:
            for symbol, data in out.symbols.items():
                key = key_param
                if axis == "종목" and not key:
                    key = get_symbol_name(symbol) or ""
                if not key:
                    decisions[symbol] = {"pass": False, "reason": "종목명 매핑 없음(자동 매핑 실패) → 판정 불가"}
                    failed.append(symbol)
                    continue

                try:
                    result = getattr(trader, method_name)(key, start=start_date, period=period_days)
                except Exception as exc:  # noqa: BLE001 - 조회 실패는 해당 종목 탈락으로 처리
                    out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                    decisions[symbol] = {"pass": False, "reason": f"조회 오류: {exc}"}
                    failed.append(symbol)
                    continue

                verdict = str(result.get("판정", "n"))
                score = float(result.get("평균", 0.0) or 0.0)
                cluster_count = int(result.get("클러스터수", 0) or 0)
                top = _top_cluster(result)
                top_topic = str(top["대표제목"]) if top else None
                top_topic_score = round(float(top["점수"]), 4) if top else None

                data["news_verdict"] = verdict
                data["news_score"] = round(score, 4)
                data["news_cluster_count"] = cluster_count
                data["news_true"] = verdict == "t"
                data["news_top_topic"] = top_topic
                data["news_top_topic_score"] = top_topic_score

                ok = _passes(pass_when, verdict)
                topic_note = f" | 주요 근거: '{top_topic}' (기여점수 {top_topic_score:+.4f})" if top else " | 근거 뉴스 없음"
                decisions[symbol] = {
                    "pass": ok,
                    "reason": (
                        f"[{axis}:{key}] 판정={verdict} 점수={round(score, 4)}"
                        f"(클러스터 {cluster_count}건) → {'통과' if ok else '탈락'}{topic_note}"
                    ),
                    "metrics": {
                        "verdict": verdict,
                        "score": score,
                        "cluster_count": cluster_count,
                        "top_topic": top_topic,
                        "top_topic_score": top_topic_score,
                    },
                }
                if ok:
                    passed[symbol] = data
                else:
                    failed.append(symbol)
        finally:
            trader.close()

        out.symbols = passed
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        out.meta.setdefault("decisions", {})[self.node_id] = decisions
        return out
