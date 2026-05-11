#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV_FILE="$ROOT_DIR/.env"
ROOT_ENV_EXAMPLE_FILE="$ROOT_DIR/.env.example"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=12
NODE_MIN_MAJOR=20

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="3000"
FRONTEND_PUBLIC_HOST="localhost"
PUBLIC_BACKEND_HOST="localhost"
AUTO_START_APPS="true"
LLM_MODEL="google/gemma-4-E4B-it"

log() {
  echo "[setup] $*"
}

warn() {
  echo "[setup][warn] $*" >&2
}

error() {
  echo "[setup][error] $*" >&2
  exit 1
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

has_display() {
  [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]
}

is_true() {
  local value="${1:-}"
  value="${value,,}"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" ]]
}

normalize_line_endings() {
  local file_path="$1"
  if [[ -f "$file_path" ]]; then
    sed -i 's/\r$//' "$file_path"
  fi
}

upsert_env_var() {
  local file_path="$1"
  local key="$2"
  local value="$3"

  if grep -qE "^${key}=" "$file_path"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file_path"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file_path"
  fi
}

ensure_root_env() {
  if [[ ! -f "$ROOT_ENV_FILE" ]]; then
    if [[ -f "$ROOT_ENV_EXAMPLE_FILE" ]]; then
      log "Tao .env tu .env.example"
      cp "$ROOT_ENV_EXAMPLE_FILE" "$ROOT_ENV_FILE"
    else
      error "Khong tim thay .env.example o root"
    fi
  fi

  normalize_line_endings "$ROOT_ENV_FILE"

  # shellcheck source=/dev/null
  source "$ROOT_ENV_FILE"

  BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  BACKEND_PORT="${BACKEND_PORT:-8000}"
  FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
  FRONTEND_PORT="${FRONTEND_PORT:-3000}"
  FRONTEND_PUBLIC_HOST="${FRONTEND_PUBLIC_HOST:-localhost}"
  PUBLIC_BACKEND_HOST="${PUBLIC_BACKEND_HOST:-localhost}"
  AUTO_START_APPS="${AUTO_START_APPS:-true}"
  LLM_MODEL="${LLM_MODEL:-google/gemma-4-E4B-it}"

  [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || error "BACKEND_PORT phai la so"
  [[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || error "FRONTEND_PORT phai la so"
}

detect_vllm_base_url() {
  local detected_host_port=""

  if has_cmd docker; then
    detected_host_port="$(
      docker ps --format '{{.Names}} {{.Ports}}' | \
        awk '/vllm/ && $0 ~ /->8000\/tcp/ {
          if (match($0, /([0-9]+)->8000\/tcp/, m)) {
            print m[1]
            exit
          }
        }'
    )"
  fi

  if [[ -n "$detected_host_port" ]]; then
    echo "http://localhost:${detected_host_port}/v1"
    return 0
  fi

  echo "http://localhost:8007/v1"
}

detect_searxng_base_url() {
  local detected_host_port=""

  if has_cmd docker; then
    detected_host_port="$(
      docker ps --format '{{.Names}} {{.Ports}}' | \
        awk '/searxng/ && $0 ~ /->8080\/tcp/ {
          if (match($0, /([0-9]+)->8080\/tcp/, m)) {
            print m[1]
            exit
          }
        }'
    )"
  fi

  if [[ -n "$detected_host_port" ]]; then
    echo "http://127.0.0.1:${detected_host_port}"
    return 0
  fi

  echo "https://searx.be"
}

build_cors_origins_json() {
  local host_candidate="$FRONTEND_HOST"
  local public_candidate="${FRONTEND_PUBLIC_HOST:-}"
  local origins=()
  local unique_origins=()
  local item

  origins+=("http://localhost:${FRONTEND_PORT}")
  origins+=("http://127.0.0.1:${FRONTEND_PORT}")

  if [[ -n "$public_candidate" ]]; then
    origins+=("http://${public_candidate}:${FRONTEND_PORT}")
  fi

  if [[ "$host_candidate" != "0.0.0.0" && "$host_candidate" != "localhost" && "$host_candidate" != "127.0.0.1" ]]; then
    origins+=("http://${host_candidate}:${FRONTEND_PORT}")
  fi

  for item in "${origins[@]}"; do
    if [[ ! " ${unique_origins[*]} " =~ " ${item} " ]]; then
      unique_origins+=("$item")
    fi
  done

  printf '['
  local index
  for index in "${!unique_origins[@]}"; do
    if [[ "$index" -gt 0 ]]; then
      printf ','
    fi
    printf '"%s"' "${unique_origins[$index]}"
  done
  printf ']'
}

python_meets_requirement() {
  local py_bin="$1"
  "$py_bin" - <<PY
import sys
ok = (sys.version_info.major, sys.version_info.minor) >= (${PYTHON_MIN_MAJOR}, ${PYTHON_MIN_MINOR})
raise SystemExit(0 if ok else 1)
PY
}

