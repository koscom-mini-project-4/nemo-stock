# nemo-stock (네모네모매매) PoC 설계 문서

> 이 문서는 `nemo-stock.md`(사업 기획서)와 `prompt.md`(구현 지시사항)를 바탕으로 PoC의 기술 설계를 정의한다.
> 확정 필요 사항은 사용자 확인을 거쳤으며(아래 "확정된 의사결정" 참조), 이후 구현은 이 문서를 기준으로 진행한다.

## 0. 확정된 의사결정 (2026-07-14 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| AI 자연어 전략 초안 생성 | **포함**. 자연어 입력 → AI가 노드 워크플로(JSON) 초안을 생성. 사용자가 검토/수정 후 저장. |
| 인증 범위 | **단일 계정 JWT 로그인**. 회원가입/다중 사용자 불필요. 계정은 서버 `.env`/부트스트랩으로 1개 생성. |
| Toss증권 실거래 연동 | **더미 구현 + Toss 어댑터 스켈레톤(미검증)**. `MarketDataProvider`/`OrderExecutionProvider` 인터페이스를 정의하고 더미 구현을 기본으로 사용. Toss Open API(OAuth2 Client Credentials, REST: 시세/호가/캔들/잔고/주문) 문서 구조를 반영한 어댑터 클래스는 작성하되, 실제 승인된 키가 없으므로 호출 검증은 하지 않는다. |

## 0-1. 추가 확정 사항 (2026-07-17 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| 캔버스 AI 챗봇 | **통합 채팅창**. 노드 수정 지시("손절 5%로 바꿔줘")와 진행 상황 설명 질문("지금 뭐하는거야?")을 하나의 채팅 UI(`ChatPanel.vue`, 캔버스 우측 "AI 챗봇" 탭)로 처리. 백엔드 `/ai/workflow-chat` 한 엔드포인트가 AI 응답의 `changed` 플래그로 두 경우를 구분(§7.5). |
| 수정 제안 적용 방식 | **미리보기 후 적용**. AI가 그래프 수정을 제안하면 채팅 말풍선 아래 "노드 N개·엣지 N개로 변경" 요약과 적용/취소 버튼만 표시하고, 사용자가 "적용"을 눌러야 캔버스(`flowNodes`/`flowEdges`)에 반영됨. 초안 생성 플로우(§7.2)와 동일하게 자동 저장/활성화하지 않음. |
| 진행 상황 설명 범위 | **그래프 구조 + 최근 실행 결과**. 채팅 요청 시 현재 그래프와 함께 마지막 "테스트 실행" 결과(`status`/`events`/`final_symbols`, 있는 경우)를 프롬프트에 포함. |
| 노드 추가 방식 확장 | 기존 팔레트 클릭 추가에 더해 **드래그 앤 드롭**으로도 추가 가능(`NodePalette.vue` 아이템 `draggable` + 캔버스 `dragover`/`drop`, Vue Flow `screenToFlowCoordinate`로 드롭 좌표를 노드 위치로 사용). |
| AI 전략 생성 진입 장벽 완화 | `AIGenerateView.vue`에 예시 투자 아이디어 템플릿 버튼(4개)을 추가해 클릭 시 텍스트영역에 자동 채움(제출은 사용자가 직접). |
| OpenAI 모델 | `gpt-4o-mini` → **`gpt-5.6-luna`**로 상향(2026-07 출시된 GPT-5.6 3단계 모델군 중 최저가/최속 티어, Sol/Terra보다 한 단계 아래지만 기존 대비 품질 우수). reasoning 계열 특성상 기본값(1) 외의 `temperature`를 거부하므로, `OpenAIClient.complete_json`이 `BadRequestError(param="temperature")`를 감지하면 `temperature` 파라미터 없이 1회 재시도하도록 방어 로직 추가(§7.1). |

## 0-2. 추가 확정 사항 (2026-07-22 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| 백테스트 시세 자동 수집 | `POST /backtest` 실행 시 요청된 종목에 해당 기간 데이터가 하나도 없으면 자동으로 수집·저장(`ensure_price_data`, §8-1). 일부라도 있으면 건드리지 않음(부분 공백을 정교하게 채우지 않는 의도된 단순화). `Settings.auto_ingest_prices`(기본 true, 테스트는 false)로 on/off. |
| 시간봉(장중) 데이터 | 공공데이터포털/KOSCOM CHECK-API는 모두 일봉만 제공하므로, 네이버 증권의 비공식 차트 API(`api.stock.naver.com`, 별도 인증 불필요, 실측 확인)로 일봉+시간봉(60분)을 모두 수집(§8-1). 시간봉은 서버 자체가 최근 약 8거래일치(56봉)만 제공하는 실측 한계가 있어 "가능한 범위까지 저장"하는 부가 데이터로 취급하고, 백테스트 엔진 자체는 계속 일봉 기준으로 동작. |
| 종목코드 입력 | 프론트 백테스트 폼(`BacktestResultView.vue`)에 이미 콤마 구분 자유입력 텍스트필드(`대상 종목코드`)가 있어 별도 UI 추가 없이 임의 종목코드 입력이 가능했음 — 이번 작업은 백엔드 자동 수집만 추가. |
| 뉴스 AI 분석 파이프라인 | 별도 독립 프로젝트 `back-news-analysis/`(루트)로 구현. `naver_economy_news.json`(92,229건)에서 AI로 기사 단위 고정 스키마 필드를 추출하고, 임베딩 유사도 기반 이벤트 클러스터링 + decay/count_factor로 종목별 뉴스 영향도 점수를 계산(§16). OpenAI 키는 `backend/.env`를 그대로 재사용. |
| 대량 AI 호출 비용 절감 | 뉴스 스코어링/임베딩처럼 서로 독립적인 대량 요청은 OpenAI Batch API(50% 할인)로 처리. 단, "새 뉴스마다 기존 대표뉴스 전체와 비교해 판단"하는 이벤트 클러스터링은 순차 의존성이 있어 Batch API와 근본적으로 맞지 않아, 임베딩 유사도 기반 클러스터링으로 대체(§16.2). |
| 뉴스 영향도(impact) 등급 체계 | High/Medium/Low 3단계 대신 **1~9등급**(9등급=전쟁·내전 발발 등 국가적 충격) + 등급별 예시를 시스템 프롬프트에 명시해, AI가 등급 기준을 자체적으로 임의 판단하지 않고 고정 앵커에 맞춰 분류하도록 함(§16.1). |
| 원시 AI 변수와 점수 계산식 분리 | decay/count_factor/정규화 등 "점수 계산식"은 나중에 바뀔 수 있으므로, AI가 추출한 원시 변수(`NewsVariables`)만 캐시에 저장하고 최종 점수는 조회 시점에 캐시된 원시 변수로부터 매번 계산(`aggregate.py`). 계산식이 바뀌어도 캐시된 AI 호출 결과는 재사용 가능 — 단, 원시 변수 자체의 스키마(예: impact 등급 체계)가 바뀌면 해당 필드는 재추출 필요(§16.5). |

