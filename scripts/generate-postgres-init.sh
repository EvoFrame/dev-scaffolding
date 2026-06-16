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

SQL_FILE="${ROOT_DIR}/.docker/dev-stacks/postgresql/init/01-init-multiple-dbs.sql"
mkdir -p "$(dirname "${SQL_FILE}")"

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

escape_ident() {
  local value="$1"
  value="${value//\"/\"\"}"
  printf "%s" "${value}"
}

escape_literal() {
  local value="$1"
  value="${value//\'/\'\'}"
  printf "%s" "${value}"
}

mapfile -t db_prefixes < <(
  grep -E '^[A-Z0-9_]+_HAS_DATABASE=true$' "${ENV_FILE}" | sed -E 's/_HAS_DATABASE=true$//' || true
)

{
  echo "-- Generated from $(basename "${ENV_FILE}")"
  echo "-- Re-run task boot-stack after editing .env/.env.example"
  echo
} > "${SQL_FILE}"

if [[ ${#db_prefixes[@]} -eq 0 ]]; then
  echo "-- No *_HAS_DATABASE=true entries found." >> "${SQL_FILE}"
  echo "Generated ${SQL_FILE} (no service databases configured)."
  exit 0
fi

for prefix in "${db_prefixes[@]}"; do
  db_name="$(get_var "${prefix}_DATABASE_NAME")"
  db_user="$(get_var "${prefix}_DATABASE_USER")"
  db_password="$(get_var "${prefix}_DATABASE_PASSWORD")"

  if [[ -z "${db_name}" ]]; then
    echo "Skipping ${prefix}: ${prefix}_DATABASE_NAME is required." >&2
    continue
  fi

  if [[ -z "${db_user}" ]]; then
    db_user="${db_name}"
  fi
  if [[ -z "${db_password}" ]]; then
    db_password="${db_user}_password"
  fi

  db_name_escaped="$(escape_ident "${db_name}")"
  db_user_ident_escaped="$(escape_ident "${db_user}")"
  db_user_literal_escaped="$(escape_literal "${db_user}")"
  db_password_escaped="$(escape_literal "${db_password}")"

  cat >> "${SQL_FILE}" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user_literal_escaped}') THEN
    CREATE ROLE "${db_user_ident_escaped}" LOGIN PASSWORD '${db_password_escaped}';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE "${db_name_escaped}" OWNER "${db_user_ident_escaped}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name_escaped}')\gexec

GRANT ALL PRIVILEGES ON DATABASE "${db_name_escaped}" TO "${db_user_ident_escaped}";

SQL
done

echo "Generated ${SQL_FILE}"
