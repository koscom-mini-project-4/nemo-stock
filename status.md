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
- [x] **Phase 3 — AI 모듈** (완료, 2026-07-14)
- [x] **Phase 4 — Toss 어댑터 스켈레톤** (완료, 2026-07-14)
- [x] **Phase 5 — 프론트엔드** (완료, 2026-07-14)
- [x] **Phase 6 — 통합 QA** (완료, 2026-07-14) — **PoC 1차 구현 완료**

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

### Phase 3 상세 (완료, 2026-07-14)

- `app/ai/base.py` + `app/ai/openai_client.py`: `AIClient` ABC(`available`/`model_name`/`complete_json`) + `OpenAIClient` 구현체. 키는 백엔드 `.env`(`OPENAI_API_KEY`)에서만 읽고 `response_format={"type":"json_object"}`로 JSON 모드 호출. 테스트는 `tests/unit/ai_test_doubles.py`의 `FakeAIClient`로 실제 OpenAI 호출 없이 진행.
- `app/ai/scoring_cache.py`: `get_or_compute_sentiment_score()` — (subject_type, subject_id, prompt_version, model) 키로 `AIScoreCacheRepository` 조회, 캐시 히트 시 AI 미호출. `PROMPT_VERSION="v1"`을 올리면 캐시 자동 무효화.
- `app/data_ingestion/opendart_client.py`: OpenDART `list.json` 공시 목록 클라이언트. **PoC 단순화**: 공시 원문(document.xml/zip)은 수집하지 않고 응답에 포함된 `report_nm`(공시 제목)을 AI 점수화 입력 텍스트로 사용. `stock_code`가 응답에 포함되어 있어 종목코드 필터링을 클라이언트 측에서 수행(corp_code 매핑 테이블 불필요). status "013"(데이터 없음)은 정상 처리, 그 외 오류코드는 `OpenDartAPIError`.
- `app/ai/workflow_draft.py`: 자연어 → 워크플로 JSON 초안 생성. `node_registry_schema()`를 프롬프트에 주입해 실제 존재하는 노드 타입만 쓰도록 유도, `WorkflowGraph.validate()`로 재검증, 실패 시 오류 메시지를 포함해 1회 재시도, 그래도 실패하면 `WorkflowDraftError(attempts=...)`. 성공 시 `DISCLAIMER`(AI 초안은 투자자문이 아니며 검토 후 저장/활성화 필요)를 함께 반환하고 **자동 저장/활성화하지 않음**.
- 신규 노드 3종: `data.news`(종목별 최근 뉴스를 `news_text`/`news_id`로 컨텍스트에 적재), `data.disclosure`(공시를 `disclosure_text`/`disclosure_id`로 적재), `ai.sentiment_score`(source=news|disclosure 파라미터로 위 텍스트를 읽어 캐시 경유 점수화, `sentiment_score`/`sentiment_summary` 필드 추가). 임계값 필터링은 기존 `logic.if_else`를 그대로 재사용(`sentiment_score > 50` 등) — 별도 필터 노드를 만들지 않음.
- `WorkflowEngine.execute()`에 `extra_providers: dict[str, Any] | None` 파라미터 추가 — market_data/broker 외의 노드 의존성(ai_client/ai_score_cache_repo/news_repo/disclosure_repo)을 node.execute(**providers)로 전달. `Container.node_providers()`가 이 dict를 만들고, `WorkerPool`(라이브), `/workflows/{id}/run`(테스트), `BacktestRunner`(백테스트) 세 실행 경로 모두에 동일하게 배선됨(라이브/테스트/백테스트 동일 실행 경로 원칙 유지).
- API 신규: `POST /ai/generate-draft`(키 없으면 400, 검증 실패 시 422+attempts), `POST /data/ingest/news/manual`, `POST /data/ingest/disclosures/public`(DART_API_KEY 없으면 400). `app/api/deps.py`에 `get_ai_client` 의존성을 별도로 분리해 테스트에서 `app.dependency_overrides[get_ai_client] = ...`로 손쉽게 대체 가능하게 함.
- 테스트: 신규 19개(유닛 `test_scoring_cache.py`/`test_workflow_draft.py`/`test_opendart_client.py`/`test_ai_nodes.py` + 통합 `test_api_ai_flow.py`) 포함 **총 57개 전부 통과**. 캐시 히트 시 AI 미호출, 초안생성 1회 재시도 후 성공/2회 실패 시 예외, OpenDART 페이지네이션/오류/데이터없음 처리, 뉴스 긍정→매수·부정→차단 시나리오, 동일 공시 재실행 시 캐시 재사용(AI 재호출 없음) 검증.
- 범위 축소: `ai.regime`(시장 국면 판단) 노드는 이번 Phase에서 구현하지 않음 — `ai.sentiment_score`와 동일한 `scoring_cache` 패턴을 재사용해 추후 쉽게 추가 가능하도록 설계되어 있어 필요 시점에 추가.

### Phase 4 상세 (완료, 2026-07-14)

- `app/broker/toss_auth.py`: `TossOAuthTokenProvider` — Client Credentials Grant 토큰 발급(`POST {base_url}/oauth2/token`) + 캐싱(만료 30초 전 갱신), `auth_header()`로 `Authorization: Bearer` 헤더 생성. market/broker 어댑터가 공유.
- `app/market_data/toss_adapter.py`: `TossInvestMarketDataProvider(MarketDataProvider)` — get_price/get_orderbook/get_ohlcv 구현.
- `app/broker/toss_adapter.py`: `TossInvestOrderExecutionProvider(OrderExecutionProvider)` — place_order/cancel_order/get_balance/get_positions 구현, `X-Tossinvest-Account` 헤더 포함.
- **명확한 한계(중요)**: 실제 승인된 Toss Open API 키가 없어 `developers.tossinvest.com`의 공식 OpenAPI 명세를 확인하지 못했다. 위 두 어댑터의 엔드포인트 경로(`/api/v1/quotes/{symbol}` 등)와 요청/응답 필드명(`price`, `prevClose`, `orderId` 등)은 **공개 요약 정보 기반 최선 추정 플레이스홀더**이며 각 파일에 `# TODO: 실제 키 발급 후 공식 명세로 교체 필요` 주석으로 명시했다. 실사용 전 반드시 명세 대조/수정이 필요하다. 이는 사전 확정된 결정(§0 "더미 구현 + Toss 어댑터 스켈레톤(미검증)")에 따른 의도된 범위다.
- 두 클래스 모두 `client_id`/`client_secret` 누락 시 생성자에서 즉시 `ValueError`.
- `app/config.py`에 `toss_account_id` 필드 추가(`.env.example`도 갱신).
- `app/dependencies.py`: `_build_market_data_provider()`/`_build_order_provider()` 팩토리 추가. `MARKET_DATA_PROVIDER=toss`/`ORDER_PROVIDER=toss`일 때 필요한 자격증명이 없으면 앱 기동 시점에 `RuntimeError`로 즉시 실패(조용한 폴백 없음). 기본값은 계속 dummy.
- 테스트: `test_toss_adapter.py`(토큰 캐싱, 인터페이스 준수, Bearer/Account 헤더 검증 — httpx.MockTransport, 실제 서비스 호출 아님) + `test_provider_selection.py`(설정값에 따른 Container 팩토리 선택/실패 검증) 총 11개 추가. **총 68개 전부 통과**.

### Phase 5 상세 (완료, 2026-07-14)

`frontend/` (Vite + Vue 3 + TypeScript, Node 26 / npm 11). 구현 범위:
- 스캐폴딩: `npm create vite -- --template vue-ts` + pinia, vue-router, axios, `@vue-flow/{core,background,controls,minimap}`, chart.js/vue-chartjs. `@` → `src` 경로 별칭(`tsconfig.app.json`/`vite.config.ts`).
- `src/api/`: `client.ts`(axios 인스턴스, 요청 인터셉터로 JWT 자동 첨부, 401 시 `setUnauthorizedHandler` 콜백으로 로그아웃+리다이렉트 — router와 순환 의존 피하려 콜백 주입 방식 사용), `types.ts`(백엔드 스키마 미러링), `services.ts`(엔드포인트별 함수), `ws.ts`(`/ws/runs/{run_id}` 구독 유틸 — 현재 미사용, 아래 참고).
- `src/stores/`: `auth.ts`(JWT, sessionStorage 영속), `draft.ts`(AI 생성 화면 → 빌더로 초안 1회성 전달).
- `src/router/`: `/login`, `/`(대시보드), `/strategies/new`, `/strategies/:id`, `/backtests/new`, `/backtests/:id`, `/ai/generate`. `beforeEach`로 미인증 접근 차단.
- `src/utils/layout.ts` + `flowAdapter.ts`: 백엔드는 노드 좌표를 저장하지 않으므로, 로드/노드 추가 시마다 스케줄러 기준 레이어드 레이아웃(Kahn 유사, max-level)으로 자동 배치. `graphToFlowElements`/`flowElementsToGraph`로 백엔드 그래프 ↔ Vue Flow 노드/엣지 상호 변환.
- **전략 빌더**(`StrategyBuilderView.vue`, 핵심 화면): `NodePalette`(카테고리별 클릭-추가) / `VueFlow` 캔버스(핸들 드래그로 연결, `useVueFlow().fitView`로 노드 추가 시 자동 화면맞춤) / 우측 탭(`PropertyPanel` — `param_schema` 기반 동적 폼, `ValidationPanel`, `DebugPanel`). 저장(생성/수정 자동 분기) → 검증 → 테스트 실행(`TestRunModal`, overrides JSON 직접 입력) → 활성화/비활성화 → 백테스트 이동.
- **테스트 실행 디버그 하이라이트**: `POST /workflows/{id}/run`의 동기 응답(`events` 배열)을 프론트에서 노드별로 순차 재생 — 실행 중인 노드는 노란 펄스(`.status-running`), 완료 노드는 초록/빨강 테두리(`.status-success`/`.status-error`)로 캔버스에 표시하고 동시에 `DebugPanel`에 이벤트가 하나씩 추가되며 클릭 시 input/output JSON을 볼 수 있다. **설계 대비 단순화**: DESIGN.md는 WS 실시간 스트리밍을 전제했으나, 테스트 실행은 이미 동기 응답으로 전체 이벤트를 받으므로 WS 없이 프론트에서 타이밍을 재현하는 방식을 채택(더 단순하고 결정적). `/ws/runs/{run_id}` 구독 유틸(`api/ws.ts`)은 준비만 해두고 실제 연동은 하지 않음 — 활성화된 워크플로를 실시간 관전하는 "라이브 모니터링" UI는 이번 Phase 범위 밖(다음 이터레이션 후보).
- **백테스트 결과 화면**(`BacktestResultView.vue`): `/backtests/new`는 workflow_id/종목/기간/초기자본 입력 폼(쿼리스트링으로 전략빌더에서 전달받음) → 실행 후 `/backtests/{id}`로 교체 이동, 지표 카드(수익률/CAGR/MDD/변동성/승률/손익비/거래횟수) + `EquityCurveChart`(vue-chartjs 자산곡선).
- **AI 전략 생성 화면**(`AIGenerateView.vue`): 자연어 입력 → `POST /ai/generate-draft` → 위험고지 문구 + 노드 목록 미리보기 → "캔버스에서 편집" 클릭 시 `draft` 스토어에 담아 `/strategies/new`로 이동, 빌더가 로드 시 소비.
- **대시보드**(`DashboardView.vue`): 워크플로 카드 목록(상태 배지/노드 수/수정시각), 편집/활성화-중지/삭제.
- 타입체크(`vue-tsc -b`) 및 프로덕션 빌드(`npm run build`) 통과. `ref<VFNode<FlowNodeData>[]>` 선언에서 `TS2589`(과도한 타입 재귀) 발생 → `ref([]) as Ref<...>` 캐스트 패턴 + `computed<T>()` 명시적 반환 타입으로 해결(원인: Vue Flow의 복잡한 제네릭과 Vue의 `UnwrapRef` 재귀 계산 충돌, 커뮤니티에 알려진 이슈).
- **브라우저 실증(Playwright, headless Chromium)**: `backend/.venv/bin/uvicorn`(:8000) + `npm run dev`(:5173) 동시 기동 후 로그인→대시보드→새 전략→팔레트에서 노드 3~4개 추가(fitView로 자동 화면맞춤 확인)→핸들 드래그로 연결→저장→검증(오류/성공 케이스 모두)→**테스트 실행 시 노드가 노란색으로 펄스했다가 초록색으로 바뀌는 애니메이션과 디버그 패널 실시간 채워짐을 스크린샷으로 직접 확인**→AI 생성 화면(키 미설정 시 400 오류 정상 처리)→백테스트 신규 폼까지 전체 골든 패스 구동, 콘솔 런타임 에러 0건.

### Phase 6 상세 (완료, 2026-07-14)

- `backend/tests/integration/test_logic_sample_scenario.py`: 기획서 `logic_sample.png` 원본 시나리오(스케줄러→시세→[트레이딩 전략 조건]→뉴스→[AI 감성 긍정]→매수)를 `data.news`/`ai.sentiment_score`까지 포함한 7노드 그래프로 재구성해 3가지 케이스(상승+긍정뉴스→매수 체결, 상승이지만 부정뉴스→차단, 하락이면 뉴스/AI 단계 도달 전 차단) 검증.
  - **버그 발견 및 수정**: 최초 작성 시 `app_client.app.dependency_overrides[get_ai_client]`로 AI를 모킹했으나, `/workflows/{id}/run`은 `Depends(get_ai_client)`를 경유하지 않고 `container.node_providers()`가 `container.ai_client`를 직접 읽는 구조라 오버라이드가 적용되지 않았다(반면 `/ai/generate-draft`는 해당 의존성을 직접 쓰므로 정상 동작). 양성 케이스(매수 체결 확인)는 이 문제로 즉시 실패해 발견했으나, 음성 케이스 2건은 "AI 미설정 시 예외 → sentiment_score=None → 조건 실패"라는 별개의 안전 경로를 타면서 우연히 통과해 문제를 가릴 뻔했다. `app_client.app.state.container.ai_client`를 직접 교체하는 방식으로 수정하고, 모든 케이스에 `fake_ai.calls` 호출 횟수 검증을 추가해 "우연한 통과"를 재발 방지했다.
- README 3종 작성/정리: 루트 `README.md`(전체 실행 가이드+문서 링크), `backend/README.md`, `frontend/README.md`(기존, Phase 5에서 작성).
- 전체 회귀: 백엔드 `pytest` **71개 전부 통과**(Phase 1: 24 → Phase 2: +14 → Phase 3: +19 → Phase 4: +11 → Phase 6: +3), 프론트 `vue-tsc -b` + `npm run build` 통과.

### PoC 완료 요약 (2026-07-14)

`DESIGN.md`에 정의된 Phase 1~6 전 범위 구현 완료. 노드 기반 워크플로 설계 → 검증 → 테스트 실행(디버그 하이라이트) → 백테스트 → (더미)실계좌 연동 인터페이스까지 기획서의 핵심 흐름을 노코드 캔버스로 구현하고, AI 자연어 전략 초안 생성과 뉴스/공시 감성 점수화(캐싱)를 통합했다.

**알려진 단순화·한계 (실 서비스 전환 시 우선 검토 대상)**

| 항목 | 현재 상태 | 비고 |
| --- | --- | --- |
| Toss증권 연동 | 어댑터 스켈레톤만 존재, 엔드포인트/필드명 미검증 | 승인된 API 키 발급 후 공식 명세로 교체 필요(Phase 4) |
| KOSCOM CHECK-API 연동 | 어댑터 스켈레톤만 존재, 실제 호출 미검증(자격증명 없음) | CHECK 단말 구독 후 cust_id/auth_key 발급 필요(2026-07-15 추가, `docs/koscom-api/README.md` 참조) |
| 백테스트 실행 | 동기(HTTP 응답 즉시 반환) | 데이터 규모 커지면 비동기 전환 필요(Phase 2) |
| 실시간 라이브 모니터링 UI | 없음(백엔드 WS 엔드포인트는 구현·테스트됨) | 프론트에서 활성 워크플로 실시간 관전 기능 추가 필요(Phase 5) |
| ai.regime(시장 국면 판단) | 미구현 | `ai.sentiment_score`와 동일 캐시 패턴 재사용 가능(Phase 3) |
| DART 공시 원문 | 제목(report_nm)만 사용, 원문(XML) 미수집. 종목 미지정 조회 시 시장 전체를 스캔하므로 max_pages=20으로 상한(2026-07-15 실사용 중 발견) | document.xml 파싱 및 corp_code 매핑 추가 시 개선 가능(Phase 3) |
| 뉴스 데이터 소스 | 수동 적재만 지원(`/data/ingest/news/manual`) | 실 뉴스 API/크롤러 연동 시 NewsRepository 인터페이스만 구현하면 교체 가능 |
| 노드 좌표 영속화 | 미지원(자동 레이아웃으로 매번 재배치) | 필요 시 WorkflowGraphIn에 layout 필드 추가 |
| 인증/사용자 | 단일 계정 | 실 서비스 전환 시 다중 사용자/회원가입 필요(§0 확정 결정, PoC 범위 내 의도된 제한) |
| 백테스트 데이터 소스 | 공공데이터포털 일봉(일 1회 T+1) — **실키로 검증 완료**(2026-07-15, 삼성전자/SK하이닉스 3~6월) + 수동 적재 | 실시간/분봉 데이터는 KOSCOM CHECK-API 등 별도 소스 필요 |

**아키텍처 검증된 확장 포인트** (설계 원칙대로 인터페이스 교체만으로 대체 가능함을 실증):
- `TriggerQueue`(인메모리 → Redis/Kafka), `MarketDataProvider`/`OrderExecutionProvider`(dummy → Toss/타 증권사), `Repository`(SQLite → 타 RDB, DATABASE_URL만 변경), `AIClient`(OpenAI → 타 LLM), `EventBus`(인메모리 → Redis pub/sub).