추가로 조사를 통해 확인한 사실:
- **Toss증권 Open API**: `developers.tossinvest.com`에 실존. OAuth2 Client Credentials Grant, 계좌 API는 `X-Tossinvest-Account` 헤더 필요. 시세/호가/체결/캔들/가격제한/종목정보/환율/시장캘린더 + 계좌/자산/주문(생성·수정·취소·조회) 제공. 현재 사전신청 기반 단계적 오픈 중이라 즉시 발급이 어려움.
- **공공데이터포털 금융위원회_주식시세정보 API** (`data.go.kr`, 서비스키 필요, 무료): 종목코드+일자 기준 시가/종가/고가/저가/거래량 등 제공. **일 1회, 영업일 T+1 오후 갱신** (실시간 아님) → 백테스트용 일봉 데이터 소스로 적합. 1초/1분 단위 "실시간성"은 이 데이터로 재현 불가능하므로, 라이브/테스트 모드에서는 이 일봉을 시드로 한 더미 실시간 시세 생성기를 별도로 둔다 (§5.2).
- **OpenDART(공시)**: `opendart.fss.or.kr` API 키 발급 필요(무료). 공시 원문/공시목록 조회에 사용.

---

## 1. 목표와 PoC 범위

기획서 전체 기능 중 PoC는 다음에 집중한다.

**포함**
- 노드 기반 워크플로 정의(스케줄러 → 데이터 → 지표 → AI 해석 → 로직 → 리스크 → 실행)
- 위상 정렬 기반 워크플로 실행 엔진 + 트리거 큐 + 워커 풀
- 테스트 실행(임의 값 주입) 및 노드별 디버그 이벤트 스트리밍(프론트 블록 하이라이트)
- 과거 데이터 기반 백테스트(수익률/MDD/승률/손익비/거래횟수)
- AI 자연어 → 워크플로 초안 생성
- DART 공시 AI 점수화 + 캐싱
- 뉴스/공시 등 공공데이터를 sqlite에 적재하여 테스트/백테스트에 사용
- 단일 계정 JWT 인증
- 증권사 연동은 더미 + 인터페이스(Toss 스켈레톤)로 확장 지점만 마련

**제외 (실 서비스 단계로 이연)**
- 실계좌 실주문 연동 검증, 다중 사용자/구독과금/마켓플레이스, 실시간 웹소켓 시세(거래소/증권사 실연동), 정교한 리스크·컴플라이언스 체계, 배포/운영 인프라(쿠버네티스 등)

---

## 2. 전체 아키텍처

```
┌─────────────────────────┐        HTTP/WS        ┌──────────────────────────────────────────┐
│   Frontend (Vue 3)      │ ───────────────────── │   Backend (FastAPI, 단일 프로세스 PoC)     │
│  - 노드 캔버스(Vue Flow) │                        │                                            │
│  - 속성/검증/디버그 패널 │                        │  API 계층 (routers)                        │
│  - 백테스트 결과 차트    │                        │  Auth(JWT) / Workflow / AI / Backtest /    │
└─────────────────────────┘                        │  Data / Runs(WS)                           │
                                                    │                                            │
                                                    │  Workflow 엔진: 파싱→검증→위상정렬→실행     │
                                                    │  Trigger Queue(인터페이스) ← Scheduler      │
                                                    │  Worker Pool(ThreadPoolExecutor)           │
                                                    │  EventBus(인터페이스) → WS 브로드캐스트     │
                                                    │                                            │
                                                    │  Node 레지스트리 (ABC 기반, 플러그형)       │
                                                    │  MarketDataProvider / OrderExecutionProvider│
                                                    │   (인터페이스) — Dummy / Historical / Toss  │
                                                    │  AI 모듈 (OpenAI) — 워크플로 초안, 공시/뉴스 │
                                                    │   점수화(+캐시)                             │
                                                    │  Backtest 엔진                              │
                                                    │  DAO(Repository 인터페이스) → SQLite 구현   │
                                                    └──────────────────────────────────────────┘
                                                                     │
                                                          ┌──────────────────────┐
                                                          │ SQLite (nemo_stock.db)│
                                                          │ + 공공데이터 적재     │
                                                          └──────────────────────┘
```

