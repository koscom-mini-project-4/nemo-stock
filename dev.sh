#!/usr/bin/env bash
# 백엔드(uvicorn) + 프론트엔드(vite)를 한 번에 띄우고, 프론트 URL을 Chrome으로 연다.
# 프론트가 VITE_API_BASE_URL=http://localhost:8000으로 고정되어 있어 백엔드는 반드시
# 8000번 포트로 떠야 한다(nemo-poc처럼 임의 포트 불가). Ctrl+C 한 번으로 둘 다 정리된다.

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT=8000
BACKEND_LOG="$ROOT/.dev-backend.log"
FRONTEND_LOG="$ROOT/.dev-frontend.log"

BACKEND_PID=""
FRONTEND_PID=""
FRONTEND_PORT=""

cleanup() {
  echo ""
  echo "정리 중..."
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  # npm/uvicorn --reload는 자식 프로세스를 따로 띄우므로 포트 기준으로도 정리한다.
  [[ -n "$FRONTEND_PORT" ]] && lsof -ti:"$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
  lsof -ti:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
  echo "dev servers stopped."
}
trap cleanup EXIT INT TERM

if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
  echo "backend/.venv가 없습니다. 먼저 아래로 가상환경을 만드세요:"
  echo "  cd backend && python3 -m venv .venv && ./.venv/bin/pip install -e '.[dev]'"
  exit 1
fi

# 프론트가 8000번 고정이라, 이미 그 포트를 쓰고 있는 프로세스가 있으면 충돌한다.
if lsof -ti:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "포트 $BACKEND_PORT 가 이미 사용 중입니다. 기존 프로세스를 정리한 뒤 다시 실행하세요:"
  echo "  lsof -ti:$BACKEND_PORT -sTCP:LISTEN | xargs kill"
  exit 1
fi

echo "[1/3] backend 기동 중 (uvicorn :$BACKEND_PORT)..."
(cd "$BACKEND_DIR" && ./.venv/bin/uvicorn app.main:app --reload --port "$BACKEND_PORT") > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for i in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1 && break
  sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo "backend가 뜨지 않았습니다. 로그 확인: $BACKEND_LOG"
    exit 1
  fi
done
echo "    backend up (pid $BACKEND_PID)"

echo "[2/3] frontend 기동 중 (vite dev)..."
(cd "$FRONTEND_DIR" && npm run dev) > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

FRONTEND_URL=""
for i in $(seq 1 30); do
  FRONTEND_URL=$(grep -oE 'http://localhost:[0-9]+' "$FRONTEND_LOG" 2>/dev/null | head -1 || true)
  [[ -n "$FRONTEND_URL" ]] && break
  sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo "frontend URL을 찾지 못했습니다. 로그 확인: $FRONTEND_LOG"
    exit 1
  fi
done
FRONTEND_PORT="${FRONTEND_URL##*:}"
echo "    frontend up at $FRONTEND_URL (pid $FRONTEND_PID)"

echo "[3/3] Chrome으로 열기..."
open -a "Google Chrome" "$FRONTEND_URL"

echo ""
echo "backend  log: $BACKEND_LOG"
echo "frontend log: $FRONTEND_LOG"
echo "로그인 계정은 backend/.env의 ADMIN_USERNAME/ADMIN_PASSWORD 참고"
echo "종료하려면 Ctrl+C"
wait
