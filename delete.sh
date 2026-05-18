#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

remove_container() {
  local name="$1"
  if [[ -z "$name" ]]; then
    return
  fi
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker rm -f -v "$name" >/dev/null
    echo "[delete] Removed container: $name"
  else
    echo "[delete] Container not found: $name"
  fi
}

remove_image() {
  local image="$1"
  if [[ -z "$image" ]]; then
    return
  fi
  if docker image inspect "$image" >/dev/null 2>&1; then
    docker rmi -f "$image" >/dev/null
    echo "[delete] Removed image: $image"
  else
    echo "[delete] Image not found: $image"
  fi
}

KEEP_IMAGES=false
for arg in "$@"; do
  case "$arg" in
    --keep-images)
      KEEP_IMAGES=true
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./delete.sh [--keep-images]

Stops local app processes, removes Docker containers configured in .env,
and removes their images unless --keep-images is provided.
EOF
      exit 0
      ;;
    *)
      echo "[delete][error] Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

load_env

if [[ -x "$ROOT_DIR/stop.sh" ]]; then
  "$ROOT_DIR/stop.sh" || true
fi

if ! docker_available; then
  echo "[delete][warn] Docker is not available. Skipping container/image cleanup."
  exit 0
fi

POSTGRES_CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-websearch-pg}"
PGADMIN_CONTAINER_NAME="${PGADMIN_CONTAINER_NAME:-websearch-pgadmin}"
SEARXNG_CONTAINER_NAME="${SEARXNG_CONTAINER_NAME:-websearch-searxng}"

POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16}"
PGADMIN_IMAGE="${PGADMIN_IMAGE:-dpage/pgadmin4:8}"
SEARXNG_IMAGE="${SEARXNG_IMAGE:-searxng/searxng:latest}"

remove_container "$POSTGRES_CONTAINER_NAME"
remove_container "$PGADMIN_CONTAINER_NAME"
remove_container "$SEARXNG_CONTAINER_NAME"

if [[ "$KEEP_IMAGES" == "true" ]]; then
  echo "[delete] Kept Docker images because --keep-images was provided."
else
  remove_image "$POSTGRES_IMAGE"
  remove_image "$PGADMIN_IMAGE"
  remove_image "$SEARXNG_IMAGE"
fi

echo "[delete] Done"