설계 원칙(기획/지시사항 반영):
1. **인터페이스 우선**: Queue, EventBus, MarketDataProvider, OrderExecutionProvider, Repository는 모두 ABC로 정의하고 PoC 구현체(인메모리/SQLite/더미)를 갈아끼우는 구조. 추후 Redis/Kafka/실증권사/타 RDB로 교체 시 해당 구현체만 추가하면 된다.
2. **노드 = ABC 플러그인**: 모든 노드는 `Node` ABC를 상속. 레지스트리에 등록되며, 프론트 노드 팔레트는 백엔드 레지스트리를 조회해 동적으로 구성된다(새 노드 추가 시 프론트 수정 불필요).
3. **동일 실행 경로**: 라이브 실행/테스트 실행/백테스트가 동일한 `WorkflowEngine.execute()`를 사용하고, 데이터 소스(Provider)만 모드에 따라 교체된다. → 백테스트에서 검증한 로직이 실행 시점에도 동일하게 동작함을 보장.
4. **분리 가능한 배치 프로세스**: 스케줄러/워커는 FastAPI 프로세스 내 백그라운드 스레드로 시작하지만, `backend/app/batch/` 패키지로 격리하여 `python -m app.batch.worker`로 별도 프로세스 실행이 가능하도록 구성. 단, 현재 `InMemoryTriggerQueue`는 프로세스 경계를 넘지 못하므로 진짜 분리 실행은 Queue를 Redis 등으로 교체한 이후에 의미가 있음(문서화해 둠).

---

## 3. 노드 시스템

### 3.1 Node ABC

```python
# app/nodes/base.py
class NodeContext:
    run_id: str
    mode: Literal["live", "test", "backtest"]
    timestamp: datetime
    symbols: dict[str, dict[str, Any]]   # 종목코드 -> 누적 데이터(가격, 지표, 점수 등)
    meta: dict[str, Any]                 # 스케줄 정보, 사용자 오버라이드 값 등

class NodeParam(TypedDict):
    key: str; type: str; label: str; default: Any; required: bool  # 프론트 속성 패널 자동 생성용

class Node(ABC):
    type: ClassVar[str]          # 예: "data.price", "logic.if_else"
    category: ClassVar[str]      # scheduler|data|indicator|ai|logic|risk|execution
    display_name: ClassVar[str]
    description: ClassVar[str] = ""  # 역할 + symbols 입출력 키 설명(아래 참조)
    param_schema: ClassVar[list[NodeParam]]

    def __init__(self, node_id: str, params: dict[str, Any]): ...

    @abstractmethod
    def execute(self, context: NodeContext, inputs: list[NodeContext]) -> NodeContext:
        """inputs: 선행 노드(들)의 출력 컨텍스트. 반환값이 다음 노드로 전달된다."""

    def validate_params(self) -> list[str]:
        """오류 메시지 리스트 반환(빈 리스트=정상). 기본 구현은 param_schema 기반 필수값 체크."""
```

레지스트리:
```python
NODE_REGISTRY: dict[str, type[Node]] = {}
def register_node(cls: type[Node]) -> type[Node]:
    NODE_REGISTRY[cls.type] = cls
    return cls
```
`GET /nodes` 엔드포인트가 `NODE_REGISTRY`를 순회해 `type/category/display_name/description/param_schema`를 JSON으로 반환 → 프론트 노드 팔레트(툴팁)/속성 패널이 이를 렌더링. `description`은 각 노드가 `NodeContext.symbols`에서 무엇을 읽고 무엇을 쓰는지(입력/출력 키)까지 구체적으로 적어야 한다 — `app/ai/workflow_draft.py`/`app/ai/workflow_chat.py`가 `node_registry_schema()`를 그대로 AI 프롬프트에 주입하므로, 여기 적힌 문장이 AI가 노드 역할을 이해하는 유일한 근거다. 필수값은 아니며(빈 문자열 허용) 노드 추가 시 채워 넣는 것을 원칙으로 한다.

### 3.2 PoC 기본 제공 노드 목록

| 카테고리 | type | 설명 |
| --- | --- | --- |
| scheduler | `scheduler.interval` | 주기(초) 트리거. 무료=60s 하한, 프로=1s 하한 (params로 강제) |
| data | `data.price` | 현재가/시세 조회 (MarketDataProvider) |
| data | `data.volume` | 거래량/거래대금 조회 |
| data | `data.news` | 종목 관련 최근 뉴스 조회(sqlite 적재분) |
| data | `data.disclosure` | 종목 관련 최근 공시 조회(OpenDART 적재분) |
| indicator | `indicator.moving_average` | 이동평균 계산 |
| indicator | `indicator.rsi` | RSI 계산 |
| indicator | `indicator.volatility` | 변동성(표준편차) 계산 |
| indicator | `indicator.custom_formula` | 사용자 수식(안전한 표현식 평가, `simpleeval` 등 사용) |
| ai | `ai.sentiment_score` | 뉴스/공시 텍스트 감성 점수화(캐시 적용) |
| ai | `ai.regime` | 시장 국면 판단(상승/하락/횡보) — 보조 판단용 |
| logic | `logic.if_else` | 조건식 분기 (True 경로만 컨텍스트 전달) |
| logic | `logic.filter` | 종목 목록 필터링 |
| logic | `logic.rank` | 조건별 상위 N 랭킹 |
| logic | `logic.switch` | 다중 분기 |
| risk | `risk.stop_loss` | 손절 기준 적용 |
| risk | `risk.position_limit` | 종목당/전략당 투자 한도 적용 |
| execution | `execution.market_order` | 시장가 매수/매도 (OrderExecutionProvider) |
| execution | `execution.limit_order` | 지정가 주문 |

각 노드는 `app/nodes/<category>/<name>.py`에 1노드 1파일로 구현하고 단위 테스트를 병행한다.

---

## 4. 워크플로 정의/실행 엔진

### 4.1 워크플로 JSON 스키마 (프론트-백엔드 공통)
```json
{
  "id": "wf_123",
  "name": "긍정뉴스+거래량 급증 매수",
  "nodes": [
    {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60}},
    {"id": "n2", "type": "data.price", "params": {"universe": "KOSPI_TOP100"}},
    {"id": "n3", "type": "logic.if_else", "params": {"expr": "volume_ratio > 2.0"}},
    {"id": "n4", "type": "data.news", "params": {}},
    {"id": "n5", "type": "ai.sentiment_score", "params": {"threshold": 0.6}},
    {"id": "n6", "type": "execution.market_order", "params": {"side": "buy", "qty_pct": 0.1}}
  ],
  "edges": [
    {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"},
    {"from": "n3", "to": "n4", "branch": "true"}, {"from": "n4", "to": "n5"},
    {"from": "n5", "to": "n6", "branch": "true"}
  ]
}
```