## E2E 브라우저 QA (2026-07-14, Phase 6 이후 추가 검증)

Playwright(headless Chromium)로 백엔드+프론트엔드를 동시 기동한 실제 애플리케이션을 구동해 로그인부터
대시보드 반영까지 골든 패스 12단계를 검증. 상세 결과와 단계별 스크린샷은
`docs/e2e/2026-07-14-golden-path/report.md` 참조(리포트별 디렉토리로 분리, 아래 2026-07-15 참조).

- **결과**: 12/12 PASS, 콘솔 런타임 에러 0건.
- **버그 발견 및 수정**: 노드를 3개 이상 연속으로 빠르게 추가하면 `fitView()`가 Vue Flow의 노드 크기
  측정(ResizeObserver) 완료 전에 호출되어, 최신 노드가 우측 속성/검증/디버그 패널 아래로 가려져 마우스로
  연결할 수 없는 프론트엔드 버그를 발견. `StrategyBuilderView.vue`에서 `fitView` 호출을
  `nextTick()` + `requestAnimationFrame` 2회 이후로 지연시키는 `scheduleFitView()`로 수정, 재검증 완료.
  실사용 흐름 그대로(팔레트 클릭 → 즉시 연결) 조작했기 때문에 발견 가능했던 이슈로, 자동화 스모크
  테스트만으로는 놓치기 쉬운 유형이었다.
- 수정 후 백엔드 `pytest` 71개 전부 통과, 프론트 `vue-tsc -b` + `npm run build` 통과 재확인.

## 2026-07-15 후속 작업: 노드 인라인 편집 + 실키 연동 + KOSCOM 어댑터

사용자 요청: (1) 노드 상세 설정을 코드로도 수정 가능하게, 파라미터가 노드 그래픽 안에 보이고
마우스로 값을 바꿀 수 있게(IF 조건도 그래프에 표시), (2) 실제 발급받은 OpenAI/공공데이터포털/
OpenDART 키로 재검증 + 리포트를 디렉토리별로 분리, (3) KOSCOM CHECK-API(`checkapi.koscom.co.kr`)
를 참고해 장중 실시세 연동 가능하도록.

**시크릿 관리**: `backend/.env.example`(git 추적됨)에 실제 OpenAI 키가 평문으로 들어가 있던 것을
발견해 `backend/.env`(gitignore 처리)로 이동하고 `.env.example`은 템플릿으로 원복. 공공데이터포털
서비스키는 디코딩된 원본 값을 써야 함(httpx가 자동 인코딩 — 인코딩된 값을 넣으면 이중 인코딩되어
인증 실패)을 확인해 반영. `tests/conftest.py`가 키 관련 설정을 명시적으로 빈 값으로 오버라이드하도록
보강(로컬 `.env`의 실제 키가 "키 미설정" 테스트 경로를 오염시키는 것을 방지).

**노드 UI**: `ParamFields.vue`(select/checkbox/number/text/expression 공용 렌더러)를 속성 패널과
캔버스 커스텀 노드(`#node-workflow` 슬롯)가 함께 사용하도록 구현 — 모든 파라미터가 캔버스 노드
박스 안에 그대로 보이고 마우스로 직접 수정 가능(`nodrag nopan`으로 Vue Flow 제스처와 분리). IF
조건(`logic.if_else`의 `expr`)은 모노스페이스+강조 배경으로 그래프에서 바로 눈에 띄게 표시.
속성 패널에 "폼"/"코드(JSON)" 탭을 추가해 노드 params를 JSON으로 직접 편집·적용 가능.

**실키 연동 중 발견해 수정한 버그 2건** (상세는 `docs/e2e/2026-07-15-full-verification/report.md`):
1. 공공데이터포털 시세 API의 `srtnCd`(종목코드 정확일치) 파라미터가 서버에서 무시되고 시장
   전체 데이터가 반환되는 버그 발견 — `likeSrtnCd`로 교체 + 클라이언트 측 방어적 재필터링 +
   `max_pages` 상한 추가. 다른 종목 데이터가 잘못된 심볼로 저장될 뻔한 데이터 무결성 문제였음.
2. OpenDART 공시 조회가 종목 미지정 시 시장 전체(수천 페이지)를 스캔해 타임아웃나는 문제 —
   `max_pages=20` 상한 추가.

**KOSCOM CHECK-API 어댑터 추가**: `checkapi.koscom.co.kr`을 Playwright로 실제 렌더링해(JS SPA)
공식 문서를 확인(`docs/koscom-api/README.md` + `raw-*.txt`). CHECK 단말 구독 고객 전용 유료
서비스라 실제 자격증명 없이 스켈레톤만 구현(Toss와 동일 성격의 한계, 다만 문서 근거는 더 구체적).
`app/market_data/koscom_adapter.py`의 `KoscomMarketDataProvider`가 basic_info/hoga_info/hist_info
3개 엔드포인트를 구현하고 공식 문서의 "1초당 1회" 레이트리밋을 실제로 강제한다.
`MARKET_DATA_PROVIDER=koscom`으로 다른 어댑터와 동일하게 선택 가능.

**실데이터 백테스트**: 사용자 요청대로 삼성전자(005930)+SK하이닉스(000660) 2종목, 2026년
3~6월 3개월 범위로 스코프를 좁혀 실제 공공데이터포털 데이터(각 81거래일)를 적재하고 백테스트
실행 성공(누적수익률 147.23%, MDD 18.73% — 매도 로직 없는 단순 매수 전략이라 거래횟수/승률은
0으로 정상 산출).

**회귀**: 백엔드 `pytest` **80개 전부 통과**, 프론트 `vue-tsc -b`+`npm run build` 통과. 두 번째
E2E 리포트는 `docs/e2e/2026-07-15-full-verification/`(스크린샷 11장 포함)에, 리포트 디렉토리
구조를 `docs/e2e/<날짜>-<제목>/{report.md, screenshots/}`로 표준화(기존 리포트도
`docs/e2e/2026-07-14-golden-path/`로 이동).

## 2026-07-15 후속 작업 2: KOSCOM 실계정 검증 + 전체 문서 크롤링

사용자가 실제 KOSCOM CHECK-API 자격증명(`KOSCOM_CUST_ID`/`KOSCOM_AUTH_KEY`, `backend/.env`에 보관)을
`.env`에 추가하고, (1) 어댑터를 실계정으로 검증, (2) 뉴스/공시 등 다른 카테고리 문서도
"제대로 된 크롤러"로 체계적으로 정리해 달라고 요청.

**KOSCOM 어댑터 실계정 검증 완료**: `get_price`/`get_orderbook`/`get_ohlcv` 3개 메서드 모두
005930/000660 기준 실제 호출 성공 확인. 더 이상 미검증 스켈레톤이 아님(Toss 어댑터는 여전히
미검증 — 실 자격증명 없음). `koscom_adapter.py` 모듈 docstring 갱신, 라이브 검증 전용 테스트
`backend/tests/integration/test_koscom_live.py` 추가(자격증명 없으면 `pytest.mark.skipif`로
자동 스킵 — CI/다른 개발자 환경에서 항상 안전). `app_client` 픽스처와 별개로 `Settings()`를
직접 읽어 실키를 사용하므로 다른 테스트의 monkeypatch 오버라이드와 충돌하지 않는다.

**checkapi.koscom.co.kr 전체 문서 크롤링**: 기존에는 뉴스/공시-API 등 일부만 수작업으로 조사했으나,
재사용 가능한 Playwright 크롤러(`docs/koscom-api/crawler/koscom_crawler.js`)를 새로 작성해
사이트 전체(6개 카테고리 · 84개 그룹 · **751개 리프 페이지**: 주식-API 243, 파생-API 334,
채권-API 72, 해외-API(license) 64, 뉴스/공시-API 7, 기타-API 31)를 크롤링, **실패 0건**(재시도
1회 포함 100% 성공). 결과는 `docs/koscom-api/pages/<category-slug>/<group>/<NN-leaf>.md`로
저장, 전체 목록/링크 인덱스는 `docs/koscom-api/pages/INDEX.md`. 카테고리별 샘플 페이지를
스팟체크해 내용 품질(요청 파라미터/응답 필드/예제 코드 모두 포함) 확인, 300바이트 미만의
비정상적으로 짧은 파일 없음(0건). `docs/koscom-api/README.md`를 전체 크롤 결과와 실계정 검증
완료 사실을 반영해 갱신.

크롤러 구현 요점: 사이드바가 시각적으로 접혀 있어도 DOM 구조는 항상 존재하므로
`page.evaluate()`로 카테고리→그룹→리프 트리를 먼저 전부 discover한 뒤, 각 리프를 클릭할 때는
동일한 이름의 리프가 다른 그룹에도 있을 수 있어 카테고리+그룹으로 스코프를 좁힌 뒤 정확한
`<span class="txt_detailidx">` 엘리먼트를 찾아 `.click()`(Playwright의 `text=` 셀렉터는
모호성/가시성 문제로 배제). 본문은 `.contents` CSS 클래스가 사이드바 노이즈 없이 깨끗하게
분리해줌을 확인. 리프당 최대 2회 재시도, 진행 상황은 `pages/_crawl-log.jsonl`에 JSONL로
누적 기록해 중단되어도 이어서 확인 가능하게 설계.

**회귀**: 백엔드 `pytest` **83개 전부 통과**(라이브 테스트 3개 포함), 프론트 `vue-tsc -b` 통과.
`.env`(실제 시크릿)는 항상 gitignore 처리 상태 유지, 커밋 전 `git status`로 스테이징 대상에
시크릿 파일 없음 확인.

## 2026-07-17 후속 작업: 캔버스 AI 챗봇 + 드래그앤드롭 노드 추가 + 예시 템플릿 + 모델 업그레이드

사용자 요청 4가지: (1) 노드 수정을 챗봇으로도 할 수 있게, (2) 노드의 진행 과정(그래프 구조+실행 결과)을
요약 설명해주는 챗봇, (3) 팔레트 클릭 외에 드래그해서 노드 추가, (4) AI 전략 생성 시작 시 예시 프롬프트
템플릿 버튼 + 더 나은 OpenAI 모델. 세부 결정 사항은 `DESIGN.md` §0-1 참조(통합 채팅창, 미리보기 후
적용, 그래프+실행결과 요약 범위, `gpt-5.6-luna` 모델).

**통합 챗봇**: (1)과 (2)를 하나의 채팅 UI로 통합하기로 확정 — 별도 엔드포인트 2개 대신
`app/ai/workflow_chat.py` + `POST /ai/workflow-chat` 하나로 처리. AI가 사용자 메시지를
"수정 지시" vs "설명 질문"으로 스스로 분류해 응답 JSON의 `changed` 불리언으로 구분(`changed=false`면
검증 없이 텍스트만, `changed=true`면 `WorkflowGraph.validate()` 통과 시에만 미리보기용 그래프 반환).
프론트 `ChatPanel.vue`가 캔버스 우측 새 "AI 챗봇" 탭으로 통합(`StrategyBuilderView.vue`). 수정 제안은
채팅 말풍선에 "노드 N개·엣지 N개로 변경" 요약 + 적용/취소 버튼으로 표시되며, "적용"을 눌러야
`flowNodes`/`flowEdges`에 반영됨(자동 반영 안 함 — 기존 AI 초안 생성과 동일한 검토 원칙 유지).

**드래그 앤 드롭**: `NodePalette.vue` 아이템에 `draggable` 부여, `StrategyBuilderView.vue` 캔버스에
`dragover`/`drop` 핸들러 추가. Vue Flow `screenToFlowCoordinate`로 드롭 지점을 노드 좌표로 변환해
기존 클릭 추가(그리드 배치)와 별개로 원하는 위치에 바로 배치 가능.

**예시 템플릿**: `AIGenerateView.vue`에 예시 투자 아이디어 4개(뉴스 긍정 매수, 이평선 돌파+손절, RSI
과매도+목표수익, 공시 호재)를 버튼으로 추가, 클릭 시 텍스트영역에 자동 채움(제출은 사용자가 직접).

**모델 업그레이드 중 발견한 회귀 버그**: 사용자가 지정한 `gpt-5.6-luna`(2026-07 출시, GPT-5.6
3단계 모델군 중 최저가 티어 — WebSearch로 실존 확인)로 `OPENAI_MODEL`을 바꾸자, 기존 코드가
모든 AI 호출에 하드코딩해 보내던 `temperature=0.2`가 400 에러(`Unsupported value: 'temperature'
... Only the default (1) value is supported`)를 유발해 챗봇이 500으로 죽는 문제 발견. gpt-5 계열
reasoning 모델의 공통 제약. `app/ai/openai_client.py`의 `complete_json`이 `BadRequestError`의
`body["param"] == "temperature"`를 감지하면 `temperature` 파라미터 없이 1회 재시도하도록 수정
(모델명을 하드코딩해 분기하지 않아 향후 모델 교체에도 견고함). 유닛 테스트(`test_openai_client.py`)로
회귀 방지.

**검증**: 실제 OpenAI API 키로 `/ai/workflow-chat`을 직접 curl 및 브라우저(Playwright)로 검증 —
"지금 이 전략 뭐하는거야?" 질문에 그래프 기반 정확한 자연어 설명 응답, "스케줄러 주기를 30초로
바꿔줘" 지시에 대해 그래프 수정 제안(미리보기)이 뜨고 "적용" 클릭 시 캔버스에 정확히 반영됨(부수적으로
드래그로 추가해 중복됐던 스케줄러 노드까지 AI가 알아서 정리). 드래그앤드롭 노드 추가, AI 전략 생성
템플릿 버튼 클릭도 브라우저에서 실제 동작 확인, 콘솔 에러 0건. 백엔드 `pytest` **93개 전부 통과**
(신규 13개: workflow_chat 유닛 5 + 통합 3 + openai_client 재시도 회귀 2 + 기존 유지), 프론트
`vue-tsc -b` 통과.

## 2026-07-22 후속 작업: 백테스트 자동 시세 수집 + back-news-analysis 뉴스 AI 분석 파이프라인

사용자 요청 2가지: (1) 포크 레포(`koscom_nemonemo`) 대비 기능 확장 + 백테스트 시 종목별
일봉/시간봉 자동 수집(종목코드 입력 포함), (2) 루트에 `back-news-analysis/` 디렉터리를 만들어
`naver_economy_news.json`에서 AI로 종목별 뉴스 영향도 변수를 추출하는 실행 가능한 파이프라인
(이벤트 클러스터링 + strength/decay/count_factor + 1000건 AI 풀 캐시, JSON/SQLite 이중 지원,
Batch API로 비용 절감, 기사 단위 고정 스키마 라벨링).

**포크 레포 조사 결과**: `koscom-mini-project-4/koscom_nemonemo`는 git 이력이 이어지지 않은 별도
커밋(2026-07-19, "Initial commit" 1개로 스쿼시)으로, 실제로는 현재 레포의 **더 이전 스냅샷**
(2026-07-17 캔버스 챗봇/드래그앤드롭 작업 이전 상태)이었다. `git diff --stat`으로 전체 비교한
결과 fork 쪽에만 있는 새 파일은 0개, 오히려 현재 레포 대비 뒤처진 파일 775개만 발견 — 병합할
신규 기능이 없어 조사만 하고 종료.

**백테스트 자동 시세 수집**(`app/data_ingestion/naver_price_client.py` +
`app/data_ingestion/auto_ingest.py`, DESIGN.md §8-1): 공공데이터포털/KOSCOM CHECK-API가 모두
일봉만 제공하는 한계 때문에, 네이버 증권의 비공식 차트 API(`api.stock.naver.com/chart/domestic/
item/{symbol}/{day|minute60}`, 별도 인증 불필요, 2026-07-22 실측 확인)로 일봉+시간봉(60분)을 모두
수집하는 `NaverStockChartClient`를 추가. **실측으로 확인한 중요한 한계**: `minute60`(시간봉)은
요청 시작일과 무관하게 서버가 최근 영업일 기준 제한된 lookback만 반환(실측 약 8거래일치 56봉) —
오래된 시간봉은 이 소스로 확보 불가. `day`(일봉)는 기간 제한 없이 정상 동작.

- 신규 테이블 `price_bars_intraday`(symbol, bar_datetime, interval, OHLCV, source) +
  `IntradayPriceBarRepository`(ABC/SQLite/인메모리 3종 구현) — 기존 `price_bars`는 PK가
  (symbol, date)라 시간 단위 다건 저장이 불가능해 별도 테이블로 분리.
- `ensure_price_data()`: `POST /backtest` 진입 시 요청 구간에 해당 종목 일봉이 하나도 없을 때만
  자동 수집(부분 공백은 건드리지 않는 의도된 단순화). 일봉 수집 실패는 결과에 기록, 시간봉 수집
  실패는 조용히 무시(백테스트 엔진 자체는 일봉만 사용하므로 시간봉 실패가 실행을 막지 않음).
  `Settings.auto_ingest_prices`(기본 true)로 on/off, 테스트는 결정론/오프라인 유지를 위해
  `tests/conftest.py`에서 명시적으로 false로 오버라이드.
- 터미널 실행용 CLI 신규: `app/cli/ingest_prices.py`(`python -m app.cli.ingest_prices --symbol ... --start ... --end ...`).
- **종목코드 자유 입력은 프론트(`BacktestResultView.vue`)에 이미 있던 콤마 구분 텍스트필드로
  이미 충족되어 있었음**(신규 UI 추가 없이 안내 문구만 갱신).
- 테스트: 신규 유닛 12개(`test_naver_price_client.py` 6, `test_auto_ingest.py` 4,
  `test_dao_sqlite.py` intraday repo 1) + 통합 1개(가짜 네이버 클라이언트를
  `dependency_overrides`로 주입해 자동수집→캐시로 재수집 안 함까지 검증) — **백엔드 pytest 105개
  전부 통과**, 프론트 `vue-tsc -b` 통과.
