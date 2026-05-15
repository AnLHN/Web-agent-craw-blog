#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV_FILE="$ROOT_DIR/.env"
ROOT_ENV_EXAMPLE_FILE="$ROOT_DIR/.env.example"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=12
NODE_MIN_MAJOR=20

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8011"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="3005"
FRONTEND_PUBLIC_HOST="localhost"
PUBLIC_BACKEND_HOST="localhost"
AUTO_START_APPS="true"
LLM_MODEL="google/gemma-4-E4B-it"
LLM_BASE_URL=""
FEATURE_SESSION_HISTORY="true"
FEATURE_OPS_DASHBOARD="true"
FEATURE_LLM_RUNTIME_CONFIG="true"
RBAC_ENABLED="false"
RBAC_ADMIN_TOKEN=""
OPS_ROLE="admin"
OPS_ADMIN_TOKEN=""
POSTGRES_AUTO_START="false"
POSTGRES_CONTAINER_NAME="websearch-pg"
POSTGRES_FORCE_RECREATE="false"
POSTGRES_PORT="5432"
POSTGRES_DB="web_search"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="postgres"
PGADMIN_AUTO_START="false"
PGADMIN_CONTAINER_NAME="websearch-pgadmin"
PGADMIN_PORT="5050"
PGADMIN_DEFAULT_EMAIL="admin@local.dev"
PGADMIN_DEFAULT_PASSWORD="admin"
SEARXNG_AUTO_START="false"
SEARXNG_CONTAINER_NAME="websearch-searxng"
SEARXNG_FORCE_RECREATE="false"
SEARXNG_PORT="8080"

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

docker_container_exists() {
  local name="$1"
  docker container inspect "$name" >/dev/null 2>&1
}

docker_container_running() {
  local name="$1"
  local running
  running="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)"
  [[ "$running" == "true" ]]
}

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

extract_env_value() {
  local file_path="$1"
  local key="$2"
  local value=""
  if [[ -f "$file_path" ]]; then
    value="$(sed -n "s/^${key}=//p" "$file_path" | tail -n 1)"
  fi
  echo "$value"
}

postgres_reachable() {
  local venv_python="$1"
  local database_url="$2"
  if [[ -z "$database_url" ]]; then
    return 1
  fi
  "$venv_python" - <<PY >/dev/null 2>&1
import psycopg
import time
url = """$database_url""".strip()
if url.startswith("postgresql+psycopg://"):
    url = "postgresql://" + url[len("postgresql+psycopg://"):]
for _ in range(10):
    try:
        psycopg.connect(url).close()
        raise SystemExit(0)
    except Exception:
        time.sleep(1)
raise SystemExit(1)
PY
}

ensure_postgres_if_enabled() {
  local backend_mode="$1"

  if ! is_true "$POSTGRES_AUTO_START"; then
    return 0
  fi

  if [[ "$backend_mode" == "local" ]]; then
    log "Session store dang local, bo qua auto-start PostgreSQL"
    return 0
  fi

  if ! has_cmd docker; then
    warn "POSTGRES_AUTO_START=true nhung khong co docker. Bo qua auto-start PostgreSQL."
    return 0
  fi

  if is_true "$POSTGRES_FORCE_RECREATE"; then
    if docker_container_exists "$POSTGRES_CONTAINER_NAME"; then
      log "POSTGRES_FORCE_RECREATE=true, dang xoa container cu: $POSTGRES_CONTAINER_NAME"
      docker rm -f "$POSTGRES_CONTAINER_NAME" >/dev/null
    fi
  fi

  if docker_container_running "$POSTGRES_CONTAINER_NAME"; then
    log "PostgreSQL container dang chay: $POSTGRES_CONTAINER_NAME"
    return 0
  fi

  if docker_container_exists "$POSTGRES_CONTAINER_NAME"; then
    log "Dang start lai PostgreSQL container: $POSTGRES_CONTAINER_NAME"
    docker start "$POSTGRES_CONTAINER_NAME" >/dev/null
  else
    log "Dang tao PostgreSQL container: $POSTGRES_CONTAINER_NAME"
    docker run --name "$POSTGRES_CONTAINER_NAME" \
      -e "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
      -e "POSTGRES_USER=$POSTGRES_USER" \
      -e "POSTGRES_DB=$POSTGRES_DB" \
      -p "$POSTGRES_PORT:5432" \
      -d postgres:16 >/dev/null
  fi

  # doi DB ready toi da 20s
  local i
  for i in {1..20}; do
    if docker exec "$POSTGRES_CONTAINER_NAME" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
      log "PostgreSQL da san sang ket noi"
      return 0
    fi
    sleep 1
  done
  warn "PostgreSQL container da start nhung chua ready trong 20s"
}