### 4.2 검증 & 위상 정렬
`app/workflow/graph.py`
1. 스케줄러 노드는 정확히 1개, 진입 간선 없음(root).
2. 사이클 존재 시 오류(카안 알고리즘으로 위상 정렬 시도 중 큐가 비면 사이클로 판단).
3. 모든 노드는 스케줄러로부터 도달 가능해야 함(고아 노드 경고).
4. 결과: 실행 순서 리스트(위상 정렬 순서) — 워크플로 저장/활성화 시 1회 계산 후 캐시, 그래프 변경 시에만 재계산.

### 4.3 실행 (`app/workflow/engine.py`)
```python
class WorkflowEngine:
    def execute(self, workflow: WorkflowDef, mode: str, trigger_meta: dict,
                overrides: dict[str, Any] | None, market_data: MarketDataProvider,
                broker: OrderExecutionProvider, event_bus: EventBus) -> RunResult:
        order = workflow.topological_order()
        ctx_by_node: dict[str, NodeContext] = {}
        for node_id in order:
            node = workflow.get_node(node_id)
            inputs = [ctx_by_node[p] for p in workflow.predecessors(node_id) if predecessor_branch_matches]
            event_bus.publish(NodeExecutionEvent(run_id, node_id, status="running", ...))
            try:
                if overrides and node_id in overrides:      # 테스트 모드 임의 값 주입
                    out_ctx = node.apply_override(inputs, overrides[node_id])
                else:
                    out_ctx = node.execute(merge(inputs), providers=(market_data, broker))
                ctx_by_node[node_id] = out_ctx
                event_bus.publish(NodeExecutionEvent(..., status="success", output=out_ctx.snapshot()))
            except Exception as e:
                event_bus.publish(NodeExecutionEvent(..., status="error", error=str(e)))
                raise
        return RunResult(...)
```
- **다중 입력 병합**: 여러 선행 노드를 갖는 노드는 각 입력 컨텍스트의 `symbols` 딕셔너리를 종목코드 기준 병합(동일 키는 최신 값으로 덮어쓰되 이력은 `meta.history`에 append)한다.
- **분기(IF/Switch)**: 조건 불충족 경로는 하위 노드로 전파하지 않음(해당 하위 노드는 "skipped" 이벤트 발행) → 프론트에서 회색 처리로 표현 가능.
- **테스트 모드 오버라이드**: `POST /workflows/{id}/run {mode:"test", overrides:{"n2": {"005930": {"price": 71000}}}}` 형태로 특정 데이터 노드의 출력값을 사용자가 직접 지정 가능 (기획 요구사항 "임의의 값들을 사용해서 테스트").

### 4.4 이벤트 버스 (디버그 하이라이트)
```python
class EventBus(ABC):
    def publish(self, event: NodeExecutionEvent) -> None: ...
    def subscribe(self, run_id: str) -> Iterator[NodeExecutionEvent]: ...
class InMemoryEventBus(EventBus): ...  # asyncio.Queue per run_id
```
`WS /ws/runs/{run_id}`가 `EventBus.subscribe`를 소비해 프론트로 push → 프론트는 이벤트 수신 시 해당 노드를 즉시 하이라이트(깜빡임)하고 입력/출력 JSON을 디버그 패널에 표시. 모든 이벤트는 `node_events` 테이블에도 적재되어 실행 종료 후 "리플레이"가 가능하다(백테스트 결과 화면에서도 동일 컴포넌트 재사용).

---

## 5. 트리거 큐 / 스케줄러 / 워커 풀

### 5.1 인터페이스
```python
# app/trigger/queue.py
class TriggerQueue(ABC):
    def put(self, trigger: Trigger) -> None: ...
    def get(self, timeout: float | None = None) -> Trigger | None: ...
    def task_done(self, trigger: Trigger) -> None: ...

class InMemoryTriggerQueue(TriggerQueue):
    """queue.Queue 기반 PoC 구현. 추후 RedisTriggerQueue/KafkaTriggerQueue로 교체 가능."""
```

### 5.2 스케줄러 서비스
- 백그라운드 스레드(`SchedulerService`)가 1초 tick마다 `status=active`인 워크플로들을 순회, `next_fire_time <= now`이면 `Trigger(workflow_id, run_id=uuid4(), fired_at=now)`를 큐에 push하고 `next_fire_time += interval_sec` 갱신.
- **라이브 더미 시세**: `DummyMarketDataProvider`가 각 종목의 최근 종가(sqlite `price_bars`의 최신 일봉)를 시드로 삼아 초 단위 랜덤워크(seed 고정 가능)로 현재가를 생성 → 1초 스케줄러 테스트가 가능하게 함. 실제 서비스 연동 시 `TossInvestMarketDataProvider`로 교체.

### 5.3 워커 풀
- `ThreadPoolExecutor(max_workers=settings.WORKER_POOL_SIZE)`가 큐를 폴링하며 `WorkflowEngine.execute()` 호출.
- 노드 실행 자체는 프로세스/스레드 경계와 무관하게 순수 함수로 작성 → 추후 `ProcessPoolExecutor`로 교체 시 노드 입출력(NodeContext)이 pickle 가능해야 함(dict/기본타입만 사용하도록 강제).
- 워커는 실행 완료 후 `runs`, `node_events`, (실행 노드가 있으면) `orders` 테이블에 결과 기록.

