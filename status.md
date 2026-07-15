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

## 커밋 이력 참고

상세 이력은 `git log --oneline`으로 확인. 주요 지점만 이 파일에 요약하며, 전체 diff/시각은 git이 원본이다.
