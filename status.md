# nemo-stock 진행 상황 (status.md)

> 이 파일은 작업 진행 상황의 단일 소스다. 작업 시작 전 `CLAUDE.md`의 안내에 따라
> 이 파일 → `DESIGN.md` → `git log`를 순서대로 확인한다. 이 파일이 git log와
> 어긋나면 git log(실제 코드/커밋)를 신뢰한다.

## 운영 방침 (사용자 지시, 2026-07-14)

- 완료될 때까지(Phase 2~6) 계속 진행한다. 설계가 확정된 범위 내에서는 재질문 없이 개발을 이어간다.
- 모든 작업은 git으로 관리한다(저장소는 프로젝트 루트 `nemo-stock/`에 2026-07-14 `git init`으로 생성). Phase/주요 작업 단위로 커밋한다.
- 진행 상황은 이 `status.md`에 계속 기록한다(이 지시 자체도 기록해 둔다 — 지금 이 섹션).
- 향후 이 저장소에서 작업하는 에이전트(세션)는 작업 전 반드시 `status.md` → `DESIGN.md` → `git log`를 읽는다. 이 규칙은 `CLAUDE.md`에도 명시되어 있다.

## 확정된 의사결정 요약 (상세는 DESIGN.md §0)

| 항목 | 결정 |
| --- | --- |
| AI 자연어 전략 초안 생성 | 포함 (Phase 3에서 구현) |
| 인증 범위 | 단일 계정 JWT 로그인 |
| Toss증권 연동 | 더미 구현 + 어댑터 스켈레톤(미검증) |

Toss증권 Open API는 실존(`developers.tossinvest.com`, OAuth2 Client Credentials, REST). 공공데이터포털 금융위원회_주식시세정보 API는 일 1회 T+1 갱신(백테스트용 일봉 소스로 사용, 실시간 아님). 상세 근거는 DESIGN.md §0 참조.

## Phase 진행 현황

- [x] **설계**: `DESIGN.md` 작성 완료 (아키텍처, 노드 시스템, 워크플로 엔진, 트리거 큐/스케줄러/워커, DAO, 마켓데이터/브로커 어댑터, AI 모듈, 백테스트, DB 스키마, API, 프론트엔드, 디렉토리 구조, 테스트 전략, Phase 1~6 로드맵).
- [x] **Phase 1 — 코어 실행 엔진** (완료, 2026-07-14)
- [x] **Phase 2 — 백테스트 + 공공데이터** (완료, 2026-07-14)
- [ ] **Phase 3 — AI 모듈** (자연어→워크플로 초안, DART 공시 점수화+캐시, 뉴스 감성) — 다음 작업
- [ ] **Phase 4 — 인증/이벤트버스/WS 마감 + Toss 어댑터 스켈레톤** (Phase 1에서 인증/이벤트버스/WS는 이미 구현됨 — Toss 스켈레톤만 남음)
- [ ] **Phase 5 — 프론트엔드** (Vue3 + Vue Flow)
- [ ] **Phase 6 — 통합 QA**

### Phase 1 상세 (완료)

백엔드: `backend/` (Python 3.12 venv, FastAPI). 구현 범위:
- `app/nodes/base.py`: Node ABC, NodeContext, 레지스트리(`@register_node`)
- 기본 노드 5종: `scheduler.interval`, `data.price`, `indicator.moving_average`, `logic.if_else`, `execution.market_order`
- `app/workflow/graph.py`: JSON 파싱 + 검증(사이클/고아노드/스케줄러 단일성) + Kahn 위상정렬
- `app/workflow/engine.py` + `app/workflow/events.py`: WorkflowEngine(live/test/backtest 공용 실행 경로), NodeExecutionEvent + InMemoryEventBus
- `app/trigger/queue.py` + `scheduler_service.py` + `worker_pool.py`: InMemoryTriggerQueue, 1초 tick 스케줄러, ThreadPoolExecutor 워커풀
- `app/dao/`: Repository ABC(`base.py`) + SQLite 구현체(`sqlite/`, SQLAlchemy) + 인메모리 구현체(`memory/`) — users/workflows/runs/node_events/price_bars
- `app/market_data/dummy.py`, `app/broker/dummy.py`: 더미 시세(시드+랜덤워크)/더미 체결(페이퍼 원장)
- `app/auth/security.py`: JWT + bcrypt(직접 사용, passlib 미사용 — 아래 "이슈/결정" 참조)
- API: `/auth/login`, `/nodes`, `/workflows`(CRUD/validate/run), `/ws/runs/{run_id}`
- 테스트: `backend/tests/` 유닛 19 + 통합 5 = 24개, 전부 통과
- 수동 검증: 실제 uvicorn 서버 기동 → 1초 스케줄러 워크플로 활성화 → 4초간 4회 자동 발화, 매번 4노드 전체 실행/기록 확인(라이브 트리거 큐→스케줄러→워커풀→엔진→DAO 전체 경로 실증)