### 5.4 배치 프로세스 분리 지점
`app/batch/worker.py`에 `SchedulerService` + 워커 풀 부트스트랩 로직을 두고, FastAPI `main.py`의 `startup` 이벤트에서 동일 함수를 호출하는 방식으로 구성 → 나중에 `python -m app.batch.worker`로 별도 프로세스 기동 시 API 서버와 분리 가능(단, Queue를 프로세스 간 공유 가능한 구현으로 교체해야 실질적 분리 효과가 있음을 §2 원칙 4에 명시).

---

## 6. 마켓데이터 / 주문 실행 어댑터

```python
# app/market_data/base.py
class MarketDataProvider(ABC):
    def get_price(self, symbol: str) -> PriceTick: ...
    def get_orderbook(self, symbol: str) -> OrderBook: ...
    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]: ...

# app/broker/base.py
class OrderExecutionProvider(ABC):
    def place_order(self, order: OrderRequest) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> None: ...
    def get_balance(self) -> Balance: ...
    def get_positions(self) -> list[Position]: ...
```

구현체:
| 구현체 | 용도 |
| --- | --- |
| `DummyMarketDataProvider` | 라이브/테스트 모드. sqlite 일봉 시드 + 랜덤워크로 초단위 시세 생성 |
| `HistoricalMarketDataProvider` | 백테스트 모드. sqlite `price_bars`를 날짜순으로 리플레이 |
| `TossInvestMarketDataProvider` | **스켈레톤(미검증)**. OAuth2 Client Credentials 토큰 발급 + 시세/호가/캔들 REST 호출부만 구현, `.env`에 키 없으면 초기화 시 명시적으로 비활성 처리 |
| `DummyOrderExecutionProvider` | 모의 체결(현재가 즉시 체결), 가상 현금/포지션을 sqlite `orders`/`positions_ledger`에 기록 (테스트·백테스트 공용) |
| `TossInvestOrderExecutionProvider` | **스켈레톤(미검증)**. 주문 생성/취소/조회 REST 호출부만 구현 |

Provider 선택은 `app/config.py`의 `MARKET_DATA_PROVIDER=dummy|historical|toss`, `ORDER_PROVIDER=dummy|toss` 환경변수로 결정하며, 실행 모드(live/test/backtest)에 따라 엔진이 자동으로 적절한 Provider를 주입한다(backtest는 항상 historical+dummy 강제).

백테스트 시세 자동 수집(네이버 차트 API로 일봉+시간봉 확보)은 §8-1 참조.

---

## 7. AI 모듈

### 7.1 공통
- `app/ai/openai_client.py`: `OPENAI_API_KEY`는 백엔드 `.env`에서만 읽음. 프론트는 AI 관련 API를 백엔드 라우터(`/ai/*`)로만 호출하며 키를 전달/노출하지 않음.
- 모든 AI 응답은 `model`, `prompt_version`을 함께 기록해 캐시 키에 포함(프롬프트 개선 시 캐시 무효화 자동 처리).
- 기본 모델은 `OPENAI_MODEL=gpt-5.6-luna`(§0-1). `chat.completions.create` 호출이 `temperature` 관련 `BadRequestError(param="temperature")`를 받으면 `temperature` 없이 1회 재시도 — gpt-5 계열 reasoning 모델은 기본값(1) 외의 temperature를 지원하지 않기 때문(모델 자체를 하드코딩해 분기하지 않고 오류 기반으로 대응해 향후 모델 교체에도 견고함).

### 7.5 캔버스 통합 챗봇 (`app/ai/workflow_chat.py`, `POST /ai/workflow-chat`)
1. 요청에 현재 워크플로 이름/그래프, 사용자 메시지, 최근 대화 이력(최대 12개), (있으면) 마지막 테스트 실행 결과(`status`/`events`/`final_symbols`)를 포함.
2. 시스템 프롬프트가 AI에게 요청을 "그래프 수정 지시" vs "구조/실행 결과 설명 질문" 중 하나로 분류하도록 지시하고, 응답 JSON의 `changed` 불리언으로 결과를 구분.
3. `changed=false`: `reply` 텍스트만 그대로 반환(그래프 검증 생략, 순수 Q&A).
4. `changed=true`: 응답의 `nodes`/`edges`를 `WorkflowGraph.validate()`로 검증(§4.2). 실패 시 오류를 포함해 1회 재시도, 그래도 실패하면 422로 원문+오류 반환(§7.2 초안 생성과 동일 패턴). 성공 시 `graph`+`disclaimer`를 함께 반환하되 **저장/캔버스 반영은 하지 않음** — 프론트가 미리보기로 보여주고 사용자가 "적용"해야 `flowNodes`/`flowEdges`에 반영(§0-1).

### 7.2 자연어 → 워크플로 초안 생성 (`app/ai/workflow_draft.py`)
1. 시스템 프롬프트에 `NODE_REGISTRY`의 사용 가능한 노드 타입/파라미터 스키마를 주입.
2. OpenAI Structured Output(`response_format={"type":"json_schema", ...}`)으로 §4.1 워크플로 JSON 스키마에 맞는 draft 생성 요청.
3. 생성된 JSON을 `WorkflowGraph` 검증기(§4.2)에 통과시킴. 실패 시 오류 메시지를 프롬프트에 포함해 1회 자동 재시도, 그래도 실패하면 사용자에게 원문 응답 + 오류를 함께 반환(수동 수정 유도).
4. 결과는 **자동 저장/활성화하지 않고** `status=draft`로 반환 — 사용자가 캔버스에서 검토 후 저장해야 함(기획서 "위험 고지" 요건 반영).

### 7.3 DART 공시 점수화 (`app/ai/disclosure_scoring.py`)
1. `data_ingestion/opendart_client.py`가 종목별 최근 공시 목록/원문을 가져와 `disclosures` 테이블에 적재.
2. `ai.sentiment_score`류 노드나 배치 작업이 공시를 스코어링할 때, 먼저 `ai_score_cache(subject_type='disclosure', subject_id=rcept_no, prompt_version, model)`를 조회.
3. 캐시 미스일 때만 OpenAI 호출 → 점수/요약 JSON을 캐시에 저장. 캐시 히트 시 AI 호출 없이 즉시 반환 → **AI 사용량 최소화** 요건 충족.

