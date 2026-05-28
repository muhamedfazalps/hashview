#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DOCKER_PLATFORM="linux/amd64"

COMPOSE_BIN="${COMPOSE_BIN:-docker compose}"
BASE_URL="${HASHVIEW_E2E_BASE_URL:-http://127.0.0.1:5000}"
KEEP_CONTAINERS="${HASHVIEW_E2E_KEEP_CONTAINERS:-0}"

if [ ! -f hashview/config.conf ]; then
  echo "Writing hashview/config.conf for e2e (matches docker-compose.yml db credentials)..."
  cat > hashview/config.conf <<'EOF'
[SERVER]
SERVER_NAME = 127.0.0.1:5000
SECRET_KEY = e2e-test-secret-key

[database]
host = db
username = hashview
password = hashview

[SMTP]
server = smtp.example.com
port = 25
use_tls = False
username =
password =
default_sender =
EOF
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv and installing test deps from requirements-dev.txt..."
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements-dev.txt
fi
./.venv/bin/python -m playwright install

echo "Starting docker compose services..."
$COMPOSE_BIN up -d --build

cleanup() {
  if [ "$KEEP_CONTAINERS" = "1" ]; then
    echo "Keeping containers running (HASHVIEW_E2E_KEEP_CONTAINERS=1)."
  else
    echo "Stopping docker compose services..."
    $COMPOSE_BIN down -v
  fi
}
trap cleanup EXIT

echo "Waiting for app to respond at $BASE_URL ..."
for _ in {1..60}; do
  if curl -fsS "$BASE_URL/login" >/dev/null 2>&1; then
    echo "App is up."
    break
  fi
  sleep 2
done

if ! curl -fsS "$BASE_URL/login" >/dev/null 2>&1; then
  echo "App did not become ready in time."
  exit 1
fi

export HASHVIEW_E2E_BASE_URL="$BASE_URL"

echo "Running pytest against $BASE_URL"
set +e
./.venv/bin/python -m pytest -m e2e --ignore=tests/security -vv -s --maxfail=1
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -ne 0 ]; then
  echo "Pytest failed; printing recent docker logs..."
  $COMPOSE_BIN logs --tail 200
fi

exit "$TEST_EXIT"
