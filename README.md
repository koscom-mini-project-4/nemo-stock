# nemo-stock (네모네모매매) — 노코드 자동매매 전략 빌더 PoC

AI 가이드 기반 노코드 자동매매 전략 빌더의 PoC 구현. 기획 배경은 `nemo-stock.md`, 최초 구현
지시사항은 `prompt.md`, 기술 설계는 `DESIGN.md`, 진행 상황/의사결정 이력은 `status.md`를 참고한다.

이 저장소에서 작업하기 전에는 `CLAUDE.md`의 안내대로 `status.md` → `DESIGN.md` → `git log`
순서로 먼저 읽는다.

## 구성

- `backend/` — Python 3.12 + FastAPI. 노드 기반 워크플로 엔진, 트리거 큐/스케줄러/워커풀, 백테스트,
  AI(자연어 전략 초안 생성·뉴스/공시 감성 점수화), Toss증권 어댑터 스켈레톤. 상세: `backend/README.md`
- `frontend/` — Vue 3 + Vite + Vue Flow. 노드 캔버스 기반 전략 빌더, 테스트 실행 디버그 하이라이트,
  백테스트 결과, AI 전략 생성 화면. 상세: `frontend/README.md`

## 빠르게 실행하기

```bash
# 1. 백엔드
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # 필요시 값 수정(OPENAI_API_KEY 등)
./.venv/bin/uvicorn app.main:app --reload --port 8000

# 2. 프론트엔드 (다른 터미널)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

브라우저에서 `http://localhost:5173` 접속 → `admin` / `admin1234`(또는 `.env`에서 변경한 값)로 로그인.

## 테스트

```bash
cd backend && ./.venv/bin/python -m pytest -q
cd frontend && npx vue-tsc -b && npm run build
```

## 진행 상황

Phase 1(코어 실행 엔진) ~ Phase 6(통합 QA)까지 `DESIGN.md`에 정의된 로드맵을 순서대로 구현했다.
각 Phase의 상세 구현 내역, 확정된 의사결정, 알려진 단순화/한계는 `status.md`에 정리되어 있다.
