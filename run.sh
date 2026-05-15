#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV_FILE="$ROOT_DIR/.env"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8011"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="3005"

log() {
  echo "[run] $*"
}

warn() {
  echo "[run][warn] $*" >&2
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

load_env() {
  if [[ -f "$ROOT_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ROOT_ENV_FILE"
  fi
  BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  BACKEND_PORT="${BACKEND_PORT:-8011}"
  FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
  FRONTEND_PORT="${FRONTEND_PORT:-3005}"
}

venv_python_path() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "$ROOT_DIR/.venv/bin/python"
    return 0
  fi
  if [[ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
    echo "$ROOT_DIR/.venv/Scripts/python.exe"
    return 0
  fi
  echo ""
}

is_pid_running() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
}

load_nvm_if_present() {
  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    local had_nounset="0"
    if [[ $- == *u* ]]; then
      had_nounset="1"
      set +u
    fi
    # shellcheck source=/dev/null
    source "$HOME/.nvm/nvm.sh"
    if [[ "$had_nounset" == "1" ]]; then
      set -u
    fi
  fi
}

start_backend() {
  local venv_python="$1"
  local backend_log="$LOG_DIR/backend.dev.log"

  if [[ -f "$BACKEND_PID_FILE" ]] && is_pid_running "$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"; then
    warn "Backend dang chay (pid=$(cat "$BACKEND_PID_FILE")). Bo qua."
    return 0
  fi

  nohup bash -lc "cd \"$ROOT_DIR/backend\" && \"$venv_python\" -m uvicorn src.main:app --reload --host \"$BACKEND_HOST\" --port \"$BACKEND_PORT\"" \
    >"$backend_log" 2>&1 &
  local pid=$!
  echo "$pid" >"$BACKEND_PID_FILE"
  log "Backend started pid=$pid log=$backend_log"
}

start_frontend() {
  local frontend_log="$LOG_DIR/frontend.dev.log"

  if [[ -f "$FRONTEND_PID_FILE" ]] && is_pid_running "$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"; then
    warn "Frontend dang chay (pid=$(cat "$FRONTEND_PID_FILE")). Bo qua."
    return 0
  fi

  nohup bash -lc "cd \"$ROOT_DIR/frontend\"; export NVM_DIR=\"$HOME/.nvm\"; if [ -s \"$HOME/.nvm/nvm.sh\" ]; then source \"$HOME/.nvm/nvm.sh\"; fi; npm run dev -- --hostname \"$FRONTEND_HOST\" --port \"$FRONTEND_PORT\"" \
    >"$frontend_log" 2>&1 &
  local pid=$!
  echo "$pid" >"$FRONTEND_PID_FILE"
  log "Frontend started pid=$pid log=$frontend_log"
}

main() {
  mkdir -p "$LOG_DIR"
  load_env

  local venv_python
  venv_python="$(venv_python_path)"
  if [[ -z "$venv_python" ]]; then
    echo "[run][error] Khong tim thay Python trong .venv. Hay chay ./setup.sh truoc." >&2
    exit 1
  fi

  load_nvm_if_present
  if ! has_cmd npm; then
    echo "[run][error] Khong tim thay npm. Hay nap nvm hoac chay ./setup.sh truoc." >&2
    exit 1
  fi

  start_backend "$venv_python"
  start_frontend

  echo
  echo "Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
  echo "Frontend: http://localhost:$FRONTEND_PORT"
  echo "Logs:     $LOG_DIR/backend.dev.log, $LOG_DIR/frontend.dev.log"
}

main "$@"
