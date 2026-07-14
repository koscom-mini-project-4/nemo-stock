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
- [ ] **Phase 2 — 백테스트 + 공공데이터** (진행 예정/진행 중 — 아래 "다음 작업" 참조)
- [ ] **Phase 3 — AI 모듈** (자연어→워크플로 초안, DART 공시 점수화+캐시, 뉴스 감성)
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

### 다음 작업 (Phase 2)

1. `app/data_ingestion/public_data_price.py`: 공공데이터포털 금융위원회_주식시세정보 API 클라이언트 (서비스키는 `.env`의 `DATA_GO_KR_SERVICE_KEY`) → `PriceBarRepository`에 적재
2. `app/market_data/historical.py`: `HistoricalMarketDataProvider` (sqlite `price_bars` 리플레이)
3. `app/backtest/runner.py` + `metrics.py`: BacktestRunner(날짜 순회, WorkflowEngine 재사용) + 성과지표(CAGR/MDD/승률/손익비/거래횟수/자산곡선)
4. `backtest_results` 테이블/Repository, API: `POST /backtest`, `GET /backtest/{id}`
5. 테스트: 합성 가격 시계열로 백테스트 end-to-end, 지표 계산 유닛테스트

완료 후 `status.md` 갱신 + 커밋 → Phase 3로 진행.

## 커밋 이력 참고

상세 이력은 `git log --oneline`으로 확인. 주요 지점만 이 파일에 요약하며, 전체 diff/시각은 git이 원본이다.