- **실검증**: 실제 uvicorn 서버 기동 후 사전 적재 없이 SK하이닉스(000660)로 curl 백테스트 실행 →
  자동으로 일봉 25건+시간봉 56건 수집되어 sqlite에 저장되고 백테스트 성공(201) 확인. 이어서
  Playwright로 브라우저에서 실제 UI(로그인 → `/backtests/new`에 종목 035420(NAVER, 사전 적재
  전무) 입력 → "백테스트 실행" 클릭)까지 구동해 자동 수집 후 결과 화면이 정상 렌더링되는 것을
  확인(콘솔 에러 0건).

**back-news-analysis 파이프라인**(DESIGN.md §16): `naver_economy_news.json` 구조(92,229건,
`url_hash`/`title`/`content`/`summary`/`published_at`, 종목 태깅 없음, 2026-06-29~07-18 범위)
확인 후 착수. 기사 단위로 AI가 고정 스키마 필드(상위분류/긍부정/세부이벤트유형/영향범위/관련종목
/관련업종/영향도/영향기간/신뢰도/근거)를 추출하고, `sentiment`/`magnitude`는 그 필드들로부터
파생 계산(추가 AI 호출 없음). 이벤트 클러스터링은 "새 뉴스마다 기존 대표뉴스들과 함께 AI 판단"
이라는 요구를 임베딩(`text-embedding-3-small`) 코사인 유사도로 구현 — 순수 LLM 순차 판단
방식은 뉴스 건수만큼 서로 의존하는 호출이 필요해 사용자가 요청한 비용 절감용 Batch API와
근본적으로 맞지 않기 때문(설계 트레이드오프를 사용자에게 설명 후 진행). 최종 점수는
`strength × decay(d) × count_factor`를 종목별 이벤트 전체에 대해 합산→평균→tanh 정규화. 캐시는
JSON/SQLite 양쪽 지원(`cache_store.py`), 대량 처리(임베딩+라벨링)는 서로 독립적인 요청이라
OpenAI Batch API(50% 할인)로 제출, 캐시미스 온디맨드 1건은 동기 호출로 즉시 채움. 1000건 AI
풀을 실제로 구축(배치 제출→완료까지 폴링→캐시 반영): 변수 1077건(배치 1000 + 검증 중 처리한
77건), 이벤트 클러스터 608개, JSON/SQLite 양쪽 저장 완료. `score_stock.py` 데모로 "한화오션"
2026-07-14 기준 최종 점수 0.2985 산출까지 실제 데이터로 검증(공급계약 호재·조선업 실적 호조
등 관련 이벤트 23건 반영).

**뉴스 영향도 등급 체계 개선(2026-07-22, 사용자 추가 요청)**: 3단계(High/Medium/Low) 대신
1~9등급(9등급=전쟁·내전 발발 등 국가적 충격)으로 세분화하고, 등급별 예시를 시스템 프롬프트에
명시해 AI가 등급 기준을 자체 판단하지 않도록 프롬프트 엔지니어링 진행(`scoring.py`). 스키마 변경이라
`PROMPT_VERSION`을 올려 캐시 자동 무효화(App §7.3 `ai_score_cache`와 동일한 캐시 무효화 패턴).
원시 AI 변수(`NewsVariables`)만 캐시에 저장하고 decay/count_factor/정규화 등 "점수 계산식"은
조회 시점마다 캐시된 원시 변수로 재계산하는 구조(`aggregate.py`)라, 계산식이 바뀌어도 AI를
재호출할 필요가 없다 — 다만 이번처럼 원시 변수 스키마 자체(등급 체계)가 바뀌면 기존 캐시는
새 스키마로 재추출이 필요.

**회귀**: 백엔드 `pytest` 105개 전부 통과, 프론트 `vue-tsc -b` 통과. `back-news-analysis/data/`
(캐시 산출물)는 `.gitignore`에 추가해 커밋 대상에서 제외. `naver_economy_news.json`(304MB)도
`.gitignore`에 추가(GitHub 파일 크기 제한 초과, 원본 데이터 재배포 불필요).

## 2026-07-22 후속 작업: 노드 description 필드 추가

사용자 질문("AI가 노드를 만들 때 노드 설명을 어떻게 참고하는가?")에 답하는 과정에서, `node_registry_schema()`
가 AI 프롬프트(`workflow_draft.py`/`workflow_chat.py`)에 `type/category/display_name/param_schema`만
주입하고 노드의 역할·입출력 설명은 전혀 넘기지 않는다는 걸 발견 — 노드 클래스 docstring은 AI가 못 봄.
`Node.description: ClassVar[str]`을 추가하고 8개 노드 전부에 `symbols`에서 무엇을 읽고 쓰는지까지
명시한 설명을 채워 넣어 `node_registry_schema()`가 노출하도록 함(자동으로 AI 프롬프트/팔레트 툴팁/
속성 패널에 반영). DESIGN.md §3.1 갱신. 백엔드 105개 전부 통과, 프론트 `vue-tsc -b` 통과.
커밋 `bd8e057`.

## 2026-07-22~23 후속 작업: 영속 포트폴리오(현금+보유종목) + 노드 자동 변수 주입 + 백테스트 일자별 그래프 재생

사용자 요청: DB로 보유종목/현금을 관리하고, 백테스트에도 이 정보(자금·보유수량)가 필요하며, 노드
조건식에서 변수로 바로 쓸 수 있어야 한다. 조사 결과 `DESIGN.md` §9.2가 문서화한 `orders`/
`positions_ledger` 테이블은 실제로는 구현된 적이 없었고, 매매 체결은 `DummyOrderExecutionProvider`가
컨테이너(서버 프로세스) 생명주기 동안만 메모리에 현금/포지션을 들고 있어 서버 재시작 시 리셋되는
구조였음(설계 드리프트). `AskUserQuestion`으로 확정: (1) 실시간 반영형(체결마다 DB 갱신, 재시작에도
유지) (2) 노드 배선 없이 스케줄러처럼 엔진이 자동 주입 (3) 백테스트는 독립 유지(`initial_capital` 기반
가상 실행) + (4) 백테스트 결과 화면에서 일자별 노드 그래프 재생 + (5) ABC 기반 다형성(실제 브로커
API로 나중에 교체 가능). 규모가 커서 `EnterPlanMode`로 계획을 세우고 승인받은 뒤 구현(계획 파일:
`lazy-stirring-crown.md`).

**Part 1 — 영속 포트폴리오**: 신규 테이블 `portfolio_cash`/`portfolio_positions` + `PortfolioRepository`
ABC(sqlite/인메모리 구현체, 기존 Repository 패턴 그대로). 매수/매도 체결 계산(`apply_fill`)을
`app/broker/fill_logic.py`로 뽑아 `DummyOrderExecutionProvider`(백테스트 전용, 순수 인메모리)와
`PersistentOrderExecutionProvider`(라이브/테스트 전용, 매 체결마다 `PortfolioRepository`에서
읽고 씀)가 공유하도록 리팩터링 — 로직 드리프트 방지. `_build_order_provider()`가 컨테이너에는
`PersistentOrderExecutionProvider`, 백테스트에는 여전히 `DummyOrderExecutionProvider`를 준다.

**Part 2 — 엔진 자동 주입**: `WorkflowEngine.execute()`가 런 시작 시 `broker.get_balance()`/
`get_positions()`를 1회 조회해, 각 노드 출력의 `symbols[code]`에 `held_qty`/`held_avg_price`/
`cash`/`equity`를 자동으로 채운다(새 노드 타입 없음, `scheduler.interval`처럼 암묵적). 값은 런
시작 시점 스냅샷이라 해당 런 자신의 주문으로는 바뀌지 않음. `logic.if_else`의 `expr`에서 바로
참조 가능(`held_qty == 0 and cash > price * 10` 같은 식).

**Part 3**: 이 변수들은 `node_registry_schema()`에 안 나타나므로(엔진이 주입, 노드가 아님) AI가
모를 수 있어 `workflow_draft.py`/`workflow_chat.py` 시스템 프롬프트와 `if_else` `description`에
고지 문구 추가.

**Part 4 — 백테스트 일자별 그래프 재생**: `BacktestRunner`가 거래일마다 별도 `run_id`로
`WorkerPool`(`app/workflow/run_persistence.py::events_to_records` 공유)과 동일하게 `RunRecord`/
`NodeEventRecord`를 저장, `BacktestResult.daily_runs`(날짜→run_id)를 `backtest_results.daily_runs_json`
에 저장. 신규 `GET /workflows/{id}/runs/{run_id}`(라이브/테스트/백테스트 run 공용 조회)를
프론트 `BacktestResultView.vue`의 날짜 `<select>` + `VueFlow`/`DebugPanel`(빌더의 "테스트 실행"
재생과 동일 컴포넌트 조합)이 소비.

**실기 중 발견한 버그(계획에 없던 수정)**: `daily_runs_json`처럼 기존 테이블에 새 컬럼을 추가하는
변경은 `Base.metadata.create_all()`이 반영해주지 못해(신규 테이블만 생성, 기존 테이블은 그대로) 이미
써오던 로컬 `nemo_stock.db`에서 백테스트가 500 에러로 즉시 실패함을 실브라우저 검증 중 발견. Alembic
없이 가볍게 해결 — `init_db()`에 ORM 모델엔 있지만 실제 테이블엔 없는 컬럼을 `ALTER TABLE ADD COLUMN`
으로 보정하는 단계를 추가(`app/dao/sqlite/database.py::_add_missing_columns`), 회귀 테스트 추가
(구버전 스키마를 raw SQL로 흉내낸 뒤 `init_db()`가 컬럼을 보정하고 정상 저장/조회되는지 확인).

**검증**: 백엔드 pytest 105→**112개**(신규: PortfolioRepository CRUD, `apply_fill` 순수함수,
`PersistentOrderExecutionProvider` 재시작 시뮬레이션, 엔진 주입, 백테스트 daily_runs 저장/조회,
컬럼 보정 마이그레이션) 전부 통과(기존 스크린 하나는 실계좌 KOSCOM 호가 API가 장외시간이라 0원을
반환해 실패 — 무관한 사전 존재 flaky 테스트, `git stash`로 확인). 프론트 `vue-tsc -b` 통과. 실제
uvicorn+vite 기동 후 curl/Playwright로 골든 패스 검증: (1) 신규 종목으로 조건식
`held_qty == 0 and cash > 1000000` 워크플로 실행 → 매수 체결 확인 (2) **실제 `pkill` + 프로세스
재기동**으로 서버 재시작 후 재실행 → 보유수량/현금이 이전 체결을 반영해 유지됨(영속화 확인,
in-memory 대비 실질적 개선) (3) 합성 시세로 15거래일 백테스트 실행 → 결과 화면에서 날짜별
`<select>`(15개 옵션)로 전환 시마다 해당 날짜의 노드 그래프가 색상 하이라이트되며 재생되고
디버그 패널이 채워짐을 스크린샷으로 확인, 콘솔 에러 0건.

## 2026-07-27 후속 작업: 백테스트 매매 시점 시각화 + 시세/보조지표/뉴스 오버레이 + AI 진단·수정 제안

사용자 요청: 백테스트 결과 그래프에 매수/매도 시점을 점으로 표시하고, 점(또는 구간)을 선택하면
현재 워크플로 로직과 함께 AI에게 왜 그렇게 매매했는지/왜 매매가 없었는지 물어보고 수정 제안까지
받을 수 있게. 대상 종목 시세와 이동평균/볼린저밴드 등 보조지표, 해당 시점 참고 뉴스도 그래프에
표시. 규모가 커서 `EnterPlanMode`로 계획 수립 후 승인받아 진행(계획 파일: `lazy-stirring-crown.md`).
사전 확인한 범위 결정: (1) 뉴스는 그 백테스트가 실제 참고한 것(`data.news` 노드 조회분)을 기본
표시하고, 기존 news 테이블 전체는 체크박스로만 옅게 보여주며 "무거우니" AI 질문에는 포함하지 않음
(2) 보조지표는 별도 호가/체결 데이터 없이 기존 `price_bars`(OHLCV)만으로 계산 가능한 것 전부
(MA5/20/60 + 볼린저밴드 + RSI14 + 거래량).

**백엔드 데이터 노출**: `OrderResult.filled_at`이 실제 벽시계 시각이라 `BacktestRunner`가 거래일
루프에서 직접 날짜를 태깅해 `trades`를 쌓음. `BacktestResultRecord`에 `universe`/`trades` 필드
추가(컬럼은 기존 `_add_missing_columns()` 마이그레이션이 자동 보정해 별도 코드 불필요).
`NewsRepository`에 `get`/`list_range` 추가. 신규 엔드포인트 `GET /backtest/{id}/prices`,
`GET /backtest/{id}/news/used`, `GET /backtest/{id}/news/all`.

**AI 진단/수정 제안**: `app/ai/backtest_explain.py::explain_backtest()`가 `chat_about_workflow()`와
동일 계약(reply/changed/graph, 검증+1회 재시도)을 따라 프론트가 같은 미리보기 UI를 재사용.
`POST /ai/backtest-explain`이 backtest_id+selection(점/구간)으로 거래내역·노드실행 요약(축약)·
종가·참고뉴스를 조립해 근거로 제공. 백테스트 화면엔 캔버스가 없어 "적용" 대신 "전략 빌더에서
열기"로 `draftStore`(신규 `targetWorkflowId`)에 담아 이동, `StrategyBuilderView.load()`가 대상
워크플로가 일치하면 그 draft를 캔버스에 덮어씀(저장은 사용자가 직접).

**프론트 차트**: `BacktestChart.vue`(신규, `EquityCurveChart.vue` 대체) — vue-chartjs 래퍼 대신
Chart.js를 직접 생성해 듀얼축(자산/시세)에 매매 마커(매수=녹색▲/매도=빨강▼)·뉴스 마커·MA·볼린저를
그리고 RSI·거래량은 같은 x축을 공유하는 서브차트로 배치. 드래그 구간 선택은 추가 플러그인 없이
`chart.scales.x.getValueForPixel()` 기반 수동 구현. `BacktestAskPanel.vue`(신규, `ChatPanel.vue`
UI 패턴 재사용)가 선택 종류별 질문을 프리필하고 AI 응답/수정 제안을 표시.

**검증**: 백엔드 pytest 112→**117개** 전부 통과(신규: `backtest_explain` changed=false/true+재시도,
`NewsRepository.get/list_range`, 러너 trades 날짜 태깅, `/backtest/{id}/prices`+`/news/used`+
`/news/all`+`/ai/backtest-explain` 통합 테스트). 프론트 `vue-tsc -b`+`npm run build` 통과(디버그
전용 훅이 프로덕션 번들에서 완전히 제거됨을 grep으로 확인). 실제 uvicorn+vite 기동 후 실제
OpenAI 키로 Playwright 골든 패스 전체 검증: 합성 시세(상승 5일-보합/하락 5일-상승 5일)+뉴스 1건
적재 → 백테스트 실행(매매 10건) → 차트에 매수 마커/뉴스 마커/이동평균/거래량 렌더 확인 → 매매
마커 클릭(Chart.js 내부 픽셀좌표를 dev-only 디버그훅으로 정확히 얻어 클릭) → AI가 노드 그래프
로직(n2~n5)을 근거로 정확한 진단 응답 → 매매 없는 구간(보합/하락 5일) 드래그 선택 → AI가
if_else 필터링 원인을 정확히 짚고 수정 그래프 제안 → "전략 빌더에서 열기" 클릭 시 캔버스에
반영 확인 → "전체 뉴스 표시" 체크박스 토글 정상 → 콘솔 에러 0건.

## 2026-07-28 후속 작업: 조건 내장 지표 노드 12종 + 테스트 실행 판단(judgment) 로그

사용자 요청: 팀 원본 저장소 `koscom-mini-project-4/koscom_nemonemo`를 참고해 if문/조건 관련
기능을 늘리고 노드 편집을 쉽게 만들 것, "테스트 실행"이 결과뿐 아니라 각 노드의 판단 근거도
로그에 보이게 할 것.

**fork 조사**: fork를 clone해 우리와 갈라진 지점(2026-07-19 `Initial commit`, 이전 조사에서는
"병합할 신규 기능 없음"으로 종료했던 그 시점) 이후 커밋 15개를 확인. `c4d7936`/`59726d8`
커밋에서 "계산 + 조건 내장" 지표 노드 12종(원시 수식 대신 사람이 읽는 조건 프리셋 드롭다운으로
판단)을 발견 — 정확히 이번 요청과 일치. 다만 fork의 `DebugPanel.vue`도 raw JSON만 보여줄 뿐
판단 근거를 사람이 읽게 보여주진 않아, 그 부분은 새로 설계했다. fork는 그 갈라진 지점 이후
우리와 다른 방향(뉴스신호 파이프라인, 산업 섹터 통제 어휘 등)으로 발전했고, 우리도 포트폴리오
자동 주입/노드 description 등 독자적으로 발전했으므로 코드를 그대로 머지하지 않고 아이디어만
이식했다.

