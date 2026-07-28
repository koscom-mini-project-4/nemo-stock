"""자유 프롬프트 AI 판단 노드(§0-9).

사용자가 프롬프트/참고자료를 자유롭게 작성하는 통과/탈락 판단 노드. 앞 노드가 symbols[code]에
채운 값을 {{키}}로 프롬프트에 자동 치환하거나(치환 모드), AI가 스스로 뉴스/가격 조회 도구를
호출해 데이터를 가져오게 할 수 있다(도구 호출 모드) — 어느 쪽을 쓸지는 params.data_mode로
노드마다 고른다(워크플로 작성자 선택 사항).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.ai.base import AIClient, AIUnavailableError
from app.market_data.base import MarketDataProvider
from app.market_data.symbol_master import get_symbol_name
from app.nodes.base import Node, NodeContext, NodeParam, register_node
from app.vendor.news_classifier import NewsTrader

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_RESERVED = {"symbol", "date"}

DATA_MODE_SUBSTITUTE = "치환"
DATA_MODE_TOOLS = "AI 직접 조회(도구 호출)"

_RESPONSE_SCHEMA_NOTE = (
    '반드시 다음 JSON 형식으로만 답하세요: {"pass": true 또는 false, '
    '"opinion": "매수" 또는 "매도" 또는 "중립", "confidence": 0~1 사이 숫자, '
    '"reason": "판단 근거 한두 문장"}'
)


def _extract_placeholders(*texts: str) -> set[str]:
    keys: set[str] = set()
    for text in texts:
        keys.update(_PLACEHOLDER_RE.findall(text or ""))
    return keys


def _substitute(text: str, values: dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)

    return _PLACEHOLDER_RE.sub(repl, text or "")


def _tools_spec() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_symbol_news_signal",
                "description": "종목코드 기준 최근 뉴스 영향 지표(판정 t/n/f, 평균 점수, 클러스터 수)를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string", "description": "종목코드(예: 005930)"}},
                    "required": ["symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sector_news_signal",
                "description": "섹터명 기준 최근 뉴스 영향 지표를 조회한다(예: '반도체 및 반도체 장비').",
                "parameters": {
                    "type": "object",
                    "properties": {"sector": {"type": "string"}},
                    "required": ["sector"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_macro_news_signal",
                "description": "거시경제 지표명 기준 최근 뉴스 영향 지표를 조회한다(예: '증권', '금리').",
                "parameters": {
                    "type": "object",
                    "properties": {"macro": {"type": "string"}},
                    "required": ["macro"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_price",
                "description": "종목의 현재가/전일종가/거래량/등락률을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
            },
        },
    ]


@register_node
class FreePromptNode(Node):
    type = "ai.free_prompt"
    category = "ai"
    subcategory = "자유 판단"
    display_name = "자유 프롬프트 판단 (AI)"
    description = (
        "사용자가 직접 작성한 프롬프트/참고자료로 AI가 종목별 통과 여부를 판단하는 범용 필터 "
        "노드. params.prompt에서 {{키}}로 symbols[code]의 값을 자동 치환할 수 있다(예: "
        "{{news_verdict}}, {{sector_momentum}}; 예약 토큰 {{symbol}}/{{date}}). "
        "params.data_mode='치환'이면 참조하는 키가 하나라도 비어 있는 종목은 AI를 호출하지 "
        "않고 즉시 탈락 처리한다(누락 키를 사유에 기록 — 정형검증). data_mode='AI 직접 "
        "조회(도구 호출)'이면 누락된 값은 AI가 뉴스/가격 조회 도구를 스스로 호출해 채울 수 "
        "있다. 출력: symbols[code]에 {node_id}_pass(bool)/{node_id}_opinion(매수·매도·중립)/"
        "{node_id}_confidence(0~1)/{node_id}_reason(문자열)을 채우고, pass=False인 종목은 "
        "탈락시킨다(logic.if_else 내장). 판단 근거는 meta.decisions에도 기록된다."
    )
    example = "프롬프트에 '{{news_verdict}}가 t이고 {{sector_momentum}}이 0.3 이상이면 매수'처럼 자유롭게 작성"
    param_schema: list[NodeParam] = [
        {
            "key": "prompt",
            "type": "prompt",
            "label": "판단 프롬프트",
            "default": "",
            "required": True,
            "hint": "자유롭게 작성하세요. {{키}}로 앞 노드가 채운 값을 자동 치환합니다(예: {{news_verdict}}).",
        },
        {
            "key": "reference",
            "type": "prompt",
            "label": "참고 자료(선택)",
            "default": "",
            "required": False,
            "hint": "판단 기준으로 삼을 참고 자료(투자 원칙, 리스크 정책 등)를 자유롭게 입력",
        },
        {
            "key": "data_mode",
            "type": "select",
            "label": "데이터 조회 방식",
            "default": DATA_MODE_SUBSTITUTE,
            "required": True,
            "options": [DATA_MODE_SUBSTITUTE, DATA_MODE_TOOLS],
            "group": "calc",
            "hint": "치환: {{키}}를 앞 노드 값으로 미리 바꿔 1회 호출(빠름/저렴, 누락 키는 즉시 탈락). "
            "직접 조회: AI가 필요하면 뉴스/가격 조회 도구를 스스로 호출(유연하지만 느리고 "
            "비용이 더 들 수 있음).",
        },
    ]

    def validate_params(self) -> list[str]:
        errors = super().validate_params()
        prompt = str(self.get_param("prompt", ""))
        reference = str(self.get_param("reference", ""))
        for label, text in (("prompt", prompt), ("reference", reference)):
            if text.count("{{") != text.count("}}"):
                errors.append(
                    f"'{label}' 파라미터의 {{{{ }}}} 플레이스홀더 괄호 짝이 맞지 않습니다 ({self.display_name})."
                )
        return errors

    def execute(self, context: NodeContext, **providers: Any) -> NodeContext:
        ai_client = providers.get("ai_client")
        if not isinstance(ai_client, AIClient):
            raise RuntimeError("ai.free_prompt 노드 실행에는 ai_client provider가 필요합니다.")

        prompt = str(self.get_param("prompt", ""))
        reference = str(self.get_param("reference", ""))
        data_mode = str(self.get_param("data_mode", DATA_MODE_SUBSTITUTE))
        placeholders = _extract_placeholders(prompt, reference) - _RESERVED

        out = context.clone()
        passed: dict[str, dict] = {}
        failed: list[str] = []
        decisions: dict[str, dict] = {}
        p_key, o_key, c_key, r_key = (
            f"{self.node_id}_pass",
            f"{self.node_id}_opinion",
            f"{self.node_id}_confidence",
            f"{self.node_id}_reason",
        )

        for symbol, data in out.symbols.items():
            missing = sorted(k for k in placeholders if k not in data)

            if missing and data_mode == DATA_MODE_SUBSTITUTE:
                reason = f"누락된 키: {', '.join(missing)} — 앞 노드에서 이 값을 채우는지 확인하세요."
                data[p_key], data[o_key], data[c_key], data[r_key] = False, None, None, reason
                decisions[symbol] = {"pass": False, "reason": reason, "metrics": {"missing_keys": missing}}
                failed.append(symbol)
                continue

            values = {**data, "symbol": symbol, "date": out.timestamp.date().isoformat()}
            resolved_prompt = _substitute(prompt, values)
            resolved_reference = _substitute(reference, values)
            if missing:  # 도구 모드: 누락 키는 안내만 남기고 AI 호출은 계속 진행(도구로 채울 수 있음)
                resolved_prompt += (
                    f"\n\n(참고: {', '.join(missing)} 값이 앞 노드에 없습니다. "
                    "필요하면 도구를 호출해 직접 조회하세요.)"
                )

            system_prompt = (
                "당신은 주식 투자 전략의 종목 통과/탈락을 판단하는 어시스턴트입니다. "
                "사용자가 제시한 판단 프롬프트와 참고 자료, 데이터를 바탕으로 이 종목을 지금 "
                "통과시킬지 결정하세요.\n\n" + _RESPONSE_SCHEMA_NOTE
            )
            user_prompt = (
                f"종목코드: {symbol}\n\n판단 프롬프트:\n{resolved_prompt}\n\n"
                f"참고 자료:\n{resolved_reference or '(없음)'}\n\n"
                f"이 종목에 대해 앞 노드가 채운 데이터: {data}"
            )

            try:
                if data_mode == DATA_MODE_TOOLS:
                    result = ai_client.complete_with_tools(
                        system_prompt,
                        user_prompt,
                        tools=_tools_spec(),
                        tool_executor=self._make_tool_executor(providers, symbol),
                        purpose="free_prompt",
                    )
                else:
                    result = ai_client.complete_json(system_prompt, user_prompt, purpose="free_prompt")
            except AIUnavailableError as exc:
                reason = f"AI 미설정: {exc}"
                data[p_key], data[o_key], data[c_key], data[r_key] = False, None, None, reason
                decisions[symbol] = {"pass": False, "reason": reason}
                failed.append(symbol)
                continue
            except Exception as exc:  # noqa: BLE001 - AI 오류는 해당 종목만 탈락 처리
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                reason = f"AI 호출 오류: {exc}"
                data[p_key], data[o_key], data[c_key], data[r_key] = False, None, None, reason
                decisions[symbol] = {"pass": False, "reason": reason}
                failed.append(symbol)
                continue

            ok = bool(result.get("pass", False))
            opinion = result.get("opinion")
            confidence = result.get("confidence")
            reason = str(result.get("reason", "") or "")
            data[p_key], data[o_key], data[c_key], data[r_key] = ok, opinion, confidence, reason
            decisions[symbol] = {
                "pass": ok,
                "reason": reason or ("통과" if ok else "탈락"),
                "metrics": {
                    "opinion": opinion,
                    "confidence": confidence,
                    "data_mode": data_mode,
                    "missing_keys": missing,
                },
            }
            if ok:
                passed[symbol] = data
            else:
                failed.append(symbol)

        out.symbols = passed
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        out.meta.setdefault("decisions", {})[self.node_id] = decisions
        return out

    def _make_tool_executor(self, providers: dict[str, Any], symbol: str) -> Callable[[str, dict], Any]:
        def executor(name: str, args: dict) -> Any:
            try:
                if name == "get_symbol_news_signal":
                    return self._news_lookup(providers, "stock", str(args.get("symbol") or symbol))
                if name == "get_sector_news_signal":
                    return self._news_lookup(providers, "sector", str(args.get("sector", "")))
                if name == "get_macro_news_signal":
                    return self._news_lookup(providers, "macro", str(args.get("macro", "")))
                if name == "get_price":
                    return self._price_lookup(providers, str(args.get("symbol") or symbol))
                return {"error": f"알 수 없는 도구: {name}"}
            except Exception as exc:  # noqa: BLE001 - 도구 실행 실패는 AI에게 알려 계속 진행시킨다
                return {"error": str(exc)}

        return executor

    def _news_lookup(self, providers: dict[str, Any], axis: str, key: str) -> dict:
        factory = providers.get("news_trader_factory")
        if not callable(factory) or not key:
            return {"error": "조회 불가(키 없음 또는 provider 없음)"}
        if axis == "stock":
            key = get_symbol_name(key) or key
        trader: NewsTrader = factory(auto_update=False)
        try:
            result = getattr(trader, axis)(key)
        finally:
            trader.close()
        return {"판정": result.get("판정"), "평균": result.get("평균"), "클러스터수": result.get("클러스터수")}

    def _price_lookup(self, providers: dict[str, Any], symbol: str) -> dict:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider) or not symbol:
            return {"error": "조회 불가(종목코드 없음 또는 provider 없음)"}
        tick = market_data.get_price(symbol)
        return {
            "price": tick.price,
            "prev_close": tick.prev_close,
            "volume": tick.volume,
            "change_pct": round(tick.change_pct, 3),
        }
