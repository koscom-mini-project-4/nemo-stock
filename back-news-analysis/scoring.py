"""기사 단위 AI 라벨링 — 고정 스키마 10개 필드(depth1~reasoning) 추출.

대량 처리는 OpenAI Batch API(비용 50% 절감), 캐시 미스 1건은 동기 호출로 빠르게 채운다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from openai import BadRequestError, OpenAI

from config import CHAT_MODEL, DATA_DIR, OPENAI_API_KEY, PROMPT_VERSION
from schemas import NewsRecord, NewsVariables, TickerImpact

BATCH_INPUT_PATH = DATA_DIR / "scoring_batch_input.jsonl"

_DEPTH2_VALUES = ("긍정", "중립", "부정")
_SCOPE_TYPE_VALUES = ("종목직접", "업종전반", "시장전체")
_TIME_HORIZON_VALUES = ("단기", "중기", "장기")
_CONFIDENCE_VALUES = ("확실", "보통", "불확실")
_IMPACT_GRADE_MIN, _IMPACT_GRADE_MAX = 1, 9

# 등급을 AI가 스스로 기준을 세워 판단하지 않도록, 등급마다 구체적 예시를 고정 앵커로 제시한다.
# (사용자 지시: "스트렝스는 등급제, 각 등급에 예시를 함께 추가해서 AI가 등급을 자체판단하지 않도록")
_IMPACT_GRADE_TABLE = """1등급 (극히 경미): 시장/종목과 거의 무관한 배경성 언급 — 예: 유명인 근황에 기업명이 스치듯 언급, 일반 통계 발표
2등급 (매우 경미): 사소한 임원 동정, 일상적 매장 오픈, 소규모 후원/이벤트
3등급 (경미): 소규모 신제품 출시, 소액 계약 체결, 애널리스트 목표주가 소폭 조정
4등급 (통상): 시장 예상에 부합하는 분기 실적 발표, 정기 주주총회, 통상적 인사 발령
5등급 (다소 중대): 시장 예상치를 벗어난 실적 서프라이즈/쇼크, 유의미한 신규 계약 체결, 신용등급 전망 변경
6등급 (중대): 매출 대비 비중이 큰 대규모 수주, 규제당국 조사 착수, 대규모 자사주 소각/배당 결정
7등급 (매우 중대): 대표이사·핵심 경영진 구속/기소, 대규모 제품 리콜, 주요 소송 패소, 신용등급 강등
8등급 (심각): 분식회계 적발, 상장폐지 위기, 대규모 유동성 위기, 정부의 산업 전반 규제 급변
9등급 (극심각/국가적 충격): 전쟁·내전 발발, 국가 부도(디폴트), 대규모 금융위기, 회사 파산·청산"""

# 종목별 등급표. impact_grade(시장 전체 관점의 사건 크기)와 별개로, "그 사건이 이 종목 하나의
# 기업가치/주가에 얼마나 영향을 주는가"를 종목마다 따로 매기게 한다. 여기에도 예시를 고정 앵커로
# 제시해 AI가 종목별 기준을 자체판단하지 않도록 한다.
# (사용자 지시: "한 종목에 미치는 영향도와 종목 전체에 미치는 영향도는 다를 것 … A,B,C에서도
#  예시를 만들어서 점수화")
_TICKER_GRADE_TABLE = """1등급 (거의 무관): 비교·배경용으로 사명만 스치듯 등장 — 예: 업종 동향 기사에서 "삼성전자 등"으로 나열, 사건 당사자가 아님
2등급 (매우 간접): 같은 업종 타사 이슈가 심리적으로만 번지는 수준 — 예: 경쟁사 소규모 리콜, 전방산업의 일반적 업황 코멘트
3등급 (간접·경미): 업황/정책 변화가 이 종목에도 걸치지만 실적 영향은 제한적 — 예: 원자재가 소폭 변동, 애널리스트 목표주가 소폭 조정
4등급 (직접·통상): 이 종목이 당사자이나 시장 예상 범위 내 — 예: 예상 부합 분기 실적, 정기 주주총회, 통상적 인사 발령
5등급 (직접·다소 중대): 실적 추정치를 바꿀 만한 사건 — 예: 이 회사의 실적 서프라이즈/쇼크, 유의미한 신규 수주, 신용등급 전망 변경
6등급 (직접·중대): 매출/이익 비중이 큰 사건 — 예: 매출 대비 큰 비중의 대규모 수주, 이 회사에 대한 규제당국 조사 착수, 대규모 자사주 소각
7등급 (직접·매우 중대): 기업가치를 크게 재평가시키는 사건 — 예: 이 회사 핵심 경영진 구속/기소, 대규모 제품 리콜, 주요 소송 패소, 신용등급 강등
8등급 (직접·심각): 존속 자체가 흔들리는 사건 — 예: 이 회사 분식회계 적발, 상장폐지 위기, 유동성 위기
9등급 (직접·극심각): 주식 가치가 사실상 소멸/반토막 수준 — 예: 이 회사 파산·청산, 주력 사업 전면 중단"""

SYSTEM_PROMPT = f"""당신은 한국 경제 뉴스를 분석해 종목/업종에 미치는 영향을 구조화하는 애널리스트입니다.
주어진 뉴스 제목/본문을 읽고 아래 고정 스키마 JSON으로만 답하세요. 다른 텍스트는 출력하지 마세요.