ensure_pgadmin_if_enabled() {
  local backend_mode="$1"

  if ! is_true "$PGADMIN_AUTO_START"; then
    return 0
  fi

  if [[ "$backend_mode" == "local" ]]; then
    log "Session store dang local, bo qua auto-start pgAdmin"
    return 0
  fi

  if ! has_cmd docker; then
    warn "PGADMIN_AUTO_START=true nhung khong co docker. Bo qua auto-start pgAdmin."
    return 0
  fi

  if docker_container_running "$PGADMIN_CONTAINER_NAME"; then
    log "pgAdmin container dang chay: $PGADMIN_CONTAINER_NAME"
    return 0
  fi

  if docker_container_exists "$PGADMIN_CONTAINER_NAME"; then
    log "Dang start lai pgAdmin container: $PGADMIN_CONTAINER_NAME"
    docker start "$PGADMIN_CONTAINER_NAME" >/dev/null
  else
    log "Dang tao pgAdmin container: $PGADMIN_CONTAINER_NAME"
    docker run --name "$PGADMIN_CONTAINER_NAME" \
      -e "PGADMIN_DEFAULT_EMAIL=$PGADMIN_DEFAULT_EMAIL" \
      -e "PGADMIN_DEFAULT_PASSWORD=$PGADMIN_DEFAULT_PASSWORD" \
      -e "PGADMIN_CONFIG_ENHANCED_COOKIE_PROTECTION=False" \
      -p "$PGADMIN_PORT:80" \
      -d dpage/pgadmin4:8 >/dev/null
  fi
}

ensure_searxng_if_enabled() {
  local searxng_config_dir="$ROOT_DIR/config/searxng"
  local searxng_settings_file="$searxng_config_dir/settings.yml"
  local searxng_mount_source="$searxng_config_dir"

  if ! is_true "$SEARXNG_AUTO_START"; then
    return 0
  fi

  if ! has_cmd docker; then
    warn "SEARXNG_AUTO_START=true nhung khong co docker. Se fallback public SearXNG neu co."
    return 0
  fi

  mkdir -p "$searxng_config_dir"
  cat >"$searxng_settings_file" <<EOF
use_default_settings: true

general:
  instance_name: "web-agent-searxng"

search:
  formats:
    - html
    - json

server:
  bind_address: "0.0.0.0"
  port: 8080
  base_url: "http://127.0.0.1:$SEARXNG_PORT/"
  limiter: false
  public_instance: false
  secret_key: "web-agent-local-dev-secret"
  method: "GET"
EOF

  if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
    if has_cmd cygpath; then
      searxng_mount_source="$(cygpath -w "$searxng_config_dir")"
    fi
  fi

  if is_true "$SEARXNG_FORCE_RECREATE"; then
    if docker_container_exists "$SEARXNG_CONTAINER_NAME"; then
      log "SEARXNG_FORCE_RECREATE=true, dang xoa container cu: $SEARXNG_CONTAINER_NAME"
      docker rm -f "$SEARXNG_CONTAINER_NAME" >/dev/null
    fi
  fi

  if docker_container_running "$SEARXNG_CONTAINER_NAME"; then
    log "SearXNG container dang chay: $SEARXNG_CONTAINER_NAME"
  elif docker_container_exists "$SEARXNG_CONTAINER_NAME"; then
    log "Dang start lai SearXNG container: $SEARXNG_CONTAINER_NAME"
    docker start "$SEARXNG_CONTAINER_NAME" >/dev/null
  else
    log "Dang tao SearXNG container: $SEARXNG_CONTAINER_NAME"
    MSYS_NO_PATHCONV=1 docker run --name "$SEARXNG_CONTAINER_NAME" \
      -e "BASE_URL=http://127.0.0.1:$SEARXNG_PORT/" \
      -e "INSTANCE_NAME=web-agent-searxng" \
      -v "$searxng_mount_source:/etc/searxng:ro" \
      -p "$SEARXNG_PORT:8080" \
      -d searxng/searxng:latest >/dev/null
  fi

  local i
  for i in {1..30}; do
    if curl -fsS "http://127.0.0.1:$SEARXNG_PORT/search?q=health&format=json" >/dev/null 2>&1; then
      log "SearXNG da san sang ket noi"
      return 0
    fi
    sleep 1
  done
  warn "SearXNG container da start nhung chua ready trong 30s"
}

