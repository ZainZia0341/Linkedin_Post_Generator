#!/usr/bin/env bash
set -euo pipefail

STREAMLIT_PORT="${STREAMLIT_PORT:-7860}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
DYNAMODB_PORT="${DYNAMODB_PORT:-8000}"

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-dummy}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-dummy}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"
export DYNAMODB_ENDPOINT_URL="${DYNAMODB_ENDPOINT_URL:-http://127.0.0.1:${DYNAMODB_PORT}}"
export LINKEDIN_API_BASE_URL="${LINKEDIN_API_BASE_URL:-http://127.0.0.1:${API_PORT}}"

if [[ -z "${DYNAMODB_DB_DIR:-}" ]]; then
    if [[ -d /data && -w /data ]]; then
        DYNAMODB_DB_DIR="/data/dynamodb"
    else
        DYNAMODB_DB_DIR="/tmp/dynamodb"
    fi
fi

mkdir -p "${DYNAMODB_DB_DIR}"

echo "Starting DynamoDB Local on port ${DYNAMODB_PORT}; db dir: ${DYNAMODB_DB_DIR}"
java \
    -Djava.library.path=/opt/dynamodb-local/DynamoDBLocal_lib \
    -jar /opt/dynamodb-local/DynamoDBLocal.jar \
    -sharedDb \
    -dbPath "${DYNAMODB_DB_DIR}" \
    -port "${DYNAMODB_PORT}" &
DYNAMODB_PID=$!

wait_for_port() {
    local host="$1"
    local port="$2"
    local name="$3"
    python - "$host" "$port" "$name" <<'PY'
import socket
import sys
import time

host, port, name = sys.argv[1], int(sys.argv[2]), sys.argv[3]
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1):
            print(f"{name} is ready on {host}:{port}")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"{name} did not become ready on {host}:{port}")
PY
}

wait_for_port "127.0.0.1" "${DYNAMODB_PORT}" "DynamoDB Local"

echo "Starting FastAPI on ${API_HOST}:${API_PORT}"
uv run uvicorn app.api.main:app --host "${API_HOST}" --port "${API_PORT}" &
API_PID=$!

wait_for_port "${API_HOST}" "${API_PORT}" "FastAPI"

echo "Starting Streamlit on 0.0.0.0:${STREAMLIT_PORT}"
uv run streamlit run streamlit_ui/app.py \
    --server.address 0.0.0.0 \
    --server.port "${STREAMLIT_PORT}" \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

shutdown() {
    echo "Stopping app services..."
    kill "${STREAMLIT_PID}" "${API_PID}" "${DYNAMODB_PID}" 2>/dev/null || true
}
trap shutdown INT TERM EXIT

wait -n "${STREAMLIT_PID}" "${API_PID}" "${DYNAMODB_PID}"
