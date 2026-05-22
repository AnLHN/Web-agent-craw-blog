#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV_FILE="$ROOT_DIR/.env"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
NINEROUTER_PID_FILE="$LOG_DIR/9router.pid"
BACKEND_PORT="8011"
FRONTEND_PORT="3005"
NINEROUTER_DASHBOARD_URL="http://localhost:20128/dashboard"

log() {
  echo "[stop] $*"
}

warn() {
  echo "[stop][warn] $*" >&2
}

load_env() {
  if [[ -f "$ROOT_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ROOT_ENV_FILE"
  fi
  BACKEND_PORT="${BACKEND_PORT:-8011}"
  FRONTEND_PORT="${FRONTEND_PORT:-3005}"
  NINEROUTER_DASHBOARD_URL="${NINEROUTER_DASHBOARD_URL:-http://localhost:20128/dashboard}"
}

stop_by_pid_file() {
  local label="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    warn "Khong tim thay $label pid file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 0.6
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    log "Da dung $label pid=$pid"
  else
    warn "$label khong con chay (pid=$pid)"
  fi
  rm -f "$pid_file"
}

stop_project_processes_windows_fallback() {
  local uname_s
  uname_s="$(uname -s)"
  if [[ "$uname_s" == MINGW* || "$uname_s" == MSYS* || "$uname_s" == CYGWIN* ]]; then
    if command -v powershell >/dev/null 2>&1; then
      powershell -NoProfile -Command "\
        Get-CimInstance Win32_Process | Where-Object { \
          (\$_.CommandLine -match 'WebSearch_Tavily\\web-agent' -and \$_.Name -match 'python|node|npm') -or \
          (\$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'multiprocessing-fork' -and \$_.CommandLine -match 'spawn_main') \
        } | ForEach-Object { try { Stop-Process -Id \$_.ProcessId -Force -ErrorAction Stop } catch {} }" >/dev/null 2>&1 || true
      log "Da quet dung process project bang PowerShell fallback"
    fi
  fi
}

stop_by_port_windows() {
  local port="$1"
  if command -v powershell >/dev/null 2>&1; then
    powershell -NoProfile -Command "\
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

warn_if_port_still_listening_windows() {
  local port="$1"
  if command -v powershell >/dev/null 2>&1; then
    local remaining
    remaining="$(powershell -NoProfile -Command "\
      @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { \$_ -and \$_ -ne 0 }) -join ','" 2>/dev/null || true)"
    if [[ -n "$remaining" ]]; then
      warn "Port $port van dang LISTEN boi PID(s): $remaining"
      warn "Neu PID khong ton tai/khong kill duoc, chay PowerShell Admin: Restart-Service WinNat -Force"
    fi
  fi
}

stop_by_port_unix() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill $pids >/dev/null 2>&1 || true
      sleep 0.3
      kill -9 $pids >/dev/null 2>&1 || true
    fi
  fi
}

main() {
  load_env
  stop_by_pid_file "backend" "$BACKEND_PID_FILE"
  stop_by_pid_file "frontend" "$FRONTEND_PID_FILE"
  stop_by_pid_file "9router" "$NINEROUTER_PID_FILE"
  local uname_s
  uname_s="$(uname -s)"
  if [[ "$uname_s" == MINGW* || "$uname_s" == MSYS* || "$uname_s" == CYGWIN* ]]; then
    stop_by_port_windows "$BACKEND_PORT"
    stop_by_port_windows "$FRONTEND_PORT"
    stop_by_port_windows "$(echo "$NINEROUTER_DASHBOARD_URL" | sed -n 's#.*:\([0-9][0-9]*\).*#\1#p')"
    warn_if_port_still_listening_windows "$BACKEND_PORT"
    warn_if_port_still_listening_windows "$FRONTEND_PORT"
  else
    stop_by_port_unix "$BACKEND_PORT"
    stop_by_port_unix "$FRONTEND_PORT"
    stop_by_port_unix "$(echo "$NINEROUTER_DASHBOARD_URL" | sed -n 's#.*:\([0-9][0-9]*\).*#\1#p')"
  fi
  stop_project_processes_windows_fallback
}

main "$@"