[1] impact_grade — 시장 전체 관점에서 이 '사건' 자체가 얼마나 큰가.
아래 9단계 기준표에서 가장 가까운 등급을 고르세요(직접 기준을 만들지 말고 표에 맞춰 판단):
{_IMPACT_GRADE_TABLE}

[2] ticker_impacts — 이 뉴스가 '개별 종목 각각'에 미치는 영향.
같은 뉴스라도 종목마다 방향과 크기가 다릅니다. 예를 들어 "A사 공장 화재로 생산 차질" 뉴스는
A사에는 부정(고등급), 반사이익을 얻는 경쟁사 B에는 긍정(중간등급), 단순 비교군으로 언급된
C에는 영향 없음일 수 있습니다. 종목마다 아래 기준표로 따로 판단하세요:
{_TICKER_GRADE_TABLE}

ticker_impacts 작성 규칙:
- 기사에 등장하거나 명백히 직접 영향을 받는 종목을 모두 나열하세요(최대 8개).
- direction/grade는 그 종목 관점에서 매깁니다. [1]의 impact_grade를 그대로 복사하지 마세요.
- 이름만 언급될 뿐 영향을 판단할 수 없으면 direction과 grade를 모두 null로 두세요(0이 아니라 null).
- 관련 종목이 전혀 없으면 빈 배열로 두세요.