### 7.4 뉴스 감성 노드
동일한 캐시 전략을 `subject_type='news'`로 적용(§7.3과 로직 공유, `app/ai/scoring_cache.py`로 공통화).

---

## 8. 백테스트 엔진

`app/backtest/runner.py`
- 입력: `workflow_id`, 종목 유니버스, 시작/종료일, 초기자본, (선택) 리플레이 주기(일봉 기준 1일 1틱이 기본; 인트라데이는 PoC 범위 밖).
- `HistoricalMarketDataProvider`가 날짜를 순회하며 각 날짜를 하나의 트리거처럼 `WorkflowEngine.execute(mode="backtest")`에 공급.
- `DummyOrderExecutionProvider`가 각 날짜 종가 기준으로 가상 체결, 손익/보유내역을 누적.
- 종료 후 `app/backtest/metrics.py`가 계산:
  - 누적수익률/연환산수익률(CAGR)
  - 최대낙폭(MDD)
  - 승률, 손익비, 거래횟수, 변동성(일간 수익률 표준편차)
  - 자산곡선(equity curve, 시계열)
- 결과는 `backtest_results` 테이블에 저장, 노드 실행 이벤트도 `node_events`에 남아 프론트에서 "특정 시점 재생" 가능.

### 8-1. 백테스트 자동 시세 수집 (`app/data_ingestion/naver_price_client.py`, `auto_ingest.py`)

`POST /backtest` 라우터가 `BacktestRunner` 실행 전, `universe`의 각 종목에 대해 요청 구간의
일봉이 하나도 없으면(§0-2) `NaverStockChartClient`로 일봉+시간봉을 수집해 각각
`price_bars`/`price_bars_intraday`에 저장한다(`ensure_price_data`). 일봉 수집이 실패하면
오류를 기록하고 계속 진행(이후 `BacktestRunner`가 데이터 없음으로 400 처리), 시간봉 수집
실패는 조용히 무시(백테스트 자체는 일봉만 필요).

`NaverStockChartClient`는 `stock.naver.com`이 프론트엔드에서 쓰는 비공식 공개 엔드포인트를
호출한다(별도 키/인증 불필요, 2026-07-22 실측 확인). `day`(일봉)는 기간 제한 없이 응답하지만,
`minute60`(시간봉)은 요청한 시작일과 무관하게 서버가 최근 영업일 기준 제한된 lookback만
반환한다(실측 약 8거래일치 56봉) — 오래된 시간봉은 이 소스로 확보할 수 없다는 한계를 인지하고
사용해야 한다.

터미널에서 수동으로 미리 적재하고 싶으면 `backend/app/cli/ingest_prices.py`를 직접 실행한다:
```bash
cd backend && ./.venv/bin/python -m app.cli.ingest_prices --symbol 005930,000660 --start 2026-06-01 --end 2026-07-20
```

---

## 9. DAO / 데이터베이스

### 9.1 Repository 패턴
```python
class WorkflowRepository(ABC):
    def get(self, id: str) -> WorkflowDef | None: ...
    def save(self, wf: WorkflowDef) -> None: ...
    def list_by_user(self, user_id: str) -> list[WorkflowDef]: ...
# 동일 패턴: RunRepository, NodeEventRepository, OrderRepository, BacktestResultRepository,
#            PriceBarRepository, DisclosureRepository, NewsRepository, AIScoreCacheRepository, UserRepository
```
- SQLite 구현체: `app/dao/sqlite/*` (SQLAlchemy 2.0 ORM, 파일 `nemo_stock.db`). 다른 RDB(Postgres 등) 전환 시 `DATABASE_URL`만 변경 + 방언 차이가 있는 부분만 조정.
- 인메모리 구현체: `app/dao/memory/*` (dict 기반). 휘발성 테스트 실행(저장 불필요한 단발 테스트 run)이나 유닛테스트에서 사용, 동일 ABC를 구현하므로 서비스 계층은 구현체를 몰라도 됨.
- 어떤 구현체를 쓸지는 DI(간단한 팩토리 함수 + FastAPI `Depends`)로 주입.

### 9.2 주요 테이블
```
users(id, username, password_hash, created_at)
workflows(id, user_id, name, graph_json, status, schedule_interval_sec, created_at, updated_at)
runs(id, workflow_id, mode, status, started_at, finished_at)
node_events(id, run_id, node_id, node_type, status, input_json, output_json, error, started_at, finished_at)
orders(id, run_id, symbol, side, order_type, qty, price, status, filled_at)
positions_ledger(id, run_id, symbol, qty, avg_price, updated_at)
backtest_results(id, run_id, workflow_id, start_date, end_date, initial_capital, final_equity,
                  cagr, mdd, win_rate, profit_loss_ratio, trade_count, equity_curve_json)
price_bars(symbol, date, open, high, low, close, volume, source, PRIMARY KEY(symbol, date))
price_bars_intraday(symbol, bar_datetime, interval, open, high, low, close, volume, source,
                     PRIMARY KEY(symbol, bar_datetime, interval))  -- §8-1, 네이버 시간봉(minute60)
disclosures(id, corp_code, symbol, rcept_no, title, disclosed_at, raw_text, source)
news(id, symbol, title, body, published_at, source)
ai_score_cache(id, subject_type, subject_id, prompt_version, model, score_json, created_at,
                UNIQUE(subject_type, subject_id, prompt_version, model))
```

---

## 10. 인증