maybe_configure_postgres_session_store() {
  local venv_python="$1"
  local backend_env="$2"
  local backend_mode
  local database_url

  backend_mode="$(extract_env_value "$backend_env" "APP_SESSION_STORE_BACKEND")"
  database_url="$(extract_env_value "$backend_env" "APP_DATABASE_URL")"
  backend_mode="${backend_mode:-auto}"

  ensure_postgres_if_enabled "$backend_mode"
  ensure_pgadmin_if_enabled "$backend_mode"

  if [[ "$backend_mode" == "local" ]]; then
    log "Session store dang o che do local (APP_SESSION_STORE_BACKEND=local)"
    return 0
  fi

  if postgres_reachable "$venv_python" "$database_url"; then
    log "Da ket noi duoc PostgreSQL, tien hanh migrate schema"
    (
      cd "$ROOT_DIR/backend"
      "$venv_python" -m alembic upgrade head
    )
    log "Migration PostgreSQL hoan tat"
    return 0
  fi

  if [[ "$backend_mode" == "postgres" ]]; then
    error "APP_SESSION_STORE_BACKEND=postgres nhung khong ket noi duoc PostgreSQL. Kiem tra APP_DATABASE_URL hoac trang thai DB."
  fi

  warn "Khong ket noi duoc PostgreSQL qua APP_DATABASE_URL hien tai"
  warn "Tu dong fallback ve local JSON de setup khong bi dung"
  upsert_env_var "$backend_env" "APP_SESSION_STORE_BACKEND" "local"
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
  echo "$ROOT_DIR/.venv/bin/python"
}

has_display() {
  [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]
}

is_true() {
  local value="${1:-}"
  value="${value,,}"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" ]]
}

stop_listeners_on_port_windows() {
  local port="$1"
  if has_cmd powershell || has_cmd pwsh; then
    local ps_cmd="powershell"
    if has_cmd pwsh; then
      ps_cmd="pwsh"
    fi
    "$ps_cmd" -NoProfile -Command "\
      for (\$i = 0; \$i -lt 5; \$i++) { \
        \$pids = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { \$_ -and \$_ -ne 0 }); \
        if (-not \$pids -or \$pids.Count -eq 0) { break } \
        foreach (\$p in \$pids) { \
          try { Stop-Process -Id \$p -Force -ErrorAction Stop } catch { try { & taskkill.exe /F /T /PID \$p | Out-Null } catch {} } \
        } \
        Start-Sleep -Milliseconds 600 \
      }" >/dev/null 2>&1 || true
  fi
}

list_listeners_on_port_windows() {
  local port="$1"
  if has_cmd powershell || has_cmd pwsh; then
    local ps_cmd="powershell"
    if has_cmd pwsh; then
      ps_cmd="pwsh"
    fi
    "$ps_cmd" -NoProfile -Command "\
      @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { \$_ -and \$_ -ne 0 }) -join ','" 2>/dev/null || true
  fi
}

ensure_port_free_windows() {
  local port="$1"
  local label="$2"
  stop_listeners_on_port_windows "$port"
  local remaining
  remaining="$(list_listeners_on_port_windows "$port")"
  if [[ -n "$remaining" ]]; then
    error "Port $port cho $label van bi giu boi PID(s): $remaining. Neu PID khong ton tai/khong kill duoc, chay PowerShell Admin: Restart-Service WinNat -Force"
  fi
}