{{
  "depth1": "뉴스의 상위 분류 (예: 증권, 산업, 경제, 정책, 국제, 사회 등 자유롭게)",
  "depth2": "{" / ".join(_DEPTH2_VALUES)} 중 하나 (시장 전체 관점의 방향)",
  "depth3": "세부 이벤트 유형 (예: 실적이익, 실적악화, 신제품, 소송, 규제, 인수합병, 경영진리스크, 공급계약 등 자유롭게)",
  "scope_type": "{" / ".join(_SCOPE_TYPE_VALUES)} 중 하나 (주요 영향 범위: 특정 종목 직접 / 업종 전반 / 시장 전체)",
  "ticker_impacts": [
    {{
      "ticker": "종목명 (한글 정식명 또는 흔히 쓰이는 약칭)",
      "direction": "{" / ".join(_DEPTH2_VALUES)} 중 하나, 판단 불가면 null",
      "grade": "위 [2] 종목별 기준표의 등급 번호(1~9 정수), 판단 불가면 null",
      "reason": "이 종목에 그 방향/등급을 매긴 근거 한 문장"
    }}
  ],
  "related_industries": ["관련 업종명 (예: 반도체, 조선, 이차전지 등, 없으면 빈 배열)"],
  "impact_grade": "위 [1] 9단계 기준표의 등급 번호(1~9 정수)",
  "time_horizon": "{" / ".join(_TIME_HORIZON_VALUES)} 중 하나 (예상 영향 지속 기간)",
  "confidence": "{" / ".join(_CONFIDENCE_VALUES)} 중 하나 (위 분류의 신뢰도)",
  "reasoning": "분류 근거를 한 문장으로 요약(왜 그 impact_grade를 골랐는지 포함)"
}}"""


def _user_prompt(record: NewsRecord) -> str:
    body = record.content or record.summary
    return f"제목: {record.title}\n본문: {body[:1500]}"


def _client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 (backend/.env 확인).")
    return OpenAI(api_key=OPENAI_API_KEY)


def _nearest(value: str, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


def _parse_impact_grade(value: object) -> int:
    try:
        grade = int(value)
    except (TypeError, ValueError):
        return 5  # 중간값(통상 수준)으로 폴백
    return max(_IMPACT_GRADE_MIN, min(_IMPACT_GRADE_MAX, grade))


def _parse_optional_grade(value: object) -> int | None:
    """종목별 등급. null/파싱 실패는 '판단 불가'로 보고 None을 유지한다(5로 채우지 않는다)."""
    if value is None:
        return None
    try:
        grade = int(value)
    except (TypeError, ValueError):
        return None
    return max(_IMPACT_GRADE_MIN, min(_IMPACT_GRADE_MAX, grade))


def _parse_ticker_impacts(content: dict) -> list[TickerImpact]:
    """ticker_impacts를 파싱한다.

    구 프롬프트(v3 이하)가 남긴 related_tickers(문자열 배열) 응답도 받아들이되, 그 경우
    종목별 판단이 없으므로 direction/grade는 None(판단 불가)으로 둔다.
    """
    raw = content.get("ticker_impacts")
    if raw is None:
        return [
            TickerImpact(ticker=str(name), direction=None, grade=None)
            for name in content.get("related_tickers", [])
            if str(name).strip()
        ]

    impacts: list[TickerImpact] = []
    for item in raw:
        if isinstance(item, str):  # 모델이 규칙을 어기고 문자열만 준 경우
            name, direction, grade, reason = item, None, None, ""
        elif isinstance(item, dict):
            name = str(item.get("ticker", "")).strip()
            direction_raw = item.get("direction")
            direction = (
                _nearest(str(direction_raw), _DEPTH2_VALUES, "중립") if direction_raw is not None else None
            )
            grade = _parse_optional_grade(item.get("grade"))
            reason = str(item.get("reason", ""))
        else:
            continue
        if not name:
            continue
        impacts.append(TickerImpact(ticker=name, direction=direction, grade=grade, reason=reason))
    return impacts


def _parse_result(url_hash: str, published_at: str, content: dict) -> NewsVariables:
    return NewsVariables(
        url_hash=url_hash,
        published_at=published_at,
        depth1=str(content.get("depth1", "")),
        depth2=_nearest(content.get("depth2", "중립"), _DEPTH2_VALUES, "중립"),
        depth3=str(content.get("depth3", "")),
        scope_type=_nearest(content.get("scope_type", "시장전체"), _SCOPE_TYPE_VALUES, "시장전체"),
        ticker_impacts=_parse_ticker_impacts(content),
        related_industries=list(content.get("related_industries", [])),
        impact_grade=_parse_impact_grade(content.get("impact_grade", 5)),
        time_horizon=_nearest(content.get("time_horizon", "단기"), _TIME_HORIZON_VALUES, "단기"),
        confidence=_nearest(content.get("confidence", "보통"), _CONFIDENCE_VALUES, "보통"),
        reasoning=str(content.get("reasoning", "")),
        model=CHAT_MODEL,
        prompt_version=PROMPT_VERSION,
    )


def score_one(record: NewsRecord) -> NewsVariables:
    """캐시 미스 1건에 대한 동기(실시간) 채점. gpt-5 reasoning 계열은 temperature 커스텀값을 거부하므로
    OpenAIClient(app/ai/openai_client.py)와 동일하게 방어적으로 재시도한다."""
    client = _client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(record)},
    ]
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL, temperature=0.2, response_format={"type": "json_object"}, messages=messages
        )
    except BadRequestError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        if body.get("param") != "temperature":
            raise
        resp = client.chat.completions.create(
            model=CHAT_MODEL, response_format={"type": "json_object"}, messages=messages
        )
    content = json.loads(resp.choices[0].message.content or "{}")
    return _parse_result(record.url_hash, record.published_at, content)


def submit_scoring_batch(records: list[NewsRecord]) -> str:
    client = _client()
    with open(BATCH_INPUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            line = {
                "custom_id": r.url_hash,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": CHAT_MODEL,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _user_prompt(r)},
                    ],
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    uploaded = client.files.create(file=open(BATCH_INPUT_PATH, "rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"purpose": "news-scoring"},
    )
    return batch.id


def poll_scoring_batch(
    batch_id: str, records_by_hash: dict[str, NewsRecord], timeout_sec: float = 0, interval_sec: float = 15
) -> list[NewsVariables]:
    client = _client()
    waited = 0.0
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status == "completed":
            break
        if batch.status in ("failed", "expired", "cancelled"):
            raise RuntimeError(f"scoring batch {batch_id} ended with status={batch.status}")
        if timeout_sec <= 0 or waited >= timeout_sec:
            print(f"[scoring] batch {batch_id} status={batch.status}, 아직 완료되지 않음")
            return []
        time.sleep(interval_sec)
        waited += interval_sec

    output_file = client.files.content(batch.output_file_id)
    results: list[NewsVariables] = []
    for line in output_file.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row["custom_id"]
        record = records_by_hash.get(custom_id)
        if record is None:
            continue
        body = row["response"]["body"]
        content = json.loads(body["choices"][0]["message"]["content"] or "{}")
        results.append(_parse_result(custom_id, record.published_at, content))
    return results