- 단일 계정: 서버 최초 기동 시 `.env`의 `ADMIN_USERNAME`/`ADMIN_PASSWORD`(또는 해시)로 `users` 테이블에 1건 upsert.
- `POST /auth/login` → JWT(HS256, `JWT_SECRET` 환경변수) 발급, 만료시간 설정.
- 이후 모든 API(`/workflows`, `/ai`, `/backtest`, `/data`, WS 포함)는 `Authorization: Bearer <token>` 필요(FastAPI dependency).
- 프론트는 로그인 화면 → 토큰을 메모리(+`sessionStorage`)에 보관, axios interceptor로 자동 첨부.

---

## 11. API 설계 (요약)

| Method | Path | 설명 |
| --- | --- | --- |
| POST | /auth/login | 로그인, JWT 발급 |
| GET | /nodes | 노드 레지스트리(팔레트/속성 스키마) |
| GET/POST | /workflows | 목록/생성 |
| GET/PUT/DELETE | /workflows/{id} | 조회/수정/삭제 |
| POST | /workflows/{id}/validate | 그래프 검증(사이클/고아노드 등) |
| POST | /workflows/{id}/run | 테스트 실행(overrides 지원), run_id 반환 |
| POST | /workflows/{id}/activate / /deactivate | 라이브 스케줄 on/off |
| GET | /runs/{id} | 실행 요약 + 노드 이벤트 로그 |
| WS | /ws/runs/{id} | 실시간 노드 이벤트 스트림(디버그 하이라이트) |
| POST | /ai/generate-draft | 자연어 → 워크플로 초안 |
| POST | /backtest | 백테스트 실행 요청(비동기, run_id 반환) |
| GET | /backtest/{id} | 결과 조회(지표+자산곡선+거래내역) |
| POST | /data/ingest/prices | 공공데이터포털 일봉 수집→sqlite 적재(관리용) |
| POST | /data/ingest/disclosures | OpenDART 공시 수집→sqlite 적재(관리용) |

---

## 12. 프론트엔드 설계

- **스택**: Vue 3 + Vite + TypeScript, 상태관리 Pinia, 그래프 캔버스 **Vue Flow**(`@vue-flow/core`), 차트는 경량 라이브러리(자산곡선 등)로 Chart.js 사용, HTTP는 axios, 실시간은 네이티브 WebSocket.
- **화면 구성**:
  1. 로그인
  2. 대시보드(워크플로 목록, 상태, 빠른 실행)
  3. AI 전략 생성(자연어 입력 → 초안 미리보기 → "캔버스에서 편집" 이동, 위험 고지 문구 표시)
  4. 전략 빌더(캔버스 = 핵심 화면)
     - 좌: 노드 팔레트(카테고리별, `/nodes` 응답 기반 동적 렌더)
     - 중: Vue Flow 캔버스(노드 드래그/연결)
     - 우: 속성 패널(선택 노드의 `param_schema` 기반 동적 폼) + 검증 패널(`/workflows/{id}/validate` 결과)
     - 하단: 저장 / 테스트 실행(오버라이드 값 입력 모달) / 백테스트 실행 버튼
     - 테스트 실행 시 WS로 이벤트 수신 → 진행 중 노드 테두리 애니메이션(깜빡임) + 클릭 시 입력/출력 JSON 사이드패널 표시
  5. 백테스트 결과(지표 요약, 자산곡선 차트, 거래내역 테이블, 노드 실행 리플레이 — 전략 빌더 캔버스 컴포넌트 재사용)
  6. 라이브 모니터링(활성 전략 상태, 최근 실행/주문 내역, 긴급 정지 버튼)

---

## 13. 디렉토리 구조

```
nemo-stock/
  DESIGN.md
  nemo-stock.md
  backend/
    app/
      main.py
      config.py
      auth/
      nodes/{base.py, scheduler.py, data/, indicator/, ai/, logic/, risk/, execution/}
      workflow/{graph.py, engine.py, events.py}
      trigger/{queue.py, scheduler_service.py, worker_pool.py}
      batch/worker.py
      market_data/{base.py, dummy.py, historical.py, toss_adapter.py}
      broker/{base.py, dummy.py, toss_adapter.py}
      ai/{openai_client.py, workflow_draft.py, disclosure_scoring.py, news_sentiment.py, scoring_cache.py}
      backtest/{runner.py, metrics.py}
      data_ingestion/{public_data_price.py, opendart_client.py}
      dao/{base.py, sqlite/, memory/}
      api/{routers/*.py, ws.py}
      schemas/*.py
    tests/{unit/, integration/}
    pyproject.toml
    .env.example
  frontend/
    src/{views/, components/, api/, stores/}
    package.json
```

---

## 14. 테스트 전략

- **유닛(pytest)**: 노드별 `execute()` 동작, 위상 정렬/사이클 검증, TriggerQueue 인메모리 구현, Repository CRUD(임시 sqlite 파일), AIScoreCache 히트/미스(OpenAI 클라이언트 mock), 백테스트 지표 계산(합성 데이터로 기대값 고정), Dummy Provider 결정성(시드 고정).
- **통합**: 기획서 예시 시나리오(스케줄러→시세→[조건]→뉴스/공시→[긍정]→매수, `logic_sample.png` 참조)를 오버라이드 값으로 TEST 모드 실행 → 최종 매수 주문 발생 검증. 소규모 합성 가격 시계열로 백테스트 end-to-end 실행.
- **API**: FastAPI `TestClient`/httpx로 인증, 워크플로 CRUD, 실행, 백테스트 제출/조회 검증.
- **프론트**: 개발 서버 기동 후 실제로 전략 생성→캔버스 편집→테스트 실행(하이라이트 확인)→백테스트까지 수동 시나리오 확인(자동화 테스트는 PoC 범위상 핵심 플로우 위주로 최소화).

---

## 15. 개발 단계 (Phase)

