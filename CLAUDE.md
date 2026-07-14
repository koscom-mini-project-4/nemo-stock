# nemo-stock 작업 지침

이 저장소에서 작업을 시작하기 전에 **반드시 아래 순서로 먼저 읽는다**. 건너뛰지 말 것.

1. `status.md` — 현재까지 진행 상황, 완료/미완료 Phase, 최근 결정 사항, 다음 작업.
2. `DESIGN.md` — 전체 아키텍처/설계 확정 사항. 코드는 이 문서를 기준으로 작성한다. 설계를 벗어나는 변경을 할 경우 `DESIGN.md`도 함께 갱신한다.
3. `git log --oneline -20` (필요시 `git log -p`로 최근 커밋 상세) — 최근에 실제로 무엇이 바뀌었는지 코드/커밋 기준으로 확인한다. `status.md`가 최신화되지 않았을 수 있으므로 git log와 대조해 불일치가 있으면 `status.md`를 신뢰하지 말고 실제 코드/로그를 우선한다.

## 작업 규칙

- 모든 작업은 git으로 관리한다. 의미 있는 단위(Phase 완료, 주요 기능 추가)마다 커밋한다.
- 각 Phase(또는 주요 작업) 완료 시 `status.md`를 갱신한 뒤 커밋한다. 코드 변경과 `status.md` 갱신은 가능한 한 함께 커밋한다.
- `nemo-stock.md`(사업 기획서)와 `prompt.md`(최초 구현 지시사항)는 변경하지 않는다(참조 전용).
- 확정되지 않은 요구사항이 생기면 `DESIGN.md` §0 결정 이력에 준하는 방식으로 사용자에게 확인 후 `status.md`/`DESIGN.md`에 기록한다. 이미 확정된 설계 범위 내 구현 중에는 불필요하게 재질문하지 않는다.
- 백엔드는 `backend/.venv`(Python 3.12)를 사용한다. 의존성 변경 시 `backend/pyproject.toml`을 갱신하고 `pip install -e ".[dev]"`로 재설치한다.
- 테스트: `cd backend && ./.venv/bin/python -m pytest -q`. 커밋 전 반드시 통과 확인.
