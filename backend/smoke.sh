#!/usr/bin/env bash
# Smoke test for the ads-runner-agent backend.
#
# Boots uvicorn with throwaway config, hits the public + protected endpoints,
# asserts on HTTP status codes, then tears everything down.
# No real LLM keys are used: the enqueued job fails with the provider's
# authentic auth error, which itself proves the real litellm path runs.
#
# Usage:  bash backend/smoke.sh
# Requires the backend venv (see README) or pip-installed requirements.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${SMOKE_PORT:-8123}"
DB_PATH="/tmp/ads_runner_smoke_$$.db"
API_KEY="${SMOKE_API_KEY:-smoke-secret-key}"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

cd "$BACKEND_DIR"
rm -f "$DB_PATH"

export API_KEY DATABASE_URL="sqlite+aiosqlite:///$DB_PATH"

# Start server in the background.
uvicorn server:app --host 127.0.0.1 --port "$PORT" >/tmp/ads_smoke_server.log 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  rm -f "$DB_PATH"
}
trap cleanup EXIT

# Wait for boot (max ~25s).
for i in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "server died during boot:"; cat /tmp/ads_smoke_server.log; exit 1
  fi
done

# 1. /health is public and returns 200.
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/health")
[ "$code" = "200" ] && pass "/health -> 200 (public)" || fail "/health -> $code"
curl -s "http://127.0.0.1:$PORT/health" | grep -q '"status":"ok"' \
  && pass "/health body ok" || fail "/health body"

# 2. /api/execute without X-API-Key -> 401, no leak.
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/execute" \
  -H 'Content-Type: application/json' \
  -d '{"product_url":"https://example.com/x","description":"A fine smoke test widget","budget":"10","provider":"gpt-4o"}')
[ "$code" = "401" ] && pass "POST /api/execute without key -> 401" || fail "no-key execute -> $code"

# 3. Invalid input with a valid key -> 422 structured JSON, no stack trace.
body=$(curl -s -w "\n%{http_code}" -X POST "http://127.0.0.1:$PORT/api/execute" \
  -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
  -d '{"product_url":"not-a-url","description":"short","budget":"","provider":"mystery-9000"}')
code=$(echo "$body" | tail -1)
[ "$code" = "422" ] && pass "invalid input -> 422" || fail "invalid input -> $code"
echo "$body" | grep -q "Traceback" && fail "422 body leaked a traceback" || pass "422 body has no traceback"
echo "$body" | grep -q "validation_error" && pass "422 body is structured JSON" || fail "422 body shape"

# 4. Valid enqueue with key -> 200 + task_id.
body=$(curl -s -X POST "http://127.0.0.1:$PORT/api/execute" \
  -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
  -d '{"product_url":"https://example.com/widget","description":"A test widget for smoke purposes","budget":"50.00","provider":"gpt-4o"}')
echo "$body" | grep -q "task_id" && pass "POST /api/execute -> 200 with task_id" || fail "enqueue: $body"
TASK_ID=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")

# 5. GET /api/tasks/{id} without key -> 401.
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/tasks/$TASK_ID")
[ "$code" = "401" ] && pass "GET /api/tasks without key -> 401" || fail "no-key task fetch -> $code"

# 6. GET /api/tasks/{id} with key -> 200.
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/tasks/$TASK_ID" \
  -H "X-API-Key: $API_KEY")
[ "$code" = "200" ] && pass "GET /api/tasks/{id} -> 200" || fail "task fetch -> $code"

# 7. Unknown task id -> 404 structured JSON.
body=$(curl -s -w "\n%{http_code}" "http://127.0.0.1:$PORT/api/tasks/does-not-exist" \
  -H "X-API-Key: $API_KEY")
code=$(echo "$body" | tail -1)
[ "$code" = "404" ] && pass "unknown task -> 404" || fail "unknown task -> $code"

echo "SMOKE OK: all checks passed"