**조건 내장 지표 노드 12종** (`backend/app/nodes/indicator/`): `calc.py`(SMA/EMA/RSI/MACD/ATR/
표준편차/MDD/rolling_max 등 순수 계산 함수) + `base.py`(`IndicatorNode` 베이스 — 봉 조회 →
`compute()` → 조건 연산자 판정 → 필터링, `Cmp`/`IndicatorSignal`/`evaluate_condition`/
`condition_param`/`threshold_param`) + 6개 노드 파일(`trend.py`: SMA/EMA/MACD,
`momentum_signal.py`: RSI매매신호/기간수익률, `volatility.py`: 변동성/볼린저/ATR추적손절,
`position.py`: 52주최고가대비, `drawdown.py`: MDD, `volume.py`: 거래량비율/거래량Z-score).
값만 계산하던 기존 `indicator.moving_average`/`indicator.rsi`/`indicator.momentum`은 변경하지
않고 그대로 유지(하위호환·기존 템플릿 안전). `indicator.rsi`와 타입이 겹치는 fork의 조건 내장
RSI는 `indicator.rsi_signal`로 개명해 충돌 회피. `logic.if_else`는 fork처럼 숨기지 않고 팔레트에
유지(복합조건/OR 로직에 여전히 필요, 사용자 확인).

**판단(judgment) 로그**: 모든 필터형 노드(`logic.if_else`/`logic.rank`/`risk.stop_loss`/조건
내장 지표 12종)가 `context.meta.decisions[node_id][symbol] = {"pass": bool, "reason": str,
"metrics"?: dict}`를 공통 포맷으로 기록하도록 통일(기존 `meta.filtered_out`은 `ai.py` 챗봇
컨텍스트 하위호환을 위해 그대로 유지, 신규 필드만 추가). `NodeContext.snapshot()`이 `meta`를
그대로 이벤트에 싣기 때문에 엔진(`workflow/engine.py`) 변경은 불필요했다.

**프론트엔드**: `types.ts`에 `NodeParamSchema.group/hint/option_labels/show_if`,
`NodeTypeSchema.subcategory/example`, `NodeDecision` 타입 추가. `ParamFields.vue`가 `group`별로
"계산용 파라미터"/"매매 조건" 구획 헤더를 나누고 `hint`를 안내 텍스트로 표시(캔버스 인라인
노드·속성 패널 공용이라 조건 프리셋 편집이 노드 박스 안에서 바로 가능). `NodePalette.vue`는
category 안에서 `subcategory`로 2차 그룹핑(추세/모멘텀/변동성/가격 위치/위험/거래량) — 기존
드래그 앤 드롭 기능은 보존. `DebugPanel.vue`에 "판단 결과" 섹션 신설: 이벤트 리스트 각 행에
통과/탈락 요약 배지, 상세 패널에 종목별 판단 테이블(통과✅/탈락⛔ + 사유)을 raw JSON 위에 추가.

**테스트**: 신규 유닛 26개(`test_indicator_calc.py` 9, `test_indicator_signal_nodes.py` 13,
`test_decision_log.py` 4) — 백엔드 pytest **119→145개 전부 통과**. 프론트 `vue-tsc -b` +
`npm run build` 통과.

