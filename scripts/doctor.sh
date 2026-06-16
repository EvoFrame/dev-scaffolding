#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  ENV_FILE="${ROOT_DIR}/.env.example"
fi

failures=0

ok() { echo "[OK] $1"; }
warn() { echo "[WARN] $1"; }
err() { echo "[ERR] $1"; failures=$((failures + 1)); }

check_cmd() {
  local cmd="$1"
  if command -v "${cmd}" >/dev/null 2>&1; then
    ok "command '${cmd}' is available"
  else
    err "command '${cmd}' is missing"
  fi
}

check_file() {
  local file_path="$1"
  if [[ -f "${file_path}" ]]; then
    ok "file exists: ${file_path}"
  else
    err "missing file: ${file_path}"
  fi
}

check_dir() {
  local dir_path="$1"
  if [[ -d "${dir_path}" ]]; then
    ok "directory exists: ${dir_path}"
  else
    err "missing directory: ${dir_path}"
  fi
}

echo "== Tooling =="
check_cmd docker
check_cmd task
check_cmd git
check_cmd openssl

echo
echo "== Core files =="
check_file "${ENV_FILE}"
check_file "${ROOT_DIR}/taskfile.yml"
check_file "${ROOT_DIR}/.docker/dev-stacks/postgresql/compose.yml"
check_file "${ROOT_DIR}/.docker/dev-stacks/redis/compose.yml"
check_file "${ROOT_DIR}/.docker/dev-stacks/monitoring/compose.yml"
check_file "${ROOT_DIR}/.docker/compose/full-stack.yml"

echo
echo "== Repositories =="
for repo in api-gateway auth-service user-service; do
  check_dir "${ROOT_DIR}/repositories/${repo}/.git"
  if [[ -f "${ROOT_DIR}/repositories/${repo}/.env" ]]; then
    ok "env exists: repositories/${repo}/.env"
  else
    warn "env missing: repositories/${repo}/.env (run: task init-env)"
  fi
done

echo
echo "== RSA keys =="
check_file "${ROOT_DIR}/.docker/keys/jwt_rs256_private.pem"
check_file "${ROOT_DIR}/.docker/keys/jwt_rs256_public.pem"

echo
echo "== Docker daemon =="
if docker info >/dev/null 2>&1; then
  ok "docker daemon is reachable"
else
  err "docker daemon is not reachable"
fi

echo
echo "== Compose sanity =="
if docker compose \
  -f "${ROOT_DIR}/.docker/dev-stacks/postgresql/compose.yml" \
  -f "${ROOT_DIR}/.docker/dev-stacks/redis/compose.yml" \
  -f "${ROOT_DIR}/.docker/dev-stacks/monitoring/compose.yml" \
  -f "${ROOT_DIR}/.docker/compose/full-stack.yml" \
  --profile services \
  config >/dev/null 2>&1; then
  ok "compose files resolve correctly"
else
  err "compose files do not resolve; run docker compose config manually"
fi

echo
if [[ "${failures}" -eq 0 ]]; then
  echo "Doctor finished: all critical checks passed."
else
  echo "Doctor finished with ${failures} error(s)."
  exit 1
fi
