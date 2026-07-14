# nemo-stock frontend (Phase 5)

설계 문서: `../DESIGN.md` · 진행 상황: `../status.md`

## 실행

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

백엔드가 `http://localhost:8000`에서 실행 중이어야 한다(`../backend/README.md` 참조).
API 주소는 `.env.development`의 `VITE_API_BASE_URL`로 바꿀 수 있다.

## 주요 화면

- `/login` — 로그인(JWT)
- `/` — 대시보드(전략 목록)
- `/strategies/new`, `/strategies/:id` — 전략 빌더(Vue Flow 캔버스, 노드 팔레트, 속성/검증/디버그 패널)
- `/ai/generate` — 자연어 → AI 전략 초안 생성(위험고지 포함) → "캔버스에서 편집"으로 빌더에 반영
- `/backtests/new`, `/backtests/:id` — 백테스트 실행/결과(자산곡선 차트)

## 알려진 단순화

- 노드 좌표는 백엔드에 저장하지 않는다. 워크플로 로드/노드 추가 시마다 스케줄러 기준
  레이어드 레이아웃(`src/utils/layout.ts`)으로 자동 재배치한다(수동 드래그는 세션 내에서만 유지).
- "테스트 실행"의 노드별 하이라이트/디버그는 `POST /workflows/{id}/run`의 동기 응답(`events` 배열)을
  프론트에서 순차적으로 재생하는 방식이다(`src/api/ws.ts`에 `/ws/runs/{run_id}` 구독 유틸리티는
  준비되어 있으나, 활성화된 워크플로를 실시간 관전하는 라이브 모니터링 UI는 이번 Phase 범위 밖).
- 노드 추가는 팔레트 클릭 방식이며(드래그 앤 드롭 아님), 연결은 Vue Flow 기본 핸들 드래그로 만든다.
- 백테스트/테스트 실행에 필요한 시세 데이터는 `POST /data/ingest/prices/manual`(백엔드 API,
  현재 별도 UI 없음)로 미리 적재해야 한다.

## 브라우저 검증

Playwright(headless Chromium)로 로그인 → 대시보드 → 전략 생성(캔버스/팔레트/노드 추가/연결) →
저장 → 검증 → 테스트 실행(노드 하이라이트 애니메이션 + 디버그 패널) → AI 전략 생성 화면까지
실제로 구동해 확인했다(콘솔 에러 없음). 스크린샷은 세션 스크래치 디렉토리에만 저장되며 저장소에는
포함하지 않는다.
