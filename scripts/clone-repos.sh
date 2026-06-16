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
  grep -E '^[A-Z0-9_]+_REPO_URL=' "${ENV_FILE}" | sed -E 's/=.*$//' | sed -E 's/_REPO_URL$//' || true
)

if [[ ${#repo_prefixes[@]} -eq 0 ]]; then
  echo "No *_REPO_URL entries found in ${ENV_FILE}."
  exit 0
fi

for prefix in "${repo_prefixes[@]}"; do
  repo_url="$(get_var "${prefix}_REPO_URL")"
  repo_branch="$(get_var "${prefix}_REPO_BRANCH")"
  repo_path="$(get_var "${prefix}_REPO_PATH")"

  if [[ -z "${repo_url}" || -z "${repo_path}" ]]; then
    echo "Skipping ${prefix}: missing ${prefix}_REPO_URL or ${prefix}_REPO_PATH." >&2
    continue
  fi

  if [[ -z "${repo_branch}" ]]; then
    repo_branch="main"
  fi

  target_path="${repo_path}"
  if [[ "${target_path}" != /* ]]; then
    target_path="${ROOT_DIR}/${target_path#./}"
  fi

  if [[ -d "${target_path}/.git" ]]; then
    git -C "${target_path}" fetch --quiet origin
    git -C "${target_path}" checkout --quiet "${repo_branch}"
    git -C "${target_path}" pull --ff-only --quiet origin "${repo_branch}"
    echo "Updated ${prefix} -> ${target_path} (${repo_branch})"
    continue
  fi

  if [[ -e "${target_path}" && ! -d "${target_path}/.git" ]]; then
    echo "Skipping ${prefix}: ${target_path} exists and is not a git repository." >&2
    continue
  fi

  mkdir -p "$(dirname "${target_path}")"
  git clone --quiet --branch "${repo_branch}" "${repo_url}" "${target_path}"
  echo "Cloned ${prefix} -> ${target_path} (${repo_branch})"
done

"${ROOT_DIR}/scripts/sync-rsa-keys.sh"
