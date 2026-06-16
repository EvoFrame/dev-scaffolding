#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  ENV_FILE="${ROOT_DIR}/.env.example"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "No .env or .env.example file found." >&2
  exit 1
fi

strip_wrapping_quotes() {
  local value="$1"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf "%s" "${value}"
}

get_var() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
  strip_wrapping_quotes "${value}"
}

mapfile -t repo_prefixes < <(
  grep -E '^[A-Z0-9_]+_REPO_PATH=' "${ENV_FILE}" | sed -E 's/=.*$//' | sed -E 's/_REPO_PATH$//' || true
)

if [[ ${#repo_prefixes[@]} -eq 0 ]]; then
  echo "No *_REPO_PATH entries found in ${ENV_FILE}."
  exit 0
fi

for prefix in "${repo_prefixes[@]}"; do
  repo_path="$(get_var "${prefix}_REPO_PATH")"
  if [[ -z "${repo_path}" ]]; then
    continue
  fi

  target_path="${repo_path}"
  if [[ "${target_path}" != /* ]]; then
    target_path="${ROOT_DIR}/${target_path#./}"
  fi

  if [[ "${target_path}" == "/" || "${target_path}" == "${ROOT_DIR}" ]]; then
    echo "Skipping ${prefix}: refusing to remove unsafe path ${target_path}." >&2
    continue
  fi

  if [[ -d "${target_path}" ]]; then
    rm -rf "${target_path}"
    echo "Removed ${prefix} -> ${target_path}"
  else
    echo "Skipped ${prefix}: ${target_path} does not exist."
  fi
done