pick_python() {
  local candidate
  for candidate in python3.12 python3 python; do
    if has_cmd "$candidate" && python_meets_requirement "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

install_python_linux_apt() {
  if [[ "$(uname -s)" != "Linux" ]] || ! has_cmd apt-get; then
    return 1
  fi

  log "Python >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} not found. Trying apt-get install..."
  if has_cmd sudo; then
    sudo apt-get update
    sudo apt-get install -y python3.12 python3.12-venv python3-pip
  else
    apt-get update
    apt-get install -y python3.12 python3.12-venv python3-pip
  fi
}

ensure_python() {
  local py_bin
  if py_bin="$(pick_python)"; then
    echo "$py_bin"
    return 0
  fi

  if install_python_linux_apt; then
    if py_bin="$(pick_python)"; then
      echo "$py_bin"
      return 0
    fi
  fi

  error "Khong tim thay Python >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}. Hay cai dat Python roi chay lai setup.sh"
}

load_nvm_if_present() {
  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/.nvm/nvm.sh"
  fi
}

ensure_node() {
  local need_install="1"

  if has_cmd node; then
    local node_major
    node_major="$(node -p "process.versions.node.split('.')[0]")"
    if [[ "$node_major" -ge "$NODE_MIN_MAJOR" ]]; then
      need_install="0"
    else
      warn "Node hien tai v${node_major} < ${NODE_MIN_MAJOR}, se cai Node LTS qua nvm"
    fi
  fi

  if [[ "$need_install" == "0" ]]; then
    return 0
  fi

  if ! has_cmd curl; then
    error "Can curl de cai nvm/Node.js"
  fi

  if [[ ! -s "$HOME/.nvm/nvm.sh" ]]; then
    log "Dang cai nvm..."
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
  fi

  load_nvm_if_present
  if ! has_cmd nvm; then
    error "Khong load duoc nvm sau khi cai dat"
  fi

  log "Dang cai Node.js LTS qua nvm..."
  nvm install --lts
  nvm use --lts
}

ensure_npm() {
  if ! has_cmd npm; then
    error "Khong tim thay npm sau khi cai Node.js"
  fi
}

ensure_venv() {
  local py_bin="$1"
  local venv_python="$ROOT_DIR/.venv/bin/python"

  if [[ -x "$venv_python" ]]; then
    if "$venv_python" -c "import sys" >/dev/null 2>&1 && python_meets_requirement "$venv_python"; then
      log "Da tim thay .venv hop le"
      return 0
    fi

    warn ".venv hien tai khong hop le, se tao lai"
    rm -rf "$ROOT_DIR/.venv"
  fi

  log "Dang tao virtual environment tai $ROOT_DIR/.venv"
  "$py_bin" -m venv "$ROOT_DIR/.venv"
}

setup_backend() {
  local venv_python="$ROOT_DIR/.venv/bin/python"
  local backend_env="$ROOT_DIR/backend/.env"
  local llm_base_url
  local searxng_base_url
  local cors_origins

  log "Dang cai dependencies backend"
  "$venv_python" -m pip install --upgrade pip setuptools wheel
  (
    cd "$ROOT_DIR/backend"
    "$venv_python" -m pip install -e ".[dev]"
  )

  if [[ ! -f "$backend_env" ]]; then
    log "Tao backend/.env tu backend/.env.example"
    cp "$ROOT_DIR/backend/.env.example" "$backend_env"
  fi

  normalize_line_endings "$backend_env"

  llm_base_url="$(detect_vllm_base_url)"
  searxng_base_url="$(detect_searxng_base_url)"
  cors_origins="$(build_cors_origins_json)"
  upsert_env_var "$backend_env" "APP_CORS_ORIGINS" "$cors_origins"
  upsert_env_var "$backend_env" "APP_SEARXNG_BASE_URL" "$searxng_base_url"
  upsert_env_var "$backend_env" "APP_SEARXNG_BACKUP_BASE_URLS" ""
  upsert_env_var "$backend_env" "APP_LLM_ENABLED" "true"
  upsert_env_var "$backend_env" "APP_LLM_BASE_URL" "$llm_base_url"
  upsert_env_var "$backend_env" "APP_LLM_MODEL" "$LLM_MODEL"
  upsert_env_var "$backend_env" "APP_LLM_TEMPERATURE" "0.2"
  upsert_env_var "$backend_env" "APP_LLM_MAX_TOKENS" "280"
  log "Da cap nhat cau hinh LLM backend: APP_LLM_BASE_URL=$llm_base_url"

  if [[ ! -f "$ROOT_DIR/backend/config/tavily_keys.json" ]]; then
    log "Tao backend/config/tavily_keys.json"
    mkdir -p "$ROOT_DIR/backend/config"
    printf '[]\n' >"$ROOT_DIR/backend/config/tavily_keys.json"
  fi
}

setup_frontend() {
  local frontend_env_local="$ROOT_DIR/frontend/.env.local"
  local api_proxy_host

  log "Dang cai dependencies frontend"
  (
    cd "$ROOT_DIR/frontend"
    if [[ -f "package-lock.json" ]]; then
      npm ci
    else
      npm install
    fi
  )

  if [[ ! -f "$frontend_env_local" ]]; then
    log "Tao frontend/.env.local tu frontend/.env.example"
    cp "$ROOT_DIR/frontend/.env.example" "$frontend_env_local"
  fi

  normalize_line_endings "$frontend_env_local"
  if [[ "$BACKEND_HOST" == "0.0.0.0" || "$BACKEND_HOST" == "::" ]]; then
    api_proxy_host="127.0.0.1"
  else
    api_proxy_host="$BACKEND_HOST"
  fi

  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_API_BASE" "/api/v1"
  upsert_env_var "$frontend_env_local" "API_PROXY_HOST" "$api_proxy_host"
  upsert_env_var "$frontend_env_local" "API_PROXY_PORT" "$BACKEND_PORT"
}

open_command_in_terminal() {
  local title="$1"
  local command="$2"

  if has_cmd gnome-terminal; then
    gnome-terminal --title "$title" -- bash -lc "$command; exec bash" >/dev/null 2>&1 &
    return 0
  fi

  if has_cmd x-terminal-emulator; then
    x-terminal-emulator -T "$title" -e bash -lc "$command; exec bash" >/dev/null 2>&1 &
    return 0
  fi

  if has_cmd konsole; then
    konsole --new-tab -p tabtitle="$title" -e bash -lc "$command; exec bash" >/dev/null 2>&1 &
    return 0
  fi

  return 1
}

start_apps_in_two_terminals() {
  local venv_python="$ROOT_DIR/.venv/bin/python"
  local backend_cmd
  local frontend_cmd
  local backend_pid
  local frontend_pid

  if ! is_true "$AUTO_START_APPS"; then
    log "AUTO_START_APPS=false, bo qua buoc bat app"
    return 0
  fi

  backend_cmd="cd $ROOT_DIR/backend && $venv_python -m uvicorn src.main:app --reload --host $BACKEND_HOST --port $BACKEND_PORT"
  frontend_cmd="cd $ROOT_DIR/frontend && npm run dev -- --hostname $FRONTEND_HOST --port $FRONTEND_PORT"

  if has_display && open_command_in_terminal "web-agent-backend" "$backend_cmd" && open_command_in_terminal "web-agent-frontend" "$frontend_cmd"; then
    log "Da mo 2 terminal cho backend va frontend"
    return 0
  fi

  if has_cmd tmux; then
    tmux has-session -t web-agent-backend 2>/dev/null && tmux kill-session -t web-agent-backend
    tmux has-session -t web-agent-frontend 2>/dev/null && tmux kill-session -t web-agent-frontend
    tmux new-session -d -s web-agent-backend "$backend_cmd"
    tmux new-session -d -s web-agent-frontend "$frontend_cmd"
    warn "Khong mo duoc GUI terminal, da chay bang tmux sessions: web-agent-backend, web-agent-frontend"
    return 0
  fi

  mkdir -p "$ROOT_DIR/logs"
  nohup bash -lc "$backend_cmd" >"$ROOT_DIR/logs/backend.dev.log" 2>&1 &
  backend_pid=$!
  nohup bash -lc "$frontend_cmd" >"$ROOT_DIR/logs/frontend.dev.log" 2>&1 &
  frontend_pid=$!

  warn "Khong mo duoc 2 terminal, da chay background"
  warn "backend pid=$backend_pid, frontend pid=$frontend_pid"
  warn "logs: logs/backend.dev.log va logs/frontend.dev.log"
}

print_summary() {
  local venv_python="$ROOT_DIR/.venv/bin/python"

  log "Setup hoan tat"
  echo
  echo "Python: $($venv_python --version 2>&1)"
  echo "Node: $(node --version)"
  echo "npm: $(npm --version)"
  echo
  echo "Ports tu root .env:"
  echo "  BACKEND_HOST=$BACKEND_HOST"
  echo "  BACKEND_PORT=$BACKEND_PORT"
  echo "  FRONTEND_HOST=$FRONTEND_HOST"
  echo "  FRONTEND_PORT=$FRONTEND_PORT"
  echo
  echo "Chay backend:"
  echo "  cd backend"
  echo "  $venv_python -m uvicorn src.main:app --reload --host $BACKEND_HOST --port $BACKEND_PORT"
  echo
  echo "Chay frontend:"
  echo "  cd frontend"
  echo "  npm run dev -- --hostname $FRONTEND_HOST --port $FRONTEND_PORT"
}

main() {
  log "Bat dau setup du an"

  ensure_root_env

  local py_bin
  py_bin="$(ensure_python)"
  log "Su dung Python: $py_bin"

  ensure_node
  ensure_npm

  ensure_venv "$py_bin"
  setup_backend
  setup_frontend
  print_summary
  start_apps_in_two_terminals
}

main "$@"