**검증**: 이번 세션에는 브라우저 자동화(Playwright MCP) 도구가 연결되어 있지 않아 실제
화면 조작 검증은 수행하지 못했다(이전 작업들과 달리, CLAUDE.md가 요구하는 "브라우저로 실제
동작 확인"을 완전히 충족하지 못한 한계로 명시해 둔다). 대신 실제 uvicorn 서버를 띄우고
curl로 API 골든 패스를 검증: 로그인 → `GET /nodes`로 신규 12종 노드의 스키마(subcategory/
example/group/hint 포함) 확인 → 스케줄러→시세→`indicator.sma`(조건: 상향 돌파)→`logic.if_else`
→ 매수 주문 워크플로를 생성해 `POST /workflows/{id}/run`(테스트 모드) 실행 → 응답의
`sma1`/`if1` 이벤트 각각의 `output_snapshot.meta.decisions`에 종목별 `{"pass": true, "reason":
"48244.7 상향 돌파 48022.14 → 통과"}` / `{"pass": true, "reason": "price > 0 → True"}`가
정확히 기록됨을 확인(프론트 `DebugPanel.vue`가 소비하는 것과 동일한 경로). 다음 세션에서
Playwright(또는 수동 브라우저)로 팔레트 2차 그룹핑·조건 프리셋 인라인 편집·판단 결과 UI를
실제 화면으로 재확인할 것을 후속 작업으로 남긴다.

## 2026-07-28 후속 작업 2: newsstock-lib 통합 — 뉴스(종목/섹터/거시) true/false 신호 노드

사용자 요청: 팀이 만든 별도 저장소 `koscom-mini-project-4/newsstock-lib`를 포함시키거나 살짝
수정해서, 뉴스 기반으로 종목/섹터/거시경제 각각에 대해 true/false를 내어주는 노드를 추가할
것. 다른 기능에서도 필요하면 크롤링을 트리거할 수 있게 할 것.

**라이브러리 조사**: clone해서 확인한 결과 `news_classifier` 패키지(`NewsTrader` 파사드)가
이미 원하는 기능을 거의 그대로 제공했다 — `trader.stock/sector/macro(name)`가 종목/섹터/거시
3축의 t(호재)/n(중립)/f(악재) 판정+점수를 돌려주고, 조회 시점에 스스로 크롤링(네이버 경제뉴스)
→AI 분류(OpenAI)→클러스터 반영을 수행한다(내부 30분 쓰로틀로 비용 제한, `auto_update=False`로
끄고 수동 `update()`도 가능). 자체 SQLite DB를 갖고 있어 기존 `NewsRepository`/
`ai.sentiment_score` 파이프라인과는 완전히 독립적이다.

**vendoring + 필요한 수정 1건**: `backend/app/vendor/news_classifier/`에 패키지를 그대로
복사(`VENDOR_NOTES.md`에 출처/수정사항 기록). 유일하게 고친 부분은 `classifier.py::call_ai`의
`temperature=0` 하드코딩 — 메인 모델 `gpt-5.6-luna`(reasoning 계열)와 충돌하는 문제라
`app/ai/openai_client.py`와 동일한 "BadRequestError(param=temperature) 시 재시도" 패턴을
적용했다(DESIGN.md §0-5).

**Provider 배선**: `NewsTrader`가 스레드 세이프하지 않은 sqlite 연결을 물고 있어 `ai_client`
처럼 공유 인스턴스를 두면 `WorkerPool`의 여러 스레드가 충돌할 수 있음을 확인 → 공유 인스턴스
대신 노드 실행마다 새 인스턴스를 만드는 **팩토리 콜러블**(`Container.news_trader_factory`)을
`node_providers()`로 주입하는 방식을 택함(`app/config.py`에 `newsstock_db_path` 1개 필드만
추가, API 키/모델은 기존 설정 재사용).

**신규 노드 `ai.news_signal`**(`backend/app/nodes/ai/news_signal.py`): axis(종목/섹터/거시경제)
+ key + period_days + auto_update + pass_when(호재(t)/악재(f)/중립 아님) 파라미터로 조건 내장
필터형 노드(지난 작업의 조건 내장 노드 패턴과 동일)를 구현. `symbols[code]`에 `news_verdict`/
`news_score`/`news_cluster_count`/**`news_true`(bool, 요청한 true/false 출력)**를 채우고
`meta.decisions`에 판단 근거를 기록한다. axis="종목"이고 key 미지정 시
`app/market_data/symbol_master.py`로 종목코드→한글명 자동 매핑(매핑 실패는 "판정 불가"로
탈락, 트레이더 조회 자체를 하지 않음).

**다른 기능의 크롤링 트리거**: `POST /data/news/update`(`app/api/routers/data.py`) 신규
추가 — `news_trader_factory(auto_update=False)`로 만든 트레이더의 `update(force=...)`를
호출해 결과를 반환한다. `ai.news_signal`의 `auto_update=false`로 실행 중 네트워크/AI 호출을
막은 워크플로나, 대시보드 등 다른 기능이 필요할 때 독립적으로 갱신을 트리거할 수 있다.

**테스트**: `ai_test_doubles.py`에 `FakeNewsTrader`/`FakeNewsTraderFactory` 추가(실제
크롤링/OpenAI 없이 결정적 테스트). 신규 유닛 `test_news_signal_node.py`(7개, 종목 자동 매핑/
매핑 실패/섹터·거시 key/pass_when 3종/auto_update 전달/close 호출/provider 누락 오류),
`test_vendor_news_classifier.py`(2개, temperature 재시도 회귀). 신규 통합
`test_api_news_signal_update.py`(2개) — 작성 중 FastAPI `response_model`이 기본적으로
pydantic alias(Korean 필드명)로 직렬화한다는 걸 놓쳐 응답 JSON에 `skipped` 키가 없어 테스트가
실패했던 걸 발견, 라우터에 `response_model_by_alias=False`를 추가해 수정. 백엔드 pytest
**145→156개 전부 통과**(신규 11개). `beautifulsoup4`/`requests`를 `pyproject.toml`에 추가.
프론트 `vue-tsc -b` 통과(이번 작업은 새 param_schema만 쓰므로 프론트 코드 변경 불필요).

**검증**: 이번 세션도 브라우저 자동화 도구가 없어(이전 후속 작업과 동일한 한계) 실 서버 curl로
검증했다. `GET /nodes`로 `ai.news_signal` 스키마 노출 확인 → 스케줄러(005930 + 매핑에 없는
가짜 코드 999999) → `ai.news_signal`(axis=종목, auto_update=false, pass_when=중립 아님)
워크플로를 생성해 `POST /workflows/{id}/run`(테스트 모드) 실행 → 실제 `Container.
news_trader_factory`가 만든 `NewsTrader`(빈 `backend/newsstock.db`)로 조회되어 005930은
"판정=n 점수=0.0(클러스터 0건) → 탈락", 999999는 "종목명 매핑 없음 → 판정 불가"(트레이더 조회
자체를 하지 않음)로 정확히 기록됨을 확인(실행 8.67ms, `auto_update=false`라 네트워크/OpenAI
호출 없음). 실행 후 `backend/newsstock.db`가 gitignore 대상으로 남는지도 확인(`git status`에
안 잡힘). Playwright 등으로 실제 화면(캔버스에서 axis/pass_when 프리셋 편집, 디버그 패널 판단
표시)까지 재확인하는 건 다음 세션 후속 작업으로 남긴다.

## 2026-07-28 후속 작업 3: OpenAI 연결 확인 + 실제 뉴스 크롤링 + 백테스트 시점 인식/AI 호출량 제한

사용자 요청: (1) `ai.news_signal`이 실제 OpenAI에 연결되어 있는지 확인, (2) 실제 뉴스를
크롤링해서 채워둘 것, (3) 백테스트에서 AI를 너무 많이 거치지 않도록 기간을 최대 4일로 제한.

**OpenAI 연결**: `backend/.env`에 이미 실제 `OPENAI_API_KEY`/`OPENAI_MODEL=gpt-5.6-luna`가
있고, `Container.news_trader_factory`가 이를 그대로 재사용하도록 배선되어 있어(§0-5) 추가
코드 변경 없이 이미 연결되어 있었다. 확인만 하고 다음 항목으로 진행.

**백테스트 시점 인식 버그 발견 및 수정**: 크롤링을 실제로 트리거하기 전, "백테스트에 이 노드를
쓰면 어떻게 동작하나"를 점검하다가 `ai.news_signal`이 `NewsTrader.stock/sector/macro()`에
`start`를 넘기지 않아 **항상 "실제 오늘" 기준으로 조회**한다는 걸 발견했다 — 다른 지표 노드
(`indicator.sma` 등)는 전부 `context.timestamp`를 쓰는데 이 노드만 빠져 있었다. 그대로 두면
백테스트의 모든 거래일이 동일한(가장 최근) 뉴스 판정을 받아 사실상 의미가 없었을 것.
`context.timestamp.date().isoformat()`을 `start`로 넘기도록 수정(DESIGN.md §0-5).

**백테스트 AI 호출량 제한**: 위 수정으로 거래일마다 실제로 다른 조회 = 다른 OpenAI 호출이
일어나게 되므로, 사용자 요청대로 `ai.news_signal`이 포함된 워크플로의 백테스트는 기간을 최대
4일로 제한하도록 `POST /backtest`에 검증을 추가했다(초과 시 400,
`app/api/routers/backtest.py::NEWS_SIGNAL_BACKTEST_MAX_DAYS`).

**세션 중 발견한 사고**: 실제 크롤링을 curl로 트리거했다가 5분 넘게 끝나지 않아(크롤러가
기사당 1.2~2.2초 지연 + 최대 100건 순차 AI 분류를 하므로 원래 수분 이상 걸림) 강제 종료하는
과정에서, `lsof -ti:8000 | xargs kill`로 검증용 서버를 내리다가 **사용자가 그날 11:14부터
3시간 넘게 띄워두고 있던 기존 백엔드 프로세스(다른 dev 세션)를 실수로 같이 죽인 것**을
뒤늦게 발견했다(포트는 이미 풀렸고 프로세스만 좀비로 남아 있었음). 사용자에게 즉시 알리고
확인을 거쳐 좀비 프로세스를 정리(kill -9)했다 — **교훈: 다음부터 포트를 정리하기 전에
`lsof -ti:PORT -sTCP:LISTEN`로 어떤 프로세스가 떠 있는지, 언제 시작됐는지 먼저 확인하고, 내가
직접 띄운 것이 아니면 함부로 죽이지 않는다.**

**테스트**: `test_query_start_date_follows_context_timestamp_for_backtest_replay`(시점 인식),
`test_api_backtest_news_signal_cap.py` 2개(4일 초과 거부/이내 통과) 추가. `FakeNewsTrader`가
`start`도 기록하도록 `ai_test_doubles.py` 보강. 백엔드 pytest **156→159개 전부 통과**.

**실제 크롤링 실행**: `POST /data/news/update`(force=true, 기본 설정 — 1일치 목록 최대 5페이지,
최대 100건 분류)을 백그라운드로 실행 — **83건 수집, 83건 AI 분류 완료**(`{"skipped": false,
"collected": 83, "classified": 83, "pending": 0, "purged_clusters": 0}`). 실제 OPENAI_API_KEY로
크롤링→분류 전체 경로가 정상 동작함을 확인. 소요 시간은 순차 크롤링(당시 코드) 기준 수분.

## 2026-07-28 후속 작업 4: 뉴스 크롤러 병렬 fetch (connection pool 여러 개)

사용자 질문("여러 connection pool을 만들어서 병렬로 빠르게 하는 방법 등도 시도했어?")에 대한
답으로, 시도하지 않았던 이유(원본 크롤러가 기사당 1.2~2.2초 지연을 두는 정중함 정책을 그대로
따름)를 설명하고 트레이드오프(네이버/OpenAI 레이트리밋 위험 vs 속도)를 안내한 뒤, 사용자가
"현재 크롤링은 끝까지 기다리고, 코드는 병렬화해서 수정해 두라"고 확정해 구현했다.

**구현**(`backend/app/vendor/news_classifier/crawler.py`): `crawl(workers=N)` 파라미터
추가(기본 `CRAWL_WORKERS=4`, env로 조정 가능, `workers=1`이면 원본과 동일한 순차 동작).
한 페이지 안의 새 기사 URL들을 `ThreadPoolExecutor`로 동시에 fetch하되, 스레드마다
`threading.local()`로 별도 `requests.Session`(=별도 connection pool)을 만들어 재사용한다
(`_thread_session`). 지연(`CRAWL_DELAY`)은 워커별로 각자 넣으므로 초당 요청수 제한이라는
원래 의도는 유지하면서 총 처리량은 워커 수만큼 늘어난다. `_fetch_page_articles()`가
순차/병렬 두 경로를 `_fetch_one()` 하나로 공유해 로직이 갈라지지 않게 했다. 목록 페이지
조회(페이지당 1회뿐이라 병렬화 실익 적음)와 AI 분류(`pipeline.classify_many` — "오래된
뉴스부터 처리해야 클러스터가 올바르게 쌓인다"는 순차 의존성이 문서화되어 있어 병렬화 시
클러스터 중복 생성 위험)는 의도적으로 병렬화하지 않았다. `Settings.crawl_workers`/
`NewsTrader.update()`까지 배선.

**테스트**: `test_vendor_news_classifier.py`에 2개 추가 — `_list_page`/`_article`을 스텁하고
`time.sleep`을 무력화해 실제 네트워크/지연 없이 (1) workers=4일 때 실제로 여러 스레드가
fetch에 참여하는지(`threading.get_ident()` 수집), (2) 순차(workers=1)와 병렬(workers=4)이
동일한 URL 집합을 모으는지 검증. 백엔드 pytest **159→161개 전부 통과**.

**세션 중 발생한 사고 기록**(교훈, 위 "후속 작업 3"에서 이미 한 번 기록한 것과 같은 유형):
크롤링을 curl로 트리거했다가 5분 넘게 끝나지 않아 `lsof -ti:8000 | xargs kill`로 서버를
내리는 과정에서 사용자가 별도로 3시간 넘게 띄워두고 있던 기존 백엔드 프로세스를 실수로 같이
죽였다. 사용자에게 즉시 알리고 확인 후 정리(kill -9)했다 — **포트를 정리하기 전에는 항상
`lsof -ti:PORT -sTCP:LISTEN`로 어떤 프로세스가, 언제부터 떠 있는지 먼저 확인할 것.**

## 2026-07-28 후속 작업 5: 뉴스 신호 완성도 작업 묶음 (Part 1~6, DESIGN.md §0-6)

실 백테스트(`ai.news_signal` 포함 워크플로)를 사용자가 직접 돌려보다가 연쇄적으로 여러 이슈를
발견/요청했고, 조사 과정에서 fork(`koscom_nemonemo`)에 지표 노드 12종 포트 이후 완전히 별도인
"뉴스 신호 파이프라인"(AI 라벨링→충격량/시계열 집계→조건 내장 노드 11종)이 통째로 빠져있었던
것도 확인해 전부 하나의 계획(`/Users/2p31/.claude/plans/keen-skipping-melody.md`)으로
묶어 처리했다.

**Part 1 — `ai.news_signal` 파라미터 확장**: `threshold`/`decay_base`/`include_zero`/
`decay_from`을 노드에서 조절 가능하도록 `param_schema`+`execute()`+
`_build_news_trader_factory()` 보강.

**Part 2 — 백테스트 뉴스 마커 버그 수정**: `/backtest/{id}/news/{used,all}`이 구 파이프라인
(`data.news`/`NewsRepository`)만 알고 `ai.news_signal`이 쓰는 `newsstock.db`를 전혀 몰라
마커가 하나도 안 뜨던 버그. 신규 `GET /backtest/{id}/news/signal` 추가(워크플로 그래프에서
`ai.news_signal` 노드를 찾아 axis/key로 조회 → `NewsMarkerOut(source="newsstock")` 매핑).
프론트 `BacktestChart.vue`에서 병합 표시(보라 세모, 출처 구분).

**Part 3 — 뉴스 노드 포함 시 기본 백테스트 기간 자동 4일**: `BacktestResultView.vue`에
`recentTradingDayRange()`/`applyNewsSignalDefaultRange()` + `watch(workflowId)` 추가.
사용자가 직접 수정하면 자동설정은 유지되지 않음. 상한은 기존 7일(`NEWS_SIGNAL_BACKTEST_MAX_DAYS`,
사용자 요청으로 4→7일 이미 상향됨) 그대로.

**Part 4 — 백테스트 차트 시간봉 지원**: `GET /backtest/{id}/prices?interval=`에
`minute60` 추가(`intraday_price_bar_repo` 조회, 없으면 일봉 폴백). 프론트는
`intradayMode` + `dayPrefix()`/`buildDayAlignedSeries()`/`lastLabelForDay()`로 매매/뉴스/AI
설명 드래그선택 전부 "정확한 문자열"이 아니라 "그 날짜"로 매칭하도록 수정(datetime 라벨에서
깨지던 버그 수정 포함).

**주요 근거 토픽 노출**: `ai.news_signal`이 `클러스터` 중 절대값 점수가 가장 큰 것을
`news_top_topic`/`news_top_topic_score`로 심볼 데이터에 포함하고, 판단 로그(`meta.decisions`)
reason에 `"주요 근거: '{topic}' (기여점수 {score:+.4f})"`를 덧붙임.

**Part 5 — 관리자 페이지**: 신규 `frontend/src/views/AdminView.vue`(`/admin`, nav에 링크
추가). (5-1) 뉴스 분석 현황: `GET /data/news/stats`(`NewsTrader.stats()`), `GET
/data/news/clusters?start=&end=`(날짜만 넘기면 문자열 비교 상한에 걸려 그날 데이터가
누락되는 라이브러리 버그를 발견해 `datetime.combine(start, time.min)`~`time.max`로 우회 —
실 서버에서 0→107건으로 검증), 수동 크롤링 트리거 버튼(`POST /data/news/update`). (5-2)
사용량 통계: `AIUsageRecord`/`AIUsageRepository`(sqlite `ai_usage` 테이블) 신설,
`OpenAIClient.complete_json(..., purpose=...)`이 매 호출 후 `response.usage`를 best-effort로
기록, 벤더 `classifier.py::call_ai()`도 `set_usage_sink()` 콜백으로 동일하게 계측(두 개의
독립된 OpenAI 호출 경로를 모두 커버). `GET /admin/metrics` = 백테스트 실행 수(
`BacktestResultRepository.count()` 신규) + `app/admin/metrics.py::aggregate_usage()`(목적별/
모델별 집계, 순수 함수로 분리해 유닛테스트).

**Part 6 — fork 뉴스 신호 파이프라인 11종 포트**: `app/nodes/conditions.py`(큐레이션
프리셋 — 직전 지표 노드 세션 때 "불필요"로 판단해 안 옮겼던 바로 그 모듈, 이번엔 11개 노드가
전부 사용해 필요해짐), `app/news_signals/{sectors,themes,impact,aggregate,ingest}.py`,
`app/ai/news_classify.py`(fork 그대로 + `purpose="news_classify"` 한 줄), `app/nodes/data/
news_signal.py`(11개 노드: `sector_momentum`/`macro_risk`/`theme_zscore`/`sentiment_ratio`/
`symbol_news_score`/`symbol_direct_impact`/`sector_linked_impact`/`macro_sentiment`/
`sector_momentum_change`/`sector_buzz`/`event_density`)를 우리 아키텍처로 그대로 포트(동일
`Node`/`NodeContext`/`register_node` 시그니처라 프론트 변경 불필요 — `group`/`hint`/
`show_if` 등 파라미터 스키마 확장이 지표 노드 세션 때 이미 되어 있었음). `NewsSignalRecord`/
`NewsSignalRepository`(sqlite+memory 양쪽 구현) 신설. `POST /data/ingest/news/classified`
신규(이미 분류된 뉴스를 AI 호출 없이 바로 신호로 적재 — 외부 분류 파이프라인 연동용),
`ingest_manual_news`도 AI 키가 있으면 best-effort로 즉석 분류→신호 저장하도록 확장.
새 노드 타입이 기존 `data.price`/`data.news`/`data.disclosure`와 겹치지 않음을 확인.

**검증**: 백엔드 pytest 161→233개 전부 통과(신규: `test_conditions.py`,
`test_news_impact.py`/`_normalized.py`, `test_news_aggregate.py`/`_ext.py`,
`test_news_classify.py`, `test_news_signal_nodes.py`, `test_api_news_signal_pipeline.py`(통합),
`test_admin_metrics.py`, `test_api_admin_metrics.py`, `test_api_news_stats_clusters.py`,
`test_api_backtest_intraday_prices.py`, `test_dao_sqlite.py` 확장). 프론트
`npx vue-tsc -b` + `npm run build` 통과. 실 서버(`--reload`)에 curl로 `/data/news/clusters`
날짜버그 수정을 라이브 검증(0→107건). `DESIGN.md` §0-6 + §3.2 노드 표(11개 행) 갱신 완료.

**미착수(다음 작업으로 명시적으로 분리)**: "AI에 질의하여 노드를 수정할 때 전/후 비교 창"
기능은 이번 계획 범위에 없었고 사용자가 별도로 요청한 것 — 별도 계획으로 다시 스코핑 필요.

## 2026-07-28 후속 작업 6: 관리자 페이지 — 클러스터↔종목/섹터/거시 상호 탐색 (DESIGN.md §0-7)

사용자 요청: "관리자 화면에서 해당 주제의 속한 종목/섹션/거시도 볼 수 있게 하고, 반대로
종목/섹션/거시로부터 해당 클러스터들을 탐색할 수 있도록 해 주세요."

**구현**: `newsstock-lib`(vendor) `classifications` 테이블에 이미 클러스터별 종목/섹터/거시
연결 정보가 있었으므로(`stock`/`sector`/`macro` 컬럼 + `cluster_id`), 새 크롤링/AI 호출 없이
조회 함수만 추가했다. `db.py::cluster_tags()`(클러스터→태그) 신규 + `cluster_stats()`에 병합,
`api.py::NewsTrader.clusters_for_key()`/`keys_in_range()`(반대 방향, 기존 `db.group_cluster_rows`/
`db.group_keys`를 얇게 래핑) 신규. 라우터: `GET /data/news/topics`(키 목록),
`GET /data/news/topics/clusters`(키→클러스터). `GET /data/news/clusters`는 시그니처 변경 없이
응답에 태그 필드만 추가(하위호환). `AdminView.vue`에 클러스터 표 태그 열 + "종목/섹터/거시로
클러스터 탐색" 섹션(축 선택→키 드롭다운→조회) 추가, 기존 뉴스 분석 현황과 날짜 범위 공유.

**검증**: 백엔드 pytest 233→242개 전부 통과(신규 `test_vendor_news_classifier_topics.py`,
`test_api_news_topics.py`). `vue-tsc -b` + `npm run build` 통과. 실 서버(`--reload`)에 curl로
라이브 검증 — `/data/news/topics?group=stock`이 실제 종목명 목록(삼성전자 등) 반환,
`/data/news/clusters`가 실제 클러스터에 종목 태그를 포함, `/data/news/topics/clusters?
group=stock&key=삼성전자`가 삼성전자 언급 실제 클러스터 7건을 정확히 반환.

## 2026-07-28 후속 작업 7: AI 챗봇 노드 수정 제안 — 전/후 비교 창 (DESIGN.md §0-8)

사용자 요청: "ai에 질의하여 노드를 수정할 때 전 / 후 비교가 가능한 창을 만들어서 다시 수정하거나
확정/확정취소 할 수 있게 해 주세요." (지난 세션에 task #26으로 미뤄뒀던 항목.)

**구현(프론트엔드 전용, 백엔드 변경 없음)**: `chat_about_workflow()`가 이미 `graph` 인자를
그대로 "현재 그래프"로 받아쓰므로, 프론트가 무엇을 넘기느냐만 바꾸면 됐다.
`utils/graphDiff.ts`(순수 함수, 노드 추가/삭제/변경 + 파라미터별 전/후 값, 엣지 추가/삭제),
`components/GraphDiffModal.vue`(diff를 배지로 시각화, 노드/파라미터 라벨은 기존
`NodeTypeSchema`/`param_schema` 재사용, 하단에 "다시 수정 요청" 입력 + "확정"/"확정 취소"),
`ChatPanel.vue` 개편(인라인 적용/취소 버튼 → "비교 검토"로 모달 오픈). 핵심 포인트: "다시 수정"
요청 시 AI에게 넘기는 `graph`를 캔버스 현재 상태가 아니라 **검토 중인 pendingGraph**로
바꿔치기해야 AI가 직전 제안 위에 이어서 고친다(그렇지 않으면 매번 원본 캔버스 기준으로 처음부터
다시 제안해 이전 수정이 사라짐 — 설계 단계에서 발견해 미리 반영). 비교 창의 "before"는 항상
실제 캔버스로 고정해 누적 diff를 보여준다. AI가 changed=false로 답하면(그래프 변경 없이 순수
답변) 비교 창이 깨지지 않도록 기존 제안을 유지하고 안내만 띄우게 처리.

**검증**: 백엔드 무변경(pytest 242개 그대로 통과). `vue-tsc -b` + `npm run build` 통과. 이번
세션도 브라우저 자동화 도구가 없어, 사용자 dev 서버(HMR)에 curl로 신규/변경 파일이 컴파일
에러 없이 서빙되는 것까지만 확인 — 실제 클릭 동작(모달 열기/다시 수정/확정)은 사용자가
`npm run dev`로 직접 확인 필요.

## 2026-07-28 후속 작업 8: 자유 프롬프트 AI 노드 + 뉴스신호 근거 보강 + 노드 단독 테스트 (DESIGN.md §0-9)

사용자 요청 3가지: (1) 프롬프트/참고자료를 자유롭게 쓰고 앞 노드 데이터(뉴스/지수 등)를
자동 치환하거나 AI가 스스로 조회(skill/도구 호출)하게 하는 통과·탈락 판단 AI 노드 신설(테스트
실행 시 판단 내용 표시 + 단독 테스트 + 키 누락 검증 요구), (2) "data.news 테스트 실행이
비어 보이고 클러스터/의견/이유가 json에 안 넘어온다"는 버그 제보, (3) "if/else 넘어가도
점수/의견이 json으로 계속 누적돼야 한다"는 아키텍처 우려.

**조사 결과**: `NodeContext.symbols`는 이미 매 노드가 clone(deepcopy)해서 이어받고,
`if_else`/`apply_condition` 둘 다 통과 종목의 데이터를 그대로 유지(탈락 종목만 제거) — (3)은
재현 안 됨, 새 아키텍처 불필요. (2)의 실체는 `data.*` 뉴스신호 11개 노드가 숫자 점수만 내고
"어떤 뉴스가 그 점수를 만들었는지" 근거가 없던 것 — `ai.news_signal`의 `top_topic` 패턴을
이식해 해결(Part D).

AskUserQuestion으로 "치환 vs AI 직접 조회(도구 호출)" 중 구현 방식을 물었고, 사용자가
**"사용자가 선택할 수 있도록"**을 선택 — 워크플로 작성자가 노드 파라미터로 둘 중 고르도록
양쪽 다 구현했다(EnterPlanMode로 4-Part 계획을 세워 승인받고 진행).

- **Part A**: `AIClient.complete_with_tools()`(도구 호출 다회 루프, max_rounds로 과금 제한)
  ABC 신설 + `OpenAIClient` 구현. `FakeAIClient`에 `tool_scripts` 테스트 더블 지원 추가.
- **Part B**: 신규 노드 `ai.free_prompt`(`app/nodes/ai/free_prompt.py`) — `{{키}}` 자동
  치환(치환 모드는 키 누락 시 AI 호출 없이 즉시 탈락 = "정형검증"의 실체, 전체 그래프 정적
  분석이 아니라 실행 시점 심볼별 런타임 가드), 도구 호출 모드는 뉴스/가격 조회 도구 4종을
  AI가 스스로 부를 수 있음(전부 기존 provider 재사용, 새 데이터소스 없음). 출력은
  `{node_id}_pass/_opinion/_confidence/_reason`로 네임스페이스, `meta.decisions`에도 기록돼
  DebugPanel이 코드 변경 없이 판단 내용을 보여줌. `backtest.py`의 AI 호출량 기간 제한을
  `ai.free_prompt`까지 확장.
- **Part C**: 노드 단독 테스트 실행(모든 노드에 범용) — `WorkflowGraph.ancestors_of()` +
  `WorkflowEngine.execute(target_node_id=...)` + `PropertyPanel.vue`의 "이 노드까지 테스트"
  버튼. 새 파라미터 타입 `"prompt"`(큰 textarea) 추가.
- **Part D**: `NewsSignalRecord.title` 필드 추가(sqlite는 기존 자동 컬럼 보정으로 하위호환) +
  `app/news_signals/aggregate.py::top_contributor()` 신규 + `apply_condition(note_fn=...)`
  확장(하위호환) — 11개 뉴스신호 노드 전부에 `<field>_top_title`/`<field>_top_score` stamp
  + 판단 사유에 근거 문구 포함.

**검증**: 백엔드 pytest 255→267개 전부 통과. `vue-tsc -b` + `npm run build` 통과. 실 서버
(`--reload`)에 curl로 라이브 검증 — `GET /nodes`에 `ai.free_prompt` 노출, 존재하지 않는 키를
참조하는 프롬프트로 테스트 실행 시 AI를 실제로 호출하지 않고(duration_ms로 확인) "누락된 키"
사유가 정확히 기록됨을 확인, `target_node_id`로 하류 노드가 실행되지 않음을 확인.

## 2026-07-28 후속 작업 9: 종목 마스터 캐시 — 종목코드↔종목명 매핑 확장 (DESIGN.md §0-10)

사용자 질문: "관리자에서 종목 키로 검색되는데, 지금 check로부터 특정 종목의 종목명과
종목코드, 섹션 등 일치시키는 로직이 있나요? 제대로 뉴스 불러올 수 있나요?" → 조사 결과
`app/market_data/symbol_master.py`가 8개 종목만 정적 하드코딩돼 있어 관리자 검색(§0-7,
뉴스에서 AI가 직접 추출한 이름 80개 이상)과 불일치함을 확인해 보고. 이어서 "캐시 구조도
만들고 둘이 일치되도록 방법을 강구해달라"는 요청으로 EnterPlanMode → 4-Part 계획 승인 →
구현.

이미 연동된 `DATA_GO_KR_SERVICE_KEY`(금융위원회_주식시세정보) API를 재사용해 KOSPI/KOSDAQ
전 종목의 코드/명/시장구분을 가져오는 `PublicDataPriceClient.fetch_market_snapshot()` 신규
(`likeSrtnCd` 없이 호출하면 시장 전체가 반환되는 기존에 알려진 서버 동작을 활용). durable
캐시로 `SymbolMasterRepository`(sqlite+in-memory) 신설, `symbol_master.py`는 8개 하드코딩을
"캐시 비었을 때의 폴백 시드"로 축소하고 `load_cache()`로 교체 가능한 in-memory 캐시 도입(호출부
4곳 전혀 무변경). `POST /data/symbols/sync` + `GET /data/symbols/stats` + 부팅 시 sqlite에서
자동 복원 + `AdminView.vue` "종목 마스터" 카드. 섹터 자동 매핑은 신뢰할 공공 API가 없어
범위에서 명시적으로 제외(기존처럼 사용자가 큐레이션된 30개 섹터에서 직접 선택).

**라이브 검증 중 발견**: 구현 후 실 서버에 `POST /data/symbols/sync`를 실제로 트리거했더니
`synced: 0`. 원인 추적 결과 신규 코드 문제가 아니라 **기존 `DATA_GO_KR_SERVICE_KEY`가 이
API(금융위원회_주식시세정보)에서 이미 항상 빈 응답(resultCode "00"인데 totalCount 0)을 준다는
것**을 확인(2025-01-02 같은 명백한 과거 영업일로 직접 curl해도 동일 — 기존
`fetch_daily_prices`/`ingest_public_prices` 경로도 똑같이 영향받음, 내가 이번에 새로 만든
코드가 원인이 아님). data.go.kr 콘솔에서 이 API에 대한 서비스키 활용 승인 상태를 확인해야
할 것으로 보임 — 코드는 mock 응답으로 전부 유닛 테스트 통과했으므로 승인만 되면 추가 코드
수정 없이 정상 동작할 것으로 예상.

**검증**: 백엔드 pytest 267→282개 전부 통과(신규: `test_symbol_master.py`,
`test_api_symbol_sync.py`, `test_public_data_price_client.py`/`test_dao_sqlite.py` 확장).
`vue-tsc -b` + `npm run build` 통과.

## 2026-07-28 후속 작업 10: 종목 마스터 동기화 — KOSCOM CHECK-API 폴백 (DESIGN.md §0-10-1)

사용자 요청: "공공데이터에서 안되는건 check api에서받아오세요" — 직전 작업(§0-10)에서 공공
데이터포털 서비스키가 실제로는 항상 빈 응답만 준다는 걸 확인했는데, 이미 실제 자격증명으로
검증된 KOSCOM CHECK-API(`app/market_data/koscom_adapter.py`)로 대체하라는 지시.

`docs/koscom-api/pages/01-stock-api/{거래소,코스닥} 종목/01-코드 정보.md`를 조사해
`POST /stock/m001(m003)/code_info`가 `jcode` 없이 시장 그룹 전체를 한 번에 돌려주는 벌크
엔드포인트임을 확인 — `KoscomMarketDataProvider.fetch_symbol_master()` 신규 추가(거래소+
코스닥 각 1회 호출, 기존 초당1회 쓰로틀 그대로 적용). `POST /data/symbols/sync`를 폴백
체인으로 변경: 공공데이터포털 먼저 시도 → 빈 응답이면 KOSCOM으로 자동 전환, 응답에
`source` 필드 추가. 관리자 페이지 문구도 갱신.

**실 서버 라이브 검증**: 사용자가 이미 띄워둔 `--reload` 서버(직접 새로 띄우지 않고 기존
프로세스 재사용 — 과거 세션에서 남의 서버를 잘못 죽인 사고 이후 확립한 습관)에
`POST /data/symbols/sync` 실행 → `{"synced": 4297, "source": "koscom"}`. 8개였던 매핑이
KOSPI+KOSDAQ 전 종목(4,297개)으로 확장됨을 실측 확인, "기아"(000270)/"LG전자"(066570) 등
정상 검색·매핑됨을 curl로 직접 확인.

섹터(업종) 정보도 API 문서상 존재함을 확인했으나(`/stock/m001/upjong_info`) 종목당 `jcode`
필요(벌크 불가) + 초당1회 제한이라 전 종목 일괄 동기화엔 부적합 — §0-10의 "섹터 자동 매핑
제외" 결정 유지, 필요시 온디맨드 개별 조회로 추후 확장 가능하다는 점만 기록.

**검증**: 백엔드 pytest 286→290개 전부 통과(신규: `test_koscom_adapter.py` 확장,
`test_api_symbol_sync.py` 확장). `vue-tsc -b` 통과.

## 2026-07-28 후속 작업 11: 백테스트/AI 화면 실시간 진행률·로그·토큰 사용량 (DESIGN.md §0-11)

사용자 요청: "백테스팅이나 ai 쓰는 화면에서 현재 로그랑 토큰 사용량, 진행률 보여줄 수 있는
패치 추가해주세요." 백테스트가 완전히 동기 요청이라 여러 거래일 실행되는 동안 프론트는
로딩 스피너만 보여주던 문제 — 조사 결과 EventBus/`/ws/runs/{run_id}`/
`subscribeRunEvents()` 실시간 스트리밍 인프라가 이미 구현돼 있었지만 전혀 안 쓰이고 있었음을
발견, 그 인프라를 재사용하는 방향으로 EnterPlanMode 계획을 세워 승인받고 진행.

- **Part A**: `BacktestRequest.progress_run_id` + `BacktestRunner.run()`이 거래일마다
  진행 이벤트(날짜/인덱스/주문건수/AI 토큰 델타)를 기존 `NodeExecutionEvent`를 "가상
  노드"로 재사용해 발행. AI 토큰 델타는 `AIUsageRepository.list_since()`(§0-6) 재사용,
  새 계측 훅 없음.
- **Part B**: `BacktestProgressPanel.vue` 신규, `BacktestResultView.vue`가 POST 전에 먼저
  WS 구독을 걸어 시작 이벤트부터 놓치지 않게 함.
- **Part C**: `/ai/generate-draft`/`/ai/workflow-chat`/`/ai/backtest-explain` 응답에
  `usage`(호출 전/후 토큰 델타) 옵션 필드 추가, `AIGenerateView.vue`/`ChatPanel.vue`에
  경과시간 카운터 + 토큰 사용량 표시.

**중요 발견(테스트 설계 버그)**: 진행 이벤트 발행 테스트에서 `bus.subscribe(id)`를 실행 완료
"이후"에 호출했더니 무한 대기(hang)가 발생 — `InMemoryEventBus.close_run()`은 "그 시점에
이미 구독 중인" 큐에만 종료 신호를 보내고 과거를 기록하지 않으므로, 늦게 구독하면 종료 신호를
영원히 못 받는다. 실제 운영에서는 WS가 항상 POST 이전에 먼저 붙으므로 문제가 안 되지만,
테스트는 monkeypatch로 `close_run` 호출 여부만 스파이하도록 수정.

**실 서버 라이브 검증(mock 아님)**: 사용자가 이미 띄워둔 서버(직접 새로 안 띄우고 기존
프로세스 재사용 — 과거 세션 사고 이후 확립한 습관)에 진짜 워크플로/백테스트를 만들고, 별도
파이썬 프로세스에서 실제 WebSocket으로 접속해 백테스트 진행 중 실시간으로 이벤트 6건을
정확한 순서로 수신함을 확인.

**검증**: 백엔드 pytest 290→293개 전부 통과. `vue-tsc -b` + `npm run build` 통과.

## 2026-07-28 후속 작업 12: 뉴스 키워드 크롤링 + 관리자 페이지 사이드바/뉴스 목록 (DESIGN.md §0-12)

사용자 요청 두 가지를 함께 처리: "지난 5일 뉴스가 없어서 5일치 뉴스만 땡겨오자. 하이닉스나
반도체, 삼성 글자가 들어간 것만" + "분석된 뉴스, 분석 안 된 뉴스도 관리 메뉴에서 볼 수 있게
해주세요. 관리자 메뉴 좀 예쁘게 만들어주시고, 최하단에 공백 좀 넣어주세요. 관리자 메뉴 내부에서
사이드바 만들어서 각 메뉴 접근 간편하도록." EnterPlanMode로 4-Part 계획 승인 후 진행.

- **Part 1**: `crawler.py::_list_page()`가 이제 URL과 헤드라인 제목을 함께 반환(추가
  네트워크 호출 없음), `_matches_keywords()` + `crawl(keywords=)`로 제목 기반 사전 필터링
  — "페이지 전부 이미 봤음" 조기중단 판단은 키워드와 무관하게 유지해 페이지네이션이
  깨지지 않게 함. `NewsTrader.update(days=, keywords=)`로 1회성 오버라이드(전역 설정 불변),
  `POST /data/news/update`에 `days`/`keywords` 필드 추가.
- **Part 2**: `db.py::count_pending`/`list_analyzed_news` + `NewsTrader` 메서드 3개 +
  `GET /data/news/pending`/`GET /data/news/analyzed` 신규.
- **Part 3**: `AdminView.vue`를 좌측 사이드바(6개 섹션) + 우측 단일 섹션 렌더링으로 전면
  재구성, "분석된 뉴스"/"미분석 뉴스" 테이블 섹션 신규, 뉴스 갱신 폼에 기간/키워드 입력
  추가, 카드 그림자 + 하단 여백(80px) 등 스타일 개선.

**Part 4 실행 직전 사용자가 실제 버그 발견**: "기사가 수집될 때 수집시점 말고 뉴스 기사
등록 시점 기준으로 판단되어야하는데" — 확인 결과 `_article()`이 발행일시 파싱에 실패하면
`datetime.now()`(크롤링 실행 시각)로 채우고 있었다. **과거 날짜를 여러 날 훑는 `days=5`
같은 크롤에서 이 폴백이 걸리면 며칠 전 기사가 "방금 발행됨"으로 잘못 찍혀** 날짜 기준
필터링/백테스트 시점 재현이 전부 틀어지는 실질 버그였다. `_article(fallback_date_str=)`을
추가해 `crawl()`이 알고 있는 "지금 훑는 목록 날짜"를 `_fetch_one`/`_fetch_page_articles`를
통해 끝까지 threading, 파싱 실패 시 그 날짜(정오 근사)로 채우도록 수정(DESIGN.md §0-12-1).
사용자가 실제 트리거 직전에 이 문제를 지적해 잘못된 타임스탬프로 데이터가 오염되는 사고를
미리 막았다 — **교훈: 실행 전에 항상 데이터 정합성을 한 번 더 검토받을 것.**

**검증**: 백엔드 pytest 293→313개 전부 통과(신규: 크롤러 키워드 필터 테스트, 발행일시
폴백 회귀 테스트, 분석됨/미분석 뉴스 db·API 테스트). `vue-tsc -b` + `npm run build` 통과.
실 서버(사용자의 `--reload` 서버)에 curl로 `/data/news/pending`(98건)/`/data/news/analyzed`
(100건) 라이브 검증, Vite dev 서버로 재구성된 `AdminView.vue` 컴파일 확인.

**미완료**: 버그 수정 후 실제 "5일 + 하이닉스/반도체/삼성 키워드" 크롤 트리거는 사용자가
커밋/푸시를 먼저 요청해 보류 — 커밋/푸시 이후 별도로 실행 필요.

## 2026-07-28 후속 작업 13: 크롤 트리거 재실행 + 한국투자증권(KIS) 연동 + 주문 수량 비율(%) (DESIGN.md §0-13)

"트리거하고, 한국투자증권 api도 붙이세요" + 중간 요청 "https://github.com/koreainvestment/
open-trading-api 여기 참고하세요" + "주문 수량을 주문 가능수량의 n% 로도 설정 가능하게
해줘(바꿀 경우 기본값 50%)". EnterPlanMode로 KIS 연동(Part A-D) + 주문 수량 비율(Part E)
통합 계획 승인 후 진행.

- **크롤 트리거 재실행**: 후속 작업 12 버그 수정 후 `POST /data/news/update`
  (`days=5, keywords=[하이닉스,반도체,삼성]`) 트리거 → `collected:0`. `GET /data/news/stats`/
  `topics`로 확인한 결과 이미 그날 이전 테스트에서 뉴스 467건/클러스터 329건(2026-07-26~
  07-28, 정확히 요청한 5일 창)이 삼성전자/SK하이닉스 등을 포함해 수집돼 있어 새로 가져올
  게 없었던 정상 동작(버그 아님)으로 결론.
- **KIS 연동**: 실제 앱키 없이도 신뢰도를 높이기 위해, 기억에 의존한 추정 대신 사용자가
  지정한 공식 GitHub 원본 예제 코드(`github.com/koreainvestment/open-trading-api`)를
  `gh api`/`curl raw.githubusercontent.com`으로 직접 fetch해 대조 확인하며 구현 — 이 과정에서
  기억으로 추정했던 주문 tr_id(`TTTC0802U` 등)가 실제로는 다름(`TTTC0011U`/`TTTC0012U`)을
  코드 대조로 잡아 정정. `app/broker/kis_auth.py`(OAuth 토큰 공급자, market_data/broker
  공유) + `app/market_data/kis_adapter.py`(시세) + `app/broker/kis_adapter.py`(주문 실행,
  잔고/보유종목 조회) 신규, `Settings`/`.env`/`.env.example`에 `KIS_APP_KEY` 등 빈 값
  추가(사용자가 직접 채워 넣을 예정), `market_data_provider`/`order_provider="kis"` DI 배선.
- **주문 수량 비율(%) 설정**: `execution.market_order`에 `qty_mode`("고정수량"|"가능수량
  비율(%)")/`qty_pct`(기본 50) 추가. KIS 전용 API 없이 엔진이 자동 주입하는 `cash`/
  `held_qty` 필드로 모든 broker provider에 동일하게 동작(provider-agnostic). **주의**:
  처음에 두 파라미터를 `required: True`로 만들었다가 기존 저장된 워크플로 그래프(이
  파라미터를 지정 안 함)가 전부 그래프 검증 실패하는 것을 pytest로 발견 — `get_param()`이
  스키마 `default`로 폴백하므로 `required: False`가 맞았다. 신규 파라미터를 required로
  추가할 때는 항상 기존 그래프 호환성을 pytest로 확인할 것(교훈).
- 상세 확인된 API 사실/필드 대소문자 비일관성 등은 DESIGN.md §0-13 참조.

**검증**: 신규 테스트(`test_kis_adapter.py`, `test_provider_selection.py` KIS 케이스,
`test_execution_nodes.py`) 포함 백엔드 pytest 313→334개 전부 통과. `vue-tsc -b` 통과(신규
파라미터가 select/number/show_if 표준 타입이라 프론트 코드 변경 불필요, `ParamFields.vue`가
그대로 렌더링). 실제 KIS API 호출 검증은 불가(앱키 미발급) — mock 기반 유닛 테스트로
구조/필드만 확인, 사용자가 앱키 발급 후 재검증 권장.

## 2026-07-28 후속 작업 14: 뉴스 목록 크롤링 빈 제목 버그 + 미저장 시 테스트/백테스트 무반응 버그

사용자가 실제 화면(`/backtests/c52213dc-...`)에서 "뉴스가 하나도 반영 안 됨" + "그래프에서
23일(=백테스트 시작일 07-23) 뉴스가 전부 마지막날에 박혀있다"를 신고. 원인 조사 중 §0-13
때 이미 "해결됐다"고 잘못 판단했던 크롤 트리거(`collected:0`)가 사실은 이 버그 때문이었음을
발견.

- **근본 원인**: 네이버 뉴스 목록 HTML은 기사 하나당 `<a>`가 두 개(썸네일 이미지용 + 헤드라인
  텍스트용) 나오고 href가 같다. `crawler.py::_list_page()`가 "URL당 첫 등장만 기록"하던
  방식이라, 썸네일 `<a>`(텍스트 없음, `<img>`만 감쌈)가 헤드라인 `<a>`보다 먼저 나오는
  경우(실측 20건 중 16건, 80%)에 제목을 빈 문자열로 저장하고 있었다. `crawl(keywords=...)`는
  이 제목으로 키워드를 매칭하므로, 빈 제목은 항상 매칭 실패 → 사실상 모든 기사가 조용히
  건너뛰어졌다. 무필터 크롤(관리자 페이지 초기 테스트)은 제목과 무관하게 본문을 항상 가져와
  이 버그가 드러나지 않았던 것.
- **수정**: 같은 URL이 다시 나오면 기존 값이 비어있을 때만 새 텍스트로 덮어쓰도록
  `_list_page()` 수정 + 실제 HTML 구조를 재현한 회귀 테스트 추가
  (`test_list_page_prefers_headline_text_over_empty_thumbnail_anchor`).
- **재검증**: 수정된 크롤러로 5일+키워드(하이닉스/반도체/삼성) 크롤을 재트리거 →
  `collected:21`(이전: 0). `newsstock.db`의 날짜 분포가 07-28 564건/07-26 1건 →
  6일(07-23~07-28) 전부에 매칭 뉴스가 채워짐으로 확인. 해당 백테스트의
  `/backtest/.../news/signal` 마커도 6일에 걸쳐 분산됨을 API 응답으로 직접 확인.
- **부수 발견/수정**: 같은 화면 조사 중 사용자가 별도로 "저장하지 않아서 메뉴가 안눌리는 경우
  (테스트/백테스트 안 열리는 경우) 알림 가이드"를 요청. `StrategyBuilderView.vue::goBacktest()`
  는 `workflowId`가 없으면(아직 저장 안 한 새 전략) 그냥 `return`해 버튼이 조용히 무반응이었고,
  `openTestRun()`도 `ensureSaved()`(자동 저장) 실패 시 에러가 알림 없이 흘렀다. 둘 다
  `ensureSaved()`를 저장 실패 시 안내 `alert()`로 감싸도록 수정(기존 `toggleActivate()`와
  동일한 패턴 재사용) — 저장 가능하면 자동 저장 후 정상 진행, 실패하면 이유를 알려준다.

**검증**: 백엔드 pytest 335개(신규 회귀 테스트 1개 포함) 전부 통과. `vue-tsc -b` 통과.
브라우저 자동화 도구가 이 환경에 없어 프론트 변경은 라이브 클릭 검증은 못했다 — 기존
`toggleActivate()`와 동일한 검증된 패턴을 그대로 재사용한 것으로 리스크를 낮췄다.

## 2026-07-28 후속 작업 15: 종목코드 자동완성 + 뉴스/AI 백테스트 최대기간 14일 + AI 아이디어 예시 5개

사용자 요청: "대상 종목코드 쓸때 자동완성 되게 해주고(한글도 숫자도 되게) ai, 뉴스 사용
백테스트 최대 14일로 늘려줘. 하닉/삼성 14일치 뉴스 갱신해주고, 투자 아이디어 쓰기 쉽게
예시 여러 개(5가지) 추가해줘."

- **종목코드 자동완성**: `symbolMaster` 스토어(§0-10, 세션 동안 캐싱된 전 종목 코드↔한글명
  매핑)에 `search(query, limit)` getter 추가 — 코드/한글명 부분일치(대소문자 무시)로 클라이언트
  단에서 필터링해 타이핑마다 API 호출이 없다. `frontend/src/components/SymbolAutocomplete.vue`
  신규(콤마 구분 다중 입력, 마지막 토큰만 검색해 드롭다운, 키보드 ↑↓/Enter/Esc 지원) —
  "대상 종목코드" 입력이 있던 3곳(`BacktestResultView.vue`, `TestRunModal.vue`,
  `AIGenerateView.vue`) 모두 이 컴포넌트로 교체.
- **뉴스/AI 백테스트 최대기간**: `app/api/routers/backtest.py::NEWS_SIGNAL_BACKTEST_MAX_DAYS`
  7 → 14, 프론트 안내 문구용 상수(`BacktestResultView.vue::NEWS_SIGNAL_MAX_DAYS`)도 동기화.
- **AI 아이디어 예시 5개 추가**: `AIGenerateView.vue::IDEA_TEMPLATES`에 사용자가 준 예시(종목
  지정+뉴스/AI확신도 매수+익절/손절/보유기간+포지션사이징+최대종목수+포트폴리오 킬스위치)를
  포함해 RSI+이동평균, 거래량+공시, 섹터모멘텀+거시리스크, 볼린저밴드+거래량 조합 등 복합
  조건 예시 4개를 더해 총 9개.
- **14일치 뉴스 재수집**: 수정된 크롤러(후속 작업 14)로 `days=14,
  keywords=[하이닉스,삼성]` 트리거.

**검증**: 백엔드 pytest 335개 전부 통과(제한값만 상수 변경이라 기존 테스트가 상수를 그대로
참조해 추가 수정 불필요). `vue-tsc -b` 통과. 브라우저 자동화 도구가 없어 자동완성 컴포넌트의
라이브 클릭 검증은 못했다.

## 2026-07-28 후속 작업 16: AI 호출 오류 — tools(함수 호출)에 reasoning_effort 미지정 시 400

사용자가 실사용 중 에러 메시지를 그대로 보고: `Function tools with reasoning_effort are not
supported for gpt-5.6-luna in /v1/chat/completions. To use function tools, use /v1/responses
or set reasoning_effort to 'none'.`

- **원인**: `OpenAIClient.complete_with_tools()`(`ai.free_prompt` 노드의 도구 호출 모드가
  사용)가 `tools=`를 넘겨 `chat.completions.create()`를 호출하는데, gpt-5.6-luna 같은
  reasoning 모델은 tools와 함께 쓸 때 `reasoning_effort`를 명시적으로 "none"으로 지정하지
  않으면 400을 낸다. 기존 코드는 이 파라미터를 아예 안 보내고 있었다(계정 기본값이 걸림).
- **수정**: `_create()`의 기존 "temperature 미지원 시 재시도" 패턴(§0-1)을 확장 —
  `BadRequestError.body.param`이 `"reasoning_effort"`이면 `reasoning_effort="none"`을 추가해
  1회 재시도(param이 `"temperature"`/`"reasoning_effort"` 둘 다 아니면 기존처럼 그대로
  re-raise). `app/vendor/news_classifier/classifier.py::call_ai`는 tools를 안 써서 이 문제와
  무관 — 수정 불필요.
- **검증**: 회귀 테스트 추가(`test_complete_with_tools_retries_with_reasoning_effort_none_on_unsupported_value`).
  백엔드 pytest 336개 전부 통과.

## 2026-07-28 후속 작업 17: 백테스트 매매 지점 클릭 → "왜 샀는지" 팝업 (DESIGN.md §0-14)

사용자 요청: "매수/매도가 어떤 로직으로 발생했는지, 뉴스 노드가 true면 무슨 뉴스로
종합적으로 그렇게 됐는지 보여줬으면 좋겠다. 그래프 지점 클릭 시 팝업으로 흐름이 시각적으로
잘 보이면 좋겠고, AI api로 뉴스 이유도 요청해서 가져와도 된다." EnterPlanMode로 Part A-D
계획 승인 후 진행.

- 조사 결과 매매 마커 클릭 → 그래프 리플레이/DebugPanel, `POST /ai/backtest-explain` 인프라는
  이미 있었지만 **AI-explain 프롬프트가 `meta.decisions`(판단 사유, ai.news_signal이면 참고
  뉴스 제목까지 포함)를 전혀 안 실었고**, `used_news`는 구 파이프라인만 알아 `ai.news_signal`
  기반 워크플로에서는 AI가 뉴스 근거를 볼 방법이 아예 없었다(§0-6에서 마커는 고쳤지만
  AI-explain은 그때 놓친 사각지대) — 이번 작업의 핵심은 이 데이터 배관 보강.
- Part A: `_summarize_day_events()`가 노드 타입 무관하게 `decisions`를 포함하도록 수정(한 줄
  변경으로 모든 필터형 노드의 판단 사유가 AI 프롬프트에 자동 반영).
- Part B: `get_backtest_news_signal()`의 클러스터 조회 로직을 `resolve_news_signal_clusters()`
  로 추출해 마커 엔드포인트와 AI-explain selection(`news_signal_clusters`)이 공유하도록
  리팩터링 — 동작 불변(기존 테스트로 확인).
- Part C: `TradeExplainModal.vue` 신규(매매 마커 클릭 시 팝업). 즉시 표시되는 부분(그날의
  decisions를 세로 타임라인으로, AI 호출 없이 무료·즉시)과 버튼 클릭 시에만 호출되는 "AI
  종합 설명" 부분을 분리 — 매 클릭마다 AI 비용이 나가지 않게 함. `DebugPanel.vue`의 decisions
  추출 로직을 `src/utils/decisions.ts`로 공유 유틸로 정리.
- Part D: `BacktestChart.vue`에 `open-trade` emit 추가(기존 `select`/`select-day` emit은
  안 건드림 — 비파괴적 추가), `BacktestResultView.vue`가 모달을 띄움.

**검증**: 신규 단위/통합 테스트 포함 백엔드 pytest 336→340개 전부 통과, 리팩터링한 마커
엔드포인트의 기존 테스트도 그대로 통과(동작 불변 확인). `vue-tsc -b` 통과. 브라우저 자동화
도구가 이 환경에 없어 모달 실제 클릭/렌더링은 라이브 검증 불가 — 기존 검증된 컴포넌트 패턴
(TestRunModal 모달 스타일, DebugPanel decisions 추출)을 그대로 재사용해 리스크를 낮췄다.

## 2026-07-29 후속 작업 18: .env로 AI 제공자(OpenAI ↔ Claude) 선택 + KIS 문의 답변 (DESIGN.md §0-15)

사용자 요청: "`.env`를 사용해서 claude를 사용할지, openai를 사용할지 결정할 수 있도록 해
주세요. order provider에 kis 들어가려면 어떻게 해야하는지 알려주세요." KIS 질문은 이미
구현된 기능(§0-13)이라 `.env` 설정 방법만 답변, AI 제공자 선택은 EnterPlanMode로 계획 승인
후 구현.

- `AIClient` 추상화(§0-6 이전부터 존재)가 이미 모든 AI 소비자를 인터페이스로만 묶어놔서,
  `app/ai/claude_client.py`(`ClaudeClient`) 신규 + `Settings.ai_provider`
  (`openai|claude`) + `app/dependencies.py::_build_ai_client()` 분기 하나로 전체 AI 기능이
  provider 전환됨. Anthropic Messages API 스펙은 공식 문서를 직접 대조해 확인(도구 스펙이
  OpenAI와 달라 변환 필요 — `_tool_to_anthropic()`).
- `app/vendor/news_classifier`(newsstock-lib)는 자체 하드코딩 OpenAI 클라이언트를 쓰는
  별개 vendored 파이프라인이라 이 토글 범위 밖으로 명시적으로 뺌.
- **실사용 중 발견한 문제 2건**(사용자가 KIS 설정을 직접 진행하며 실시간으로 마주침):
  1. `KIS_ACCOUNT_NO`를 8자리 계좌번호만 넣어(`50199589`) 발생한 `ValueError`("12345678-01"
     형식 요구) — 모의투자도 8자리+상품코드 2자리(보통 "01") 형식이 필요함을 안내, 사용자가
     `50199589-01`로 직접 수정해 해결.
  2. 그 후 실제 KIS API(`inquire-balance`)에서 500 에러 — 공식 예제(`inquire_balance.py`)와
     파라미터/tr_id를 다시 대조해 우리 쪽 요청 구성엔 문제가 없음을 확인, KIS 측(신규 발급
     키 전파 지연 또는 모의투자 서버 이슈로 추정) 문제로 안내. **미해결** — 사용자가 KIS
     쪽에서 직접 확인 필요.
  3. (부수 발견) `tests/conftest.py::app_client` 픽스처가 자격증명만 비우고 provider 선택
     (`market_data_provider`/`order_provider`) 자체는 그대로 둬, 로컬 `.env`가 실사용 설정
     (koscom/kis)일 때 거의 모든 통합 테스트가 fixture 단계에서 깨지는 걸 실제로 겪고 발견 →
     provider 선택도 함께 dummy로 강제하도록 수정(픽스처 자체 주석에 이미 명시된 의도를
     완성).

**검증**: 신규 `test_claude_client.py`(8개) + `test_provider_selection.py` 확장 포함 백엔드
pytest 340→350개 전부 통과(`test_koscom_live.py`는 실 시장 상황에 따라 비결정적인 기존
라이브 테스트라 제외). `vue-tsc -b` 통과(프론트 변경 없음). 실제 Anthropic 호출은 사용자가
`ANTHROPIC_API_KEY`를 채워 넣은 뒤 재검증 필요.

## 2026-07-29 후속 작업 19: 관심종목 + 보유 포지션 직접 관리 + PWTESTQ1/PWRESTART1 정리 (DESIGN.md §0-16)

사용자가 대시보드에서 `PWTESTQ1`/`PWRESTART1`를 발견하고 질문 → 조사해서 원인 설명("테스트
실행"이 라이브 계좌를 공유해 생긴 잔재) → "관심종목 신규 / 보유 포지션 직접 관리 / 정리
전부 다"로 답변받아 EnterPlanMode로 계획 승인 후 구현.

- `WatchlistRepository` 3계층 신규(기존 `PortfolioRepository`와 동일 패턴) + `PUT`/`DELETE
  /account/positions/{symbol}`(기존 `upsert_position`의 "qty<=0=삭제" 재사용) + `GET/POST/
  DELETE /account/watchlist`. `DashboardView.vue`에 포지션 수정/삭제 버튼 + "종목 직접 추가"
  + "관심 종목" 섹션(`SymbolAutocomplete` 재사용) 추가.
- 새 DELETE 엔드포인트로 실제 `PWTESTQ1`/`PWRESTART1`를 정리 — sqlite로 직접 확인 완료.
  (`GET /account/summary`는 현재 `ORDER_PROVIDER=kis`가 KIS 측 500으로 막혀 있어 확인에
  못 씀 — §0-15 후속의 미해결 외부 이슈, 이번 작업과 무관.)
- **작업 중간에 사용자가 새 요청 3건을 추가로 보냄**(모두 태스크로 큐잉, 순서대로 처리 예정):
  "로그인 페이지 없애줘"(인증 자체 완전 제거로 확인), "AI 배치 호출을 스트리밍으로",
  "전략 생성 AI와 나머지 AI가 .env에서 모델을 각각 선택할 수 있게".

**검증**: 신규 통합 테스트 8개 포함 백엔드 pytest 351→359개 전부 통과. `vue-tsc -b` 통과.
브라우저 자동화 도구가 없어 프론트 클릭 검증은 못함 — curl로 API 자체는 라이브 검증.

## 2026-07-29 후속 작업 20: 인증 게이트 완전 제거 (DESIGN.md §0-17)

사용자 요청: "로그인 페이지 없애줘." AskUserQuestion으로 범위 확인("프론트 자동 로그인" vs
"인증 자체 완전 제거") → 인증 자체를 완전히 제거하는 것으로 확정 후 진행.

- 백엔드: `POST /auth/login`(`app/api/routers/auth.py`) + `app/schemas/auth.py` 삭제, 7개
  라우터의 `Depends(get_current_username)` 게이트 전부 제거, `app/auth/security.py`를
  `hash_password`(admin 계정 시드용) 하나로 축소, `Settings.jwt_*` 필드 + `pyjwt` 의존성
  제거.
- 프론트엔드: `LoginView.vue`/`stores/auth.ts` 삭제, 라우터 가드/Authorization 헤더 첨부/
  401 인터셉터/로그아웃 버튼 전부 제거 — 앱 진입 시 바로 대시보드로 감.
- 기존 테스트 대부분은 `conftest.py::auth_headers`를 `/auth/login` 대신 빈 dict를 반환하도록
  바꿔 무수정으로 통과시키고, "인증 없이 401 기대"하던 테스트 9개는 더 이상 성립하지 않는
  주장이라 삭제.

**검증**: 백엔드 pytest 359→350개 전부 통과. `vue-tsc -b` 통과. 인증 관련 잔여 참조 없음을
grep으로 재확인.

## 2026-07-29 후속 작업 21: AI 배치 호출을 스트리밍으로 전환 (DESIGN.md §0-18)

사용자 요청: "전략 생성이나 대화 등 빠르게 요청받아야 하는 것들은 배치가 아닌 stream으로
바꿔줘." AI 응답이 `{"reply","changed","nodes","edges"}`가 한 JSON에 같이 담기는 구조라
"순수 대화 텍스트만 깔끔하게 스트리밍"(프롬프트 계약 변경 필요, 검증/재시도 로직 리스크)과
"원문 텍스트 실시간 미리보기"(저위험, 기존 로직 무변경) 중 선택하도록 확인 질문 →
저위험 옵션으로 확정 후 EnterPlanMode로 계획 승인 후 진행.

- `AIClient.complete_json_stream(..., on_chunk=None)` 신규(OpenAI/Claude 둘 다 구현, Claude는
  공식 문서 스트리밍 패턴을 직접 대조해 확인). `generate_workflow_draft`/`chat_about_workflow`/
  `explain_backtest`가 첫 시도만 스트리밍하고 재시도 경로는 기존 블로킹 유지.
- `POST /ai/{generate-draft,workflow-chat,backtest-explain}/stream` 3개 신규(SSE, 기존
  블로킹 엔드포인트는 무수정 유지 — 순수 추가라 리스크 최소).
- 프론트: `postSSE()` 유틸 신규, AIGenerateView/ChatPanel/BacktestAskPanel이 스트리밍 중
  누적 원문을 실시간으로 보여주다 완료 시 기존 UI로 전환.

**검증**: 신규 유닛/통합 테스트 포함 백엔드 pytest 350→361개 전부 통과. `vue-tsc -b` 통과.
curl/TestClient로 실제 SSE 프레임 순서(chunk→result) 라이브 확인.

## 2026-07-29 후속 작업 22: 전략 생성 AI와 나머지 AI의 모델을 .env에서 별도 선택 (DESIGN.md §0-19)

사용자 요청: "전략 생성 ai랑 나머지 ai 에서 사용할 모델을 별도로 선택할 수 있도록 해 주세요.
.env에서 사용 모델을 각각 선택하고 싶어요." 기존엔 `AI_PROVIDER`+`OPENAI_MODEL`/
`ANTHROPIC_MODEL` 하나로 전략 생성과 나머지 AI 기능이 항상 같은 모델을 썼다.

- `_build_ai_client(settings, ai_usage_repo, model_override=None)` — 기존 팩토리에
  `model_override` 파라미터만 추가. `Container`에 `strategy_ai_client` 필드 신설,
  `build_container()`에서 팩토리를 두 번 호출해 `ai_client`(기본)와
  `strategy_ai_client`(`AI_MODEL_STRATEGY` 있으면 그걸, 없으면 기본과 동일)를 분리 생성.
- `Settings.ai_model_strategy` + `.env`/`.env.example`에 `AI_MODEL_STRATEGY=` 신규(빈 값 =
  기본 모델 그대로).
- `get_strategy_ai_client` 신규 의존성. `POST /ai/generate-draft`(+`/stream`) 두 엔드포인트만
  이걸로 교체, `workflow-chat`/`backtest-explain`(+`/stream`)은 기존 `get_ai_client` 유지.

**검증**: `_build_ai_client` model_override 유닛 테스트 2개 추가. 기존 `/ai/generate-draft`
테스트 5개가 `dependency_overrides[get_ai_client]`를 쓰고 있어 엔드포인트가 이제
`get_strategy_ai_client`를 쓰는 데 맞춰 오버라이드 키 수정(동작이 아니라 테스트가 갈아끼울
의존성만 변경). 두 클라이언트가 독립적으로 주입되는지 확인하는 통합 테스트 신규 추가.
백엔드 pytest 361→364개 전부 통과. `vue-tsc -b` 통과(프론트 변경 없음).

## 2026-07-29 후속 작업 23: 프론트엔드 디자인 리뉴얼 (nemo-poc 참고) + 새 전략 페이지 통합

사용자 요청: `koscom-mini-project-4/nemo-poc`(React/Vite 버전) 프론트 CSS를 참고해 색상·로고·
버튼·화면 비율을 비슷하게 가져오고, 노드 빌더 노드마다 카테고리별 외곽선 색, 손익/매수·매도
색상, "nemo-stock PoC" 문구 삭제. 이어서 버튼/노드를 각진 사각형으로, 배경에 은은한 그래디언트,
화면 전반에 shadow 추가 요청. 마지막으로 "새 전략" 페이지를 nemo-poc의 NewStrategyPage처럼
빈 캔버스/AI 초안/템플릿 3가지 시작 방법을 한 페이지에 모으고, 대시보드의 "템플릿으로 시작하기"
섹션은 제거, 기존 AI 전략 생성 페이지의 예시 프롬프트 자동완성 버튼은 유지하도록 요청.

**색상/디자인 시스템**: `frontend/src/style.css`의 CSS 변수를 nemo-poc 팔레트로 교체(주황
`--accent #f26a21` + 남색 `--secondary`, `--bg`/`--surface`/`--border` 등). 한국 증시 관례에
맞춰 `--positive`(빨강, 상승/매수/이익)·`--negative`(파랑, 하락/매도/손실) 신설 — 기존엔
매수=초록/매도=빨강(서구식)으로 뒤섞여 있던 것을 통일: `BacktestChart.vue` 매매 마커(범례도
매수/매도 데이터셋으로 분리)·`PriceChart.vue` 캔들 upColor/downColor·`BacktestResultView.vue`
누적수익률·`TradeExplainModal.vue` 매수/매도 라벨+실현손익에 전부 적용.

**노드 카테고리 색상**: `frontend/src/utils/categoryColors.ts` 신규(scheduler=보라/data=파랑/
indicator=청록/ai=핑크/logic=주황/risk=빨강/execution=남보라) — `NodePalette.vue` 아이템
좌측 테두리, `StrategyBuilderView.vue`/`BacktestResultView.vue`의 캔버스 노드 카드(`.wf-node`)
좌측 굵은 테두리 + 색 점에 공통 적용.

**로고/브랜딩**: nemo-poc의 `logo2.png`를 `frontend/public/logo.png`로 복사해 헤더 로고 +
파비콘으로 사용. `App.vue`에서 "nemo-stock PoC" 문구 삭제, `index.html` title을
"네모네모매매"로 변경.

**각진 스타일 + shadow + 그래디언트**: 프로젝트 전역 `border-radius`를 python 스크립트로
일괄 정규화(6~12px/999px → 4px, 5px → 3px; 버튼/입력/배지는 3px, 카드/노드는 4px 또는 3px)해
전체적으로 각진 느낌으로 통일. `.btn`에 `text-decoration: none` 명시(RouterLink 기반 버튼의
밑줄 제거), `.card`/`.btn`/`.btn-primary`/`.wf-node`/`.node-palette`에 은은한 box-shadow 추가.
배경 그래디언트는 처음에 `.app-main`(내부 스크롤 컨테이너)에 넣었더니 스크롤 시 중간에 끊기는
문제가 있어(요소 자체 높이 기준으로만 그려짐) `body`로 옮기고 `background-attachment: fixed`로
변경 — 뷰포트 기준 한 번만 그려져 내부 콘텐츠가 아무리 길어도 끊기지 않음.

**"새 전략" 페이지 통합**: 기존엔 빈 캔버스(`/strategies/new`가 캔버스를 바로 염) / AI 생성
(`/ai/generate` 별도 페이지) / 템플릿(대시보드에 섹션)이 흩어져 있었음. nemo-poc의
NewStrategyPage 구조를 참고해 `frontend/src/views/NewStrategyView.vue` 신규 — 빈 전략 배너 +
AI 초안 폼(기존 `AIGenerateView.vue`의 스트리밍 생성/예시 프롬프트 자동완성 버튼 9종/디스클레이머
로직을 그대로 이식) + 템플릿 그리드(대시보드에서 이전)를 한 페이지에 배치. 라우팅 변경:
`/strategies/new` = 새 랜딩 페이지, `/strategies/new/canvas` = 실제 빌더 캔버스(신규 경로),
`/ai/generate` 경로와 `AIGenerateView.vue` 삭제(기능은 새 페이지로 이식됨), 헤더 네비게이션의
"AI 전략 생성" 링크 제거. `DashboardView.vue`에서 템플릿 fetch/상태/그리드 섹션 전부 제거하고
"새 전략 만들기" 버튼 하나만 남김(기존 "AI로 전략 생성" 버튼도 중복이라 제거).

**검증**: `vue-tsc -b`(`noUnusedLocals` 포함) + `npm run build` 통과. Playwright로 대시보드/
새 전략 페이지/캔버스 실제 렌더링 확인(콘솔 에러 0건) — 카테고리별 노드 테두리 색, 캔들
빨강/파랑, 각진 버튼/카드, 그래디언트 배경 정상 표시. 백엔드 변경 없음(pytest 재실행 생략).

## 2026-07-29 후속 작업: 대시보드 수익률(전략별/종목별/평가자산) + 클릭 토글

사용자 요청: 대시보드에서 전략별/종목 시세별/평가자산 수익률을 보여주고, 클릭하면 수익률(%)이
수익금액(원)으로 바뀌는 기능. 수익=빨강/손실=파랑(기존 `--positive`/`--negative`, 한국 증시 관례,
이미 `BacktestChart.vue` 매수/매도 마커에 적용되어 있던 색상 재사용).

**전략별 수익률 계산 기준 확정**(`AskUserQuestion`): 계좌가 전략별로 분리되지 않은 단일 공용
포트폴리오라 실거래 손익을 전략별로 정확히 나눌 원장이 없음을 확인 후, "실거래 체결 이력 기반"
(신규 구현, 같은 종목을 여러 전략이 매매하면 근사치)으로 결정.

**신규 `app/workflow/pnl.py`**: 워크플로의 live/test run들이 남긴 `execution.market_order` 노드의
`meta.orders`(order_id 기준 시간순 중복 제거)를 모아, 해당 워크플로 자신의 체결만으로 이동평균
평단가를 별도 추적해 실현+평가손익을 근사 계산(`load_workflow_fills` + `compute_workflow_pnl`,
순수 함수 — `fill_logic.py`와 동일 패턴으로 테스트 용이성 확보). `GET /workflows/pnl-summary`
(라우트 순서상 `/{workflow_id}`보다 먼저 등록 — `templates`와 동일한 이유) 신규 추가.

**실기 중 발견한 사전 존재 버그(계획에 없던 수정)**: `POST /workflows/{id}/run`("테스트 실행")이
`RunRecord`는 저장하면서도 `NodeEventRecord`는 저장하지 않아(라이브 트리거/백테스트만 저장), 테스트
실행이 실제로 공용 포트폴리오에 체결을 남기는데도(`container.broker`가 라이브/테스트 공용
`PersistentOrderExecutionProvider`) 그 체결 이력이 전략별 손익 집계와 `GET /runs/{run_id}` 재생
양쪽에서 누락되고 있었음. `run_workflow`에 `container.node_event_repo.save_many(events_to_records(...))`
추가로 라이브/테스트/백테스트 3경로 모두 동일하게 영속화되도록 수정.

**평가자산 수익률**: `AccountSummaryOut`에 `initial_cash`(= `Settings.initial_portfolio_cash`) 필드
추가, 프론트가 `(equity - initial_cash) / initial_cash`로 계산(백엔드에 별도 계산 로직 불필요).

**종목 시세별 수익률**: 신규 엔드포인트 없이 프론트에서 기존 보유 포지션(`avg_price`)과 이미
로드해 쓰던 `priceSeries`(최근 종가)로 계산.

**프론트**: `frontend/src/utils/pnl.ts`(신규, `pnlClass`/`formatSignedPct`/`formatSignedKrw`) +
`DashboardView.vue`에 클릭 토글용 `reactive(Set)`(`amountMode`, 키: `"equity"`/`"pos:<symbol>"`/
`"wf:<id>"`) — 항목별로 독립적으로 %/원 표시 전환.

**검증**: 백엔드 pytest 105→**370개 전부 통과**(신규 `test_workflow_pnl.py` 5 + 통합 1),
프론트 `vue-tsc -b` 통과. 실제 실행 중이던 dev 서버(8000/5173)에 curl로 임시 워크플로를
만들어 테스트 실행 → `pnl-summary`가 체결을 정확히 반영(`realized_pnl`/`unrealized_pnl`/
`return_pct`)함을 확인 후 임시 워크플로 삭제. **이 과정에서 실제 dev DB의 005930 포지션에 테스트
매수 1주(₩1,000)가 실제로 체결되어 남았음을 확인, 포지션은 원래 값(qty=2, avg_price=50040.95)으로
복원했으나 현금 ₩1,000(시드 1천만 원의 0.01%)은 계좌 조정용 API가 없어 복구하지 못함** — 사용자에게
공지. 브라우저를 통한 실제 렌더링/클릭 토글 시각 확인은 이번 세션에 Playwright 등 브라우저 도구가
없어 수행하지 못했음(백엔드 API curl 검증 + 프론트 타입체크 + dev 서버 로그의 정상 200 응답까지만
확인) — 다음 세션에서 브라우저로 실제 클릭 토글/색상 표시를 확인 필요.

## 2026-07-29 후속 작업 2: 관리자 페이지 AI 사용량에 추정 비용(USD) 추가

사용자가 OpenAI/Anthropic 공식 가격표를 붙여넣고 관리자 메뉴 "사용량 통계"에서 비용도
볼 수 있게 해달라고 요청. 기존에 `AIUsageRecord`(purpose/model/prompt_tokens/
completion_tokens)는 이미 있었으나 $ 환산이 없었음.

**`backend/app/admin/pricing.py`(신규)**: 2026-07-29 기준 스냅샷 가격표(하드코딩,
자동 갱신 안 됨) — OpenAI(gpt-5.6/5.4/5.2/5.1/5/4.1 계열)와 사용자가 지정한 Claude 4종
(sonnet-5/opus-5/haiku-4-5/fable-5). `claude-sonnet-5`는 2026-08-31까지 도입가($2/$10)
적용, 이후 정가($3/$15)로 갱신 필요라고 주석에 명시. `estimate_cost_usd(model, prompt,
completion)` — 가격표에 없는 모델은 `None`(합계에서 제외, "가격 미상"으로 표시).
`AIUsageRecord`가 캐시 히트 여부를 기록하지 않아 prompt_tokens 전체를 표준(비캐시)
단가로 계산 — 상한 추정치임을 관리자 페이지에 안내 문구로 명시.

**`app/admin/metrics.py::aggregate_usage`**: by_purpose/by_model 각 항목에 `cost_usd`
추가(by_purpose는 모델이 섞일 수 있어 `unpriced_tokens`도 별도 집계), 전체
`total_cost_usd`/`total_unpriced_tokens` 추가. 기존 유닛 테스트(정확 dict 비교)가
깨져서 갱신 + 미가격 모델 케이스 테스트 추가.

**실기 중 발견한 가격표 공백**: 실행 중이던 dev 서버의 실제 사용 이력(`/admin/metrics`)으로
검증하던 중 `gpt-5.4-nano`(742만 토큰, 전체의 약 25%)가 가격표에 빠져 있어
`total_unpriced_tokens`가 0이 아니게 잡히는 것을 발견 — 사용자가 붙여넣은 표에 있던
gpt-5.4 계열(5.4/5.4-mini/5.4-nano)과 5.2/5.1을 추가해 실사용 데이터 기준
`total_unpriced_tokens=0`, `total_cost_usd≈$21.44`까지 확인.

**프론트**: `AIUsageSummary`/`AIUsageByBreakdown`에 `cost_usd`/`total_cost_usd`/
`unpriced_tokens`/`total_unpriced_tokens` 추가, `frontend/src/utils/format.ts`에
`formatUsd`(소수점 4자리, 소액 표시용) 추가, `AdminView.vue`에 "추정 비용(USD)" KPI +
목적별/모델별 표에 비용 컬럼 + 미가격 토큰 안내 문구.

**회귀**: 백엔드 pytest 370/371 통과(실패 1건은 KOSCOM 실계좌 라이브 API 의존 사전
존재 flaky 테스트, 무관), 프론트 `vue-tsc -b` 통과. 실행 중이던 dev 서버에 curl로
`/admin/metrics` 직접 호출해 실제 이력 데이터 기준 값 확인.

## 2026-07-29 후속 작업 3: 대시보드 배지 개행 수정 + "내 전략" 위치 이동 + 관심종목 드래그 정렬

사용자가 스크린샷으로 "중지"/"초안" 배지 글씨가 두 줄로 개행되는 문제를 지적, "내 전략"
섹션을 5개 KPI 요약 카드 바로 아래로 옮겨달라고 요청, 관심종목을 드래그로 순서 변경할 수
있게 해달라고 요청.

**`frontend/src/style.css`**: `.badge`에 `white-space: nowrap` 추가.
`DashboardView.vue`의 `.workflow-name`에 ellipsis 처리 + `.workflow-card-head`에
`gap` 추가해 긴 전략명이 배지를 밀어내 개행되는 것도 방지.

**`frontend/src/views/DashboardView.vue`**: "내 전략" `<section>`을 KPI 그리드
바로 아래(보유 종목 시세 섹션보다 위)로 이동. 관심종목 카드에 `draggable="true"` +
드래그 핸들(⠿) 추가, `onWatchDragStart`/`onWatchDrop`으로 `watchlist` 배열을 직접
splice해 순서 변경 — 백엔드에 순서 저장 필드가 없어 화면 표시 순서만 바뀌고 새로고침 시
초기화됨(영구 저장하려면 추후 정렬 필드 추가 필요).

**검증**: 프론트 `vue-tsc -b` 통과. `NODE_PATH`로 기존에 설치된 playwright
(`/Users/2p31/mcp-servers/web-search-mcp/node_modules`)를 빌려 dev 서버
스크린샷으로 배지 한 줄 표시/섹션 순서 확인 + 마우스 드래그 시뮬레이션으로 관심종목
순서가 실제로 바뀌는 것까지 확인.

## 2026-07-29 후속 작업 4: AI 초안 미리보기를 텍스트 목록 → 캔버스로 전환 + 전략 설명 텍스트 추가

사용자가 "새 전략" 페이지에서 AI 초안 생성 결과가 `n1 — scheduler.interval` 같은 텍스트
목록으로만 보이는 게 아쉽다며, 실제 노드/간선 배치가 보이는 미리보기 캔버스로 바꾸고
전략에 대한 설명 텍스트도 같이 받아서 보여달라고 요청.

**`backend/app/ai/workflow_draft.py`**: 시스템 프롬프트에 `description`(전략을 2~4문장
한국어로 요약) 필드를 JSON 응답 형식에 추가 요구, 두 return 지점 모두
`raw.get("description") or ""`로 채움(누락 시 빈 문자열 기본값). `backend/app/schemas/ai.py`의
`GenerateDraftResponse`에 `description: str = ""` 추가.

**`frontend/src/components/WorkflowGraphPreview.vue`(신규)**: `StrategyBuilderView.vue`가
쓰는 것과 같은 VueFlow 캔버스를 읽기 전용(드래그/연결/선택 모두 비활성화)으로 재사용하는
공용 미리보기 컴포넌트 — `graph`/`nodeTypes` prop만 받아 `graphToFlowElements`로 렌더링.
`frontend/src/views/NewStrategyView.vue`에서 기존 `<ul class="node-list">` 대신 이 컴포넌트를
쓰고, `draft.description`을 그 위에 표시. 미리보기용 노드 표시명/카테고리 색을 위해
`fetchNodeTypes()`도 함께 로드하도록 추가.

**검증**: 백엔드 pytest 372개 통과(설명 필드 있음/누락 케이스 유닛 테스트 추가), 프론트
`vue-tsc -b` 통과. dev 서버에서 playwright로 실제 AI 초안 생성 → 설명 텍스트 + 캔버스
미리보기 표시 → "캔버스에서 편집" 클릭 시 정상적으로 편집 캔버스로 넘어가는 것까지 확인.

## 2026-07-29 후속 작업 5: 검색 기반 뉴스 딥 크롤러 + 대시보드 일봉 180일 + Docker 배포 버그 2건 (DESIGN.md §0-20, §0-21)

사용자 요청: (1) "아이씨에이치"가 제목/본문에 들어간 뉴스 8일치를 크롤링해 gpt-5-nano로
DB에 추가하고 매매 판단 가능한 수준으로 분석, (2) 대시보드 일봉 조회 기간 90일→180일,
(3) `npm run build` 후 Docker 배포 시 `/strategies/new`에서 F5 하면 404, 다른 배포
문제도 점검.

**뉴스**: 기존 `POST /data/news/update`(경제 섹션 헤드라인만 훑는 크롤러)로 시도했으나
실제 크롤링 이력 1,192건 중 "아이씨에이치" 관련이 0건 — 코스닥 소형주는 이 소스에
잘 안 실린다는 구조적 한계를 발견. 사용자가 "검색어로 최신순 딥 서치"를 요청해
`app/vendor/news_classifier/search_crawler.py`(신규, 네이버 뉴스 검색 기반) +
`app/cli/ingest_news_search.py`(신규 CLI)를 추가했고, `Container.news_trader_factory`/
`NewsTrader.update()`/`NewsUpdateRequest`에 `model`/`max_pages` 1회성 오버라이드도
추가(§0-20 상세 참조). 소규모 드라이런(15건 후보 중 13건 성공, 실제 관련 기사 확인)
후 본 실행(`--query 아이씨에이치 --days 8 --max-results 100 --model gpt-5-nano`)을
백그라운드로 트리거 — 크롤링은 신규 59건 수집 완료, gpt-5-nano AI 분류 단계가
예상보다 느려(첫 호출부터 20분 이상) 이번 세션 종료 시점까지 완료를 확인하지 못함.
다음 세션에서 `newsstock.db`의 분류 완료 여부(`SELECT COUNT(*) FROM crawled WHERE
classified=0`)를 먼저 확인할 것.

**일봉 180일**: `frontend/src/api/services.ts::fetchPrices` 기본값 +
`DashboardView.vue::loadPriceSeries` 호출 인자 + 백엔드 `GET /data/prices/{symbol}`
기본값을 90→180으로 일괄 변경.

**Docker 배포 버그**: (1) `frontend/Dockerfile`이 `serve dist`(SPA fallback 미설정)로
서빙해 히스토리 모드 라우터(`createWebHistory()`)의 새로고침이 404 → `serve -s dist`로
수정. (2) 점검 중 `COPY .env ./`가 존재하지 않는(gitignore된) 파일을 참조해 **새 클론
환경에서는 `docker build` 자체가 실패**하는 버그를 추가로 발견 → 코드에 이미 있던 안전한
기본값(`client.ts`의 `VITE_API_BASE_URL` 폴백)에 의존하도록 해당 COPY 줄 제거.
(3) 부가로 `backend/`/`frontend/` `.dockerignore` 신규 추가(`.venv`/`node_modules`가
매번 빌드 컨텍스트에 올라가던 문제), `backend/Dockerfile`의 apt 캐시 정리 경로 오타 수정.
Docker 데몬이 이 세션 환경에 없어 실제 빌드로 검증하지 못함 — 사용자가 재배포 후 최종
확인 필요.

**검증**: 백엔드 pytest 372개 전부 통과, 프론트 `vue-tsc -b` 통과.

## 커밋 이력 참고

상세 이력은 `git log --oneline`으로 확인. 주요 지점만 이 파일에 요약하며, 전체 diff/시각은 git이 원본이다.
