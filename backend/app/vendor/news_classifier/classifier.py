"""OpenAI 호출 + 프롬프트.

vendored from koscom-mini-project-4/newsstock-lib. nemo-stock 통합 시 call_ai()의
temperature 처리만 수정했다(아래 주석 참조) — 그 외 로직은 원본 그대로다.
"""
import json

from openai import BadRequestError, OpenAI

from .config import (OPENAI_API_KEY, OPENAI_MODEL, CONTENT_MAX_CHARS,
                     SECTORS, MACROS, STRENGTHS)

_clients = {}   # api_key -> OpenAI 클라이언트. 키마다 따로 캐시한다.

# 목록이 길어져서 프롬프트에는 한 줄에 하나씩 넣는다.
_SECTOR_LIST = "\n".join(f"  - {s}" for s in SECTORS)
_MACRO_LIST = " / ".join(MACROS)


def _client_once(api_key: str = None) -> OpenAI:
    """키별로 클라이언트를 캐시한다. 키를 안 주면 .env 값을 쓴다."""
    key = api_key or OPENAI_API_KEY
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY 가 없습니다. .env 에 넣거나 "
            "NewsTrader(api_key=...) 로 넘기세요.")
    if key not in _clients:
        _clients[key] = OpenAI(api_key=key)
    return _clients[key]


SYSTEM_PROMPT = f"""너는 한국 주식시장 뉴스 분석가다. 뉴스 하나를 읽고 아래 규칙대로 분류해서 JSON만 출력한다.

[1] items — 뉴스가 영향을 주는 대상들
- 뉴스가 여러 종목/섹터/거시지표에 영향을 주면 items 배열에 항목을 여러 개 만든다.
- 각 항목은 {{"stock", "sector", "macro"}} 한 세트다.
- stock: 이 뉴스가 영향을 주는 구체적인 주식 종목명. 없거나 불확실하면 null.
- sector: 반드시 아래 {len(SECTORS)}개(GICS 산업그룹) 중 하나만. 해당 없으면 null.
{_SECTOR_LIST}
- macro: 반드시 이 {len(MACROS)}개 중 하나만. {_MACRO_LIST}. 해당 없으면 null.
- 목록에 없는 값은 절대 지어내지 말고 null 을 써라. 문자열을 그대로 복사해서 써라.
- 섹터는 큰 분류가 아니라 세부 산업그룹이다. 반도체 기업은 "반도체 및 반도체 장비",
  스마트폰·PC 제조는 "기술 하드웨어 및 장비", IT 서비스·플랫폼·게임은 "소프트웨어 및 서비스"처럼
  가장 좁게 들어맞는 하나를 고른다.
- 영향 대상이 전혀 없으면 items 는 [{{"stock": null, "sector": null, "macro": null}}] 하나만 둔다.
- 반대로 의미 있는 항목이 하나라도 있으면, 셋 다 null 인 항목은 넣지 마라.

[2] strength — 이 뉴스로 주가가 얼마나 움직일 것인가
- 반드시 이 7개 값 중 하나만 사용한다: {STRENGTHS}. 중간값(0.4, 0.8, -0.5 등)은 절대 쓰지 마라.
- 판단 기준은 "이 뉴스 때문에 주가가 실제로 움직이는가"다.
  기사의 논조나 홍보 문구가 긍정적인지가 아니다.

  +1.0  업종 판도를 바꾸는 초대형 호재. 주가 급등(+5% 이상) 수준.
        예) 분기 실적이 컨센서스를 크게 상회 / 대형 M&A 피인수 / 신약 임상 3상 성공
            연 매출에 맞먹는 초대형 수주 / 경쟁사 퇴출로 인한 반사이익
  +0.6  실적에 실제로 잡히는 뚜렷한 호재. (+2~5%)
        예) 매출에서 유의미한 비중을 차지하는 계약·수주(금액이 공시됨)
            주력 제품 가격 인상 / 대규모 자사주 매입·배당 확대 / 규제 완화 확정
  +0.3  방향은 호재지만 실적 기여가 작거나 불확실. (0~+2%)
        예) 주력 라인의 신제품 실제 출시 / 소규모 계약 / 증권사 목표주가 상향
            해당 기업이 속한 업황의 개선 전망
   0.0  주가와 무관하거나 이미 주가에 반영된 내용.
        ★ 기업 보도자료의 대부분이 여기에 해당한다.
        예) 단순 홍보·마케팅·행사·전시회 참가 / MOU·업무협약·"협력 추진"
            수상·인증 / 채용·교육·아카데미·사회공헌·캠페인 / 인사이동
            제품 "공개"·디자인 발표(출시·판매 아님) / 금액이 명시되지 않은 사업 착수
            상장사가 아닌 기관·지자체·협회 소식 / 특정 기업과 무관한 일반 해설 기사
            연예인·개인 신변 등 기업 실적과 무관한 소식
  -0.3  방향은 악재지만 영향이 제한적. (0~-2%)
        예) 소규모 소송 제기 / 증권사 목표주가 하향 / 업황 둔화 전망 / 단기 수급 악화
  -0.6  실적·펀더멘털을 훼손하는 뚜렷한 악재. (-2~5%)
        예) 주요 고객 이탈 / 실적이 컨센서스 하회 / 제품 리콜 / 규제 강화 확정
            대규모 유상증자 / 핵심 인력 대량 이탈
  -1.0  존립을 위협하는 초대형 악재. 주가 급락(-5% 이상) 수준.
        예) 지수 급락·서킷브레이커 발동 / 분식회계·상장폐지 위험 / 핵심 사업 중단
            대형 소송 패소 / 오너 구속 / 주력 시장을 잃는 수준의 경쟁 심화

- ★ 가장 흔한 실수는 기업 보도자료를 호재로 착각하는 것이다.
  "출시했다 / 선보였다 / 협약했다 / 참가했다 / 수상했다 / 나선다 / 강화한다 / 착수했다"
  류의 문장은, 구체적인 금액이나 실적 영향이 함께 제시되지 않으면 0.0 이다.
- 금액·수치·실적 언급이 전혀 없으면 절댓값 0.6 이상을 주지 마라.
- 애매하면 절댓값이 작은 쪽을 골라라. 과대평가가 과소평가보다 훨씬 나쁘다.

[3] 클러스터 — 같은 사건을 다룬 뉴스 묶음
- 입력으로 기존 클러스터 목록(id, 대표제목)이 주어진다.
- 뉴스 제목을 기존 클러스터의 대표제목과 비교해서, 같은 사건을 다루는 클러스터가 있으면
  그 클러스터의 id 를 cluster_id 에 넣는다.
- 같은 사건이 없으면 cluster_id 를 null 로 두고, representative_title 에 이 뉴스를 대표할
  간결한 제목(원문 제목을 다듬은 형태)을 넣는다.
- 단어 몇 개가 겹치는 정도로 묶지 마라. 같은 사건/이슈일 때만 묶는다.

출력은 아래 형태의 JSON 객체 하나만. 설명 문장은 쓰지 마라.
{{
  "cluster_id": 3 또는 null,
  "representative_title": "새 클러스터일 때 대표 제목, 기존 클러스터에 붙으면 null",
  "strength": -0.6,
  "items": [{{"stock": "현대차", "sector": "자동차 및 부품", "macro": "산업/재계"}}]
}}"""