**이슈/결정**: `passlib[bcrypt]`가 최신 `bcrypt`(5.0)와 호환성 버그(`password cannot be longer than 72 bytes` 오탐)로 실패 → `passlib` 제거하고 `bcrypt` 라이브러리를 `app/auth/security.py`에서 직접 사용하도록 변경. `pyproject.toml`도 반영됨.

### Phase 2 상세 (완료, 2026-07-14)

- `app/data_ingestion/public_data_price.py`: 공공데이터포털 금융위원회_주식시세정보 API 클라이언트(`PublicDataPriceClient`). 엔드포인트 `GetStockSecuritiesInfoService/getStockPriceInfo`, `srtnCd`+`beginBasDt`/`endBasDt`로 조회, 페이지네이션 자동 처리, `resultCode` 오류 시 `PublicDataAPIError`. 실제 서비스키 없이도 `httpx.MockTransport`로 단위테스트 가능하도록 `http_client` 주입 지원.
- `app/market_data/historical.py`: `HistoricalMarketDataProvider` — `advance_to(date)`로 리플레이 커서를 이동시키고 `price_bars`를 조회. 라이브/테스트와 동일한 `MarketDataProvider` 인터페이스라 노드 코드 변경 없이 백테스트에 재사용됨.
- `app/backtest/metrics.py`: `compute_metrics()` — 총수익률/CAGR/MDD/변동성(연환산)/승률/손익비/거래횟수. 손익비·승률은 매도 체결의 `realized_pnl`(신규 필드, `OrderResult.realized_pnl`, `DummyOrderExecutionProvider`가 평단가 대비 실현손익을 계산해 채움) 기준.
- `app/backtest/runner.py`: `BacktestRunner` — 종목별 `price_bars`의 거래일 합집합을 캘린더로 사용, 날짜별로 `HistoricalMarketDataProvider.advance_to()` 후 `WorkflowEngine.execute(mode="backtest")` 재사용(라이브/테스트와 동일 실행 경로). 종가 기준 시가평가로 자산곡선(equity curve) 산출. 가격 데이터가 없으면 `ValueError`.
- DAO: `BacktestResultRecord`/`BacktestResultRepository`(`dao/base.py`) + SQLite 구현체(`backtest_results` 테이블, `equity_curve_json` 컬럼).
- API 신규:
  - `POST /data/ingest/prices/manual` — 임의 값으로 직접 시세를 넣어 테스트/백테스트 가능(기획서의 "임의의 값으로 테스트" 요건 충족).
  - `POST /data/ingest/prices/public` — 공공데이터포털 실제 수집(서비스키 없으면 400).
  - `POST /backtest`(workflow_id+universe+기간+초기자본 → 즉시 동기 실행 후 결과 반환·저장), `GET /backtest/{id}`.
- 테스트: 신규 14개(유닛 `test_metrics.py`, `test_historical_provider_and_backtest.py`, `test_public_data_price_client.py` + 통합 `test_api_backtest_flow.py`) 포함 **총 38개 전부 통과**. 합성 우상향 가격 시계열로 백테스트 end-to-end(최종자산 > 초기자본, MDD=0) 검증.
- 설계 대비 단순화: DESIGN.md는 `POST /backtest`를 "비동기, run_id 반환"으로 서술했으나 PoC 규모상 **동기 실행**으로 구현(작업 큐 불필요, 응답에 결과 즉시 포함). 데이터 규모가 커지는 시점에 비동기로 전환 가능(엔드포인트 계약은 유지하고 내부만 교체하면 됨).

### 다음 작업 (Phase 3 — AI 모듈)

1. `app/ai/openai_client.py`: OpenAI 클라이언트 래퍼(`OPENAI_API_KEY`는 백엔드 전용)
2. `app/ai/workflow_draft.py`: 자연어 → 워크플로 JSON 초안 생성(구조화 출력 + `WorkflowGraph.validate()` 재검증 + 1회 재시도), `POST /ai/generate-draft`
3. `app/data_ingestion/opendart_client.py`: OpenDART 공시 수집 클라이언트
4. `app/ai/scoring_cache.py` + `disclosure_scoring.py`(+`news_sentiment.py`): `ai_score_cache` 테이블/Repository로 캐싱, 캐시 히트 시 AI 미호출
5. AI 노드 추가: `ai.sentiment_score`, `ai.regime` (+ `data.news`, `data.disclosure` 데이터 노드도 이 단계에서 함께 구현)
6. 테스트: OpenAI 클라이언트는 mock으로 단위테스트(실제 키 불필요), 캐시 히트/미스 테스트, 자연어→워크플로 생성 결과가 `WorkflowGraph.validate()`를 통과하는지 검증

완료 후 `status.md` 갱신 + 커밋 → Phase 4(Toss 어댑터 스켈레톤)로 진행.

## 커밋 이력 참고

상세 이력은 `git log --oneline`으로 확인. 주요 지점만 이 파일에 요약하며, 전체 diff/시각은 git이 원본이다.
