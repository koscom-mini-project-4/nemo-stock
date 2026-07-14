# nemo-stock backend (Phase 1)

설계 문서: `../DESIGN.md`

## 실행

```bash
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # 필요시 값 수정

./.venv/bin/uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://127.0.0.1:8000/docs
- 기본 계정: `admin` / `admin1234` (`.env`의 ADMIN_USERNAME/ADMIN_PASSWORD로 변경)

## 테스트

```bash
./.venv/bin/python -m pytest -q
```

## Phase 1 범위

- Node ABC + 레지스트리, 기본 노드 5종(scheduler.interval, data.price, indicator.moving_average, logic.if_else, execution.market_order)
- WorkflowGraph(위상정렬/검증) + WorkflowEngine(+EventBus)
- TriggerQueue(인메모리) + SchedulerService + WorkerPool(ThreadPoolExecutor)
- DAO(SQLite: users/workflows/runs/node_events) + 인메모리 구현체
- 더미 MarketDataProvider/OrderExecutionProvider
- API: /auth/login, /nodes, /workflows(CRUD/validate/run), /ws/runs/{run_id}
- 단일 계정 JWT 인증

AI, 백테스트, 공공데이터/DART 수집, Toss 어댑터, 프론트엔드는 `../DESIGN.md`의 Phase 2~6에서 이어서 구현한다.