def build_user_prompt(news: dict, clusters: list) -> str:
    cluster_lines = (
        "\n".join(f'- id={c["id"]} | 대표제목: {c["representative_title"]} '
                  f'| 최초발생: {c["first_seen_at"]} | strength: {c["strength"]}'
                  for c in clusters)
        if clusters else "(없음 — 무조건 새 클러스터)"
    )
    content = (news.get("content") or news.get("summary") or "")[:CONTENT_MAX_CHARS]
    return (
        f"[기존 클러스터 목록]\n{cluster_lines}\n\n"
        f"[분류할 뉴스]\n"
        f"제목: {news.get('title', '')}\n"
        f"발행일시: {news.get('published_at', '')}\n"
        f"본문: {content}"
    )


def call_ai(news: dict, clusters: list, model: str = None,
            api_key: str = None) -> dict:
    client = _client_once(api_key)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(news, clusters)},
    ]
    model = model or OPENAI_MODEL
    try:
        resp = client.chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"}, messages=messages,
        )
    except BadRequestError as exc:
        # nemo-stock 통합 수정: gpt-5 계열 reasoning 모델(gpt-5.6-luna 등)은 기본값(1) 외의
        # temperature를 거부한다(app/ai/openai_client.py와 동일한 문제/패턴). 해당 오류일 때만
        # temperature 없이 1회 재시도한다.
        body = exc.body if isinstance(exc.body, dict) else {}
        if body.get("param") != "temperature":
            raise
        resp = client.chat.completions.create(
            model=model, response_format={"type": "json_object"}, messages=messages,
        )
    return json.loads(resp.choices[0].message.content)