cleanup_existing_processes() {
  log "Dang don cac process cu cua project neu co"

  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
    if is_pid_running "$pid"; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.3
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$BACKEND_PID_FILE"
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
    if is_pid_running "$pid"; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.3
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi

  if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
    if has_cmd powershell || has_cmd pwsh; then
      local ps_script
      local ps_cmd="powershell"
      if has_cmd pwsh; then
        ps_cmd="pwsh"
      fi
      ps_script='Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -match "WebSearch_Tavily\\web-agent" -and $_.Name -match "python|node|npm|uvicorn") -or ($_.Name -eq "python.exe" -and $_.CommandLine -match "multiprocessing-fork" -and $_.CommandLine -match "spawn_main") } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }'
      "$ps_cmd" -NoProfile -Command "$ps_script" >/dev/null 2>&1 || true
    fi
    ensure_port_free_windows "$BACKEND_PORT" "backend"
    ensure_port_free_windows "$FRONTEND_PORT" "frontend"
    return 0
  fi

  if has_cmd pkill; then
    pkill -f "uvicorn src.main:app" >/dev/null 2>&1 || true
    pkill -f "next dev" >/dev/null 2>&1 || true
    pkill -f "$ROOT_DIR/frontend" >/dev/null 2>&1 || true
    pkill -f "$ROOT_DIR/backend" >/dev/null 2>&1 || true
  fi
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
  BACKEND_PORT="${BACKEND_PORT:-8011}"
  FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
  FRONTEND_PORT="${FRONTEND_PORT:-3005}"
  FRONTEND_PUBLIC_HOST="${FRONTEND_PUBLIC_HOST:-localhost}"
  PUBLIC_BACKEND_HOST="${PUBLIC_BACKEND_HOST:-localhost}"
  AUTO_START_APPS="${AUTO_START_APPS:-true}"
  LLM_MODEL="${LLM_MODEL:-google/gemma-4-E4B-it}"
  LLM_BASE_URL="${LLM_BASE_URL:-}"
  FEATURE_SESSION_HISTORY="${FEATURE_SESSION_HISTORY:-true}"
  FEATURE_OPS_DASHBOARD="${FEATURE_OPS_DASHBOARD:-true}"
  FEATURE_LLM_RUNTIME_CONFIG="${FEATURE_LLM_RUNTIME_CONFIG:-true}"
  RBAC_ENABLED="${RBAC_ENABLED:-false}"
  RBAC_ADMIN_TOKEN="${RBAC_ADMIN_TOKEN:-}"
  OPS_ROLE="${OPS_ROLE:-admin}"
  OPS_ADMIN_TOKEN="${OPS_ADMIN_TOKEN:-}"
  POSTGRES_AUTO_START="${POSTGRES_AUTO_START:-false}"
  POSTGRES_CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-websearch-pg}"
  POSTGRES_FORCE_RECREATE="${POSTGRES_FORCE_RECREATE:-false}"
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  POSTGRES_DB="${POSTGRES_DB:-web_search}"
  POSTGRES_USER="${POSTGRES_USER:-postgres}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
  PGADMIN_AUTO_START="${PGADMIN_AUTO_START:-false}"
  PGADMIN_CONTAINER_NAME="${PGADMIN_CONTAINER_NAME:-websearch-pgadmin}"
  PGADMIN_PORT="${PGADMIN_PORT:-5050}"
  PGADMIN_DEFAULT_EMAIL="${PGADMIN_DEFAULT_EMAIL:-admin@local.dev}"
  PGADMIN_DEFAULT_PASSWORD="${PGADMIN_DEFAULT_PASSWORD:-admin}"
  SEARXNG_AUTO_START="${SEARXNG_AUTO_START:-false}"
  SEARXNG_CONTAINER_NAME="${SEARXNG_CONTAINER_NAME:-websearch-searxng}"
  SEARXNG_FORCE_RECREATE="${SEARXNG_FORCE_RECREATE:-false}"
  SEARXNG_PORT="${SEARXNG_PORT:-8080}"

  [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || error "BACKEND_PORT phai la so"
  [[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || error "FRONTEND_PORT phai la so"
  [[ "$POSTGRES_PORT" =~ ^[0-9]+$ ]] || error "POSTGRES_PORT phai la so"
  [[ "$PGADMIN_PORT" =~ ^[0-9]+$ ]] || error "PGADMIN_PORT phai la so"
  [[ "$SEARXNG_PORT" =~ ^[0-9]+$ ]] || error "SEARXNG_PORT phai la so"
}

detect_vllm_base_url() {
  local detected_host_port=""
  local llm_host="localhost"

  if [[ -n "${LLM_BASE_URL:-}" ]]; then
    echo "$LLM_BASE_URL"
    return 0
  fi

  if [[ "$BACKEND_HOST" != "0.0.0.0" && "$BACKEND_HOST" != "::" ]]; then
    llm_host="$BACKEND_HOST"
  fi

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
    echo "http://${llm_host}:${detected_host_port}/v1"
    return 0
  fi

  echo "http://${llm_host}:8007/v1"
}

detect_searxng_base_url() {
  local detected_host_port=""

  if is_true "$SEARXNG_AUTO_START"; then
    echo "http://127.0.0.1:${SEARXNG_PORT}"
    return 0
  fi

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
    # nvm.sh can reference unset internals on some shells (notably Git Bash).
    # Temporarily disable nounset to avoid "unbound variable" failures.
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
  local had_nounset="0"
  if [[ $- == *u* ]]; then
    had_nounset="1"
    set +u
  fi
  nvm install --lts
  nvm use --lts
  if [[ "$had_nounset" == "1" ]]; then
    set -u
  fi
}

ensure_npm() {
  if ! has_cmd npm; then
    error "Khong tim thay npm sau khi cai Node.js"
  fi
}

ensure_venv() {
  local py_bin="$1"
  local venv_python
  venv_python="$(venv_python_path)"

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
  local venv_python
  venv_python="$(venv_python_path)"
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
    if [[ -f "$ROOT_DIR/backend/.env.example" ]]; then
      log "Tao backend/.env tu backend/.env.example"
      cp "$ROOT_DIR/backend/.env.example" "$backend_env"
    else
      error "Khong tim thay backend/.env.example"
    fi
  fi

  normalize_line_endings "$backend_env"

  ensure_searxng_if_enabled

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
  upsert_env_var "$backend_env" "APP_FEATURE_SESSION_HISTORY" "$FEATURE_SESSION_HISTORY"
  upsert_env_var "$backend_env" "APP_FEATURE_OPS_DASHBOARD" "$FEATURE_OPS_DASHBOARD"
  upsert_env_var "$backend_env" "APP_FEATURE_LLM_RUNTIME_CONFIG" "$FEATURE_LLM_RUNTIME_CONFIG"
  upsert_env_var "$backend_env" "APP_RBAC_ENABLED" "$RBAC_ENABLED"
  upsert_env_var "$backend_env" "APP_RBAC_ADMIN_TOKEN" "$RBAC_ADMIN_TOKEN"
  upsert_env_var "$backend_env" "APP_LLM_RUNTIME_STORE_PATH" "config/llm_runtime.json"
  upsert_env_var "$backend_env" "APP_AUDIT_LOG_STORE_PATH" "config/audit_logs.jsonl"
  log "Da cap nhat cau hinh LLM backend: APP_LLM_BASE_URL=$llm_base_url"

  if [[ -z "$(extract_env_value "$backend_env" "APP_DATABASE_URL")" ]]; then
    upsert_env_var "$backend_env" "APP_DATABASE_URL" "postgresql+psycopg://postgres:postgres@localhost:5432/web_search?connect_timeout=5"
  fi
  if [[ -z "$(extract_env_value "$backend_env" "APP_SESSION_STORE_BACKEND")" ]]; then
    upsert_env_var "$backend_env" "APP_SESSION_STORE_BACKEND" "auto"
  fi
  if [[ -z "$(extract_env_value "$backend_env" "APP_SESSION_STORE_DUAL_WRITE")" ]]; then
    upsert_env_var "$backend_env" "APP_SESSION_STORE_DUAL_WRITE" "false"
  fi

  if [[ ! -f "$ROOT_DIR/backend/config/tavily_keys.json" ]]; then
    log "Tao backend/config/tavily_keys.json"
    mkdir -p "$ROOT_DIR/backend/config"
    printf '[]\n' >"$ROOT_DIR/backend/config/tavily_keys.json"
  fi

  if [[ ! -f "$ROOT_DIR/backend/config/chat_sessions.json" ]]; then
    log "Tao backend/config/chat_sessions.json"
    mkdir -p "$ROOT_DIR/backend/config"
    printf '[]\n' >"$ROOT_DIR/backend/config/chat_sessions.json"
  fi

  if [[ ! -f "$ROOT_DIR/backend/config/llm_runtime.json" ]]; then
    log "Tao backend/config/llm_runtime.json"
    mkdir -p "$ROOT_DIR/backend/config"
    cat >"$ROOT_DIR/backend/config/llm_runtime.json" <<EOF
{"base_url":"$llm_base_url","model":"$LLM_MODEL","temperature":0.2,"max_tokens":null}
EOF
  fi

  if [[ ! -f "$ROOT_DIR/backend/config/audit_logs.jsonl" ]]; then
    log "Tao backend/config/audit_logs.jsonl"
    mkdir -p "$ROOT_DIR/backend/config"
    : >"$ROOT_DIR/backend/config/audit_logs.jsonl"
  fi

  maybe_configure_postgres_session_store "$venv_python" "$backend_env"
}

setup_frontend() {
  local frontend_env_local="$ROOT_DIR/frontend/.env.local"
  local api_proxy_host
  local npm_cmd

  log "Dang cai dependencies frontend"
  (
    cd "$ROOT_DIR/frontend"
    if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
      # Windows + Git Bash hay gap ENOTEMPTY voi npm ci khi prune node_modules.
      npm_cmd="install"
    elif [[ -f "package-lock.json" ]]; then
      npm_cmd="ci"
    else
      npm_cmd="install"
    fi

    if npm "$npm_cmd" --no-audit --no-fund; then
      :
    else
      warn "npm $npm_cmd that bai, thu don node_modules va cai lai (workaround ENOTEMPTY tren Windows)"
      if [[ -d "node_modules" ]]; then
        local stale_dir="node_modules_stale_$(date +%s)"
        mv node_modules "$stale_dir" 2>/dev/null || true
        rm -rf "$stale_dir" >/dev/null 2>&1 || true
      fi
      npm cache verify >/dev/null 2>&1 || true
      npm install --no-audit --no-fund
    fi
  )

  if [[ ! -f "$frontend_env_local" ]]; then
    if [[ -f "$ROOT_DIR/frontend/.env.example" ]]; then
      log "Tao frontend/.env.local tu frontend/.env.example"
      cp "$ROOT_DIR/frontend/.env.example" "$frontend_env_local"
    else
      warn "Khong tim thay frontend/.env.example, se tao frontend/.env.local moi"
      : >"$frontend_env_local"
    fi
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
  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_FEATURE_SESSION_HISTORY" "$FEATURE_SESSION_HISTORY"
  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_FEATURE_OPS_DASHBOARD" "$FEATURE_OPS_DASHBOARD"
  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG" "$FEATURE_LLM_RUNTIME_CONFIG"
  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_OPS_ROLE" "$OPS_ROLE"
  upsert_env_var "$frontend_env_local" "NEXT_PUBLIC_OPS_ADMIN_TOKEN" "$OPS_ADMIN_TOKEN"
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
  local venv_python
  venv_python="$(venv_python_path)"
  local backend_cmd
  local frontend_cmd
  local backend_pid
  local frontend_pid

  if ! is_true "$AUTO_START_APPS"; then
    log "AUTO_START_APPS=false, bo qua buoc bat app"
    return 0
  fi

  backend_cmd="cd $ROOT_DIR/backend && $venv_python -m uvicorn src.main:app --reload --host $BACKEND_HOST --port $BACKEND_PORT"
  frontend_cmd="cd $ROOT_DIR/frontend && export NVM_DIR=\"$HOME/.nvm\" && if [ -s \"$HOME/.nvm/nvm.sh\" ]; then source \"$HOME/.nvm/nvm.sh\"; fi; npm run dev -- --hostname $FRONTEND_HOST --port $FRONTEND_PORT"

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
  echo "$backend_pid" >"$BACKEND_PID_FILE"
  nohup bash -lc "$frontend_cmd" >"$ROOT_DIR/logs/frontend.dev.log" 2>&1 &
  frontend_pid=$!
  echo "$frontend_pid" >"$FRONTEND_PID_FILE"

  warn "Khong mo duoc 2 terminal, da chay background"
  warn "backend pid=$backend_pid, frontend pid=$frontend_pid"
  warn "logs: logs/backend.dev.log va logs/frontend.dev.log"
}

print_summary() {
  local venv_python
  venv_python="$(venv_python_path)"

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
  if is_true "$PGADMIN_AUTO_START"; then
    echo "  PGADMIN_PORT=$PGADMIN_PORT"
  fi
  echo
  echo "Chay backend:"
  echo "  cd backend"
  echo "  $venv_python -m uvicorn src.main:app --reload --host $BACKEND_HOST --port $BACKEND_PORT"
  echo
  echo "Chay frontend:"
  echo "  cd frontend"
  echo "  npm run dev -- --hostname $FRONTEND_HOST --port $FRONTEND_PORT"
  if is_true "$PGADMIN_AUTO_START"; then
    echo
    echo "pgAdmin:"
    echo "  URL: http://localhost:$PGADMIN_PORT"
    echo "  Email: $PGADMIN_DEFAULT_EMAIL"
  fi
}

main() {
  log "Bat dau setup du an"

  ensure_root_env
  cleanup_existing_processes

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