1. **Phase 1 – 코어 실행 엔진**: Node ABC/레지스트리, WorkflowEngine(위상정렬/실행/이벤트), TriggerQueue+Scheduler+WorkerPool(인메모리), DAO(sqlite: users/workflows/runs/node_events), 기본 노드 5종(scheduler.interval, data.price[dummy], indicator.moving_average, logic.if_else, execution.market_order[dummy]), 워크플로 CRUD+테스트실행 API, 유닛/통합 테스트. → **이 시점에서 최초로 실행 가능한 테스트 확보**.
2. **Phase 2 – 백테스트 + 공공데이터**: 공공데이터포털 일봉 수집기, HistoricalMarketDataProvider, BacktestRunner+metrics, 백테스트 API/테스트.
3. **Phase 3 – AI 모듈**: OpenAI 클라이언트, 자연어→워크플로 초안, OpenDART 수집기, 공시/뉴스 점수화+캐시, AI 관련 노드(ai.sentiment_score, ai.regime).
4. **Phase 4 – 인증/이벤트버스/WS/Toss 스켈레톤**: JWT 로그인, EventBus+WS 브로드캐스트, TossInvest 어댑터 스켈레톤.
5. **Phase 5 – 프론트엔드**: Vue3+Vue Flow 캔버스, 노드 팔레트/속성/검증 패널, 테스트 실행 디버그 하이라이트, 백테스트 결과 대시보드, 로그인.
6. **Phase 6 – 통합 QA**: 기획서 예시 시나리오 E2E(백엔드+프론트), 회귀 점검, README 정리.

각 Phase 종료 시점마다 해당 범위의 테스트를 실행/통과시키고 다음 단계로 진행한다.

---

## 16. back-news-analysis — 뉴스 이벤트 분석 파이프라인 (독립 프로젝트, `back-news-analysis/`)

`backend/`·`frontend/`와 별도로 루트에 위치한 독립 Python 프로젝트. `naver_economy_news.json`(네이버
경제 뉴스 92,229건)을 AI로 분석해 종목별 백테스트에 쓸 수 있는 뉴스 영향도 변수를 산출한다.
`backend/.venv`(openai/dotenv 이미 설치됨)를 그대로 재사용하고, `OPENAI_API_KEY`도 `backend/.env`의
값을 그대로 읽는다(별도 키 보관 없음). 상세 사용법은 `back-news-analysis/README.md` 참조.

### 16.1 기사 단위 AI 라벨링 (고정 스키마 10개 필드)

뉴스 1건이 들어오면 AI(채팅 모델, 백엔드와 동일한 `gpt-5.6-luna`)가 다음 10개 필드를 JSON으로
추출한다(`scoring.py`): `depth1`(상위분류), `depth2`(긍정/중립/부정), `depth3`(세부 이벤트 유형),
`scope_type`(종목직접/업종전반/시장전체), `related_tickers`(관련 종목), `related_industries`(관련
업종), `impact_strength`(High/Medium/Low), `time_horizon`(단기/중기/장기), `confidence`(확실/보통/
불확실), `reasoning`(분류 근거). `sentiment`(+1/0/-1)와 `magnitude`(1.5/1.0/0.5)는 각각
`depth2`/`impact_strength`로부터 파생되는 계산값으로 별도 AI 호출 없이 도출한다(`schemas.py`).

### 16.2 이벤트 클러스터링

"뉴스가 들어올 때마다 기존 대표뉴스들과 함께 AI에 넣어서 판단, 새로 생기는지 판단"이라는 요구를
임베딩(`text-embedding-3-small`) 유사도로 구현했다(`clustering.py`). 순수 LLM 순차 판단 방식은
뉴스 건수만큼 서로 의존하는 호출이 필요해 아래 §16.3 Batch API(비용 절감)와 근본적으로 맞지 않기
때문이다. 시간순으로 뉴스를 훑으며, 임베딩이 기존 클러스터 대표(centroid)와 코사인 유사도
임계값(`CLUSTER_SIMILARITY_THRESHOLD`, 기본 0.62) 이상이면 편입하고 아니면 새 클러스터를 만든다.

### 16.3 대량 처리 비용 절감 — OpenAI Batch API

임베딩과 채팅(라벨링) 호출은 뉴스 1건당 완전히 독립적인 요청이라 Batch API(50% 할인,
`embeddings.py`/`scoring.py`의 `submit_*_batch`/`poll_*_batch`)로 대량 제출·완료 후 캐시에 반영한다
(`build_pool.py --submit` / `--poll`). 백테스트 등에서 캐시에 없는 뉴스가 필요할 때만
(`extract_variables.py`) 그 자리에서 동기 호출로 즉시 채워 넣는다(온디맨드 경로는 배치가 아닌
실시간 API 사용 — 속도가 우선이므로).

### 16.4 최종 점수 계산 (`aggregate.py`)

```
strength = sentiment(+1/0/-1) * magnitude(1.5/1.0/0.5)
decay(d) = 1 / (d + 1)                              # d = 이벤트 최초 보도일로부터 경과일
count_factor = 1 + 0.3 * log(source_count)          # source_count = 같은 이벤트를 다룬 뉴스 수
event_score = strength * decay(d) * count_factor
종목 점수 = 그 종목에 관련된 모든 이벤트의 event_score 합산 -> 평균 -> tanh로 [-1, 1] 정규화
```

### 16.5 캐시 — JSON / SQLite 이중 지원

`cache_store.py`가 `JSONCacheStore`/`SQLiteCacheStore` 두 구현을 동일 인터페이스(`CacheStore`)로
제공하며 `--store json sqlite`로 선택. `build_pool.py`가 약 1000건(기본값)을 미리 처리해 캐시를
채우는 "AI 풀" 빌더 역할을 한다(2026-07-22 최초 구축: 뉴스 1000건 처리 → 이벤트 클러스터 608개,
JSON/SQLite 양쪽에 저장 완료). `score_stock.py`는 특정 종목·기준일의 점수를 조회하는 데모 CLI로,
캐시에 없는 뉴스는 `extract_variables.ensure_variables()`가 즉시 채워 넣는다.
