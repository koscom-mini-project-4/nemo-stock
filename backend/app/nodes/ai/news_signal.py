"""뉴스 기반 종목/섹터/거시경제 신호 노드.

app/vendor/news_classifier(koscom-mini-project-4/newsstock-lib를 vendor)의 NewsTrader를
감싼다. NewsTrader는 조회 시점에 스스로 "크롤링(네이버 경제뉴스) → AI 분류 → 클러스터 반영"을
수행한 뒤(마지막 갱신 후 30분 이내면 건너뜀) A/B/C(종목/섹터/거시) 영향 지표를 계산해
t(호재)/n(중립)/f(악재) 판정을 돌려준다. 우리 NewsRepository/ai.sentiment_score와는 완전히
별개의 독립 파이프라인(자체 SQLite DB, app/config.py의 newsstock_db_path)이다.
"""

from __future__ import annotations

from typing import Callable

from app.market_data.symbol_master import get_symbol_name
from app.nodes.base import Node, NodeContext, NodeParam, register_node
from app.vendor.news_classifier import NewsTrader

_AXIS_METHOD = {"종목": "stock", "섹터": "sector", "거시경제": "macro"}


def _passes(pass_when: str, verdict: str) -> bool:
    if pass_when == "호재(t)":
        return verdict == "t"
    if pass_when == "악재(f)":
        return verdict == "f"
    return verdict != "n"  # "중립 아님"


@register_node
class NewsSignalNode(Node):
    type = "ai.news_signal"
    category = "ai"
    subcategory = "뉴스"
    display_name = "뉴스 신호(종목/섹터/거시)"
    description = (
        "뉴스 기반으로 종목/섹터/거시경제 중 하나(params.axis)의 최근 params.period_days일 "
        "영향 지표를 계산해 symbols[code]에 news_verdict('t'=호재/'n'=중립/'f'=악재), "
        "news_score(평균 점수), news_cluster_count(근거 클러스터 수), "
        "news_true(bool, verdict=='t')를 채운다. axis='종목'이고 params.key가 비어 있으면 "
        "종목코드를 app/market_data/symbol_master.py로 한글 종목명 자동 변환해 조회한다(매핑이 "
        "없는 코드는 판정 불가로 탈락). axis='섹터'/'거시경제'는 params.key에 이름을 직접 "
        "지정해야 한다(예: '반도체 및 반도체 장비', '증권'). params.pass_when 기준으로 조건을 "
        "만족하는 종목만 통과시키는 필터형 노드다(logic.if_else 내장). params.auto_update=true"
        "(기본)면 조회 시 자동으로 크롤링+AI 분류를 트리거한다(라이브러리 자체가 마지막 갱신 "
        "후 30분 이내면 건너뛰어 비용을 제한함); false면 이미 적재된 데이터만 읽고 네트워크/AI "
        "호출을 하지 않는다 — 이 경우 크롤링은 POST /data/news/update로 별도 트리거해야 한다. "
        "통과/탈락 근거는 meta.decisions에 기록된다."
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
        method_name = _AXIS_METHOD.get(axis, "stock")

        out = context.clone()
        passed: dict[str, dict] = {}
        failed: list[str] = []
        decisions: dict[str, dict] = {}

        trader = factory_fn(auto_update=auto_update)
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
                    result = getattr(trader, method_name)(key, period=period_days)
                except Exception as exc:  # noqa: BLE001 - 조회 실패는 해당 종목 탈락으로 처리
                    out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                    decisions[symbol] = {"pass": False, "reason": f"조회 오류: {exc}"}
                    failed.append(symbol)
                    continue

                verdict = str(result.get("판정", "n"))
                score = float(result.get("평균", 0.0) or 0.0)
                cluster_count = int(result.get("클러스터수", 0) or 0)
                data["news_verdict"] = verdict
                data["news_score"] = round(score, 4)
                data["news_cluster_count"] = cluster_count
                data["news_true"] = verdict == "t"

                ok = _passes(pass_when, verdict)
                decisions[symbol] = {
                    "pass": ok,
                    "reason": (
                        f"[{axis}:{key}] 판정={verdict} 점수={round(score, 4)}"
                        f"(클러스터 {cluster_count}건) → {'통과' if ok else '탈락'}"
                    ),
                    "metrics": {"verdict": verdict, "score": score, "cluster_count": cluster_count},
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
