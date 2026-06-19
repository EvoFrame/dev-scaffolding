#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

REGISTRY_PATH = Path(os.getenv("SERVICE_REGISTRY", "config/services.toml"))
DEFAULT_GENERATED_COMPOSE = Path(".docker/compose/services.generated.yml")
VALID_DEPENDENCY_CONDITIONS = {
    "service_started",
    "service_healthy",
    "service_completed_successfully",
}


class RegistryError(Exception):
    pass


def _require_table(source: dict, key: str, context: str) -> dict:
    value = source.get(key)
    if not isinstance(value, dict):
        raise RegistryError(f"{context}.{key} must be a table")
    return value


def _require_string(source: dict, key: str, context: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _optional_string(source: dict, key: str, default: str, context: str) -> str:
    value = source.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{context}.{key} must be a non-empty string when provided")
    return value.strip()


def _optional_bool(source: dict, key: str, default: bool, context: str) -> bool:
    value = source.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise RegistryError(f"{context}.{key} must be a boolean when provided")
    return value


def _optional_int(source: dict, key: str, default: int, context: str) -> int:
    value = source.get(key)
    if value is None:
        return default
    if not isinstance(value, int):
        raise RegistryError(f"{context}.{key} must be an integer when provided")
    return value


def _optional_string_list(source: dict, key: str, default: list[str], context: str) -> list[str]:
    value = source.get(key)
    if value is None:
        return default
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RegistryError(f"{context}.{key} must be a list of non-empty strings when provided")
    return [item.strip() for item in value]


def _optional_string_map(source: dict, key: str, context: str) -> dict[str, str]:
    value = source.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RegistryError(f"{context}.{key} must be a table when provided")
    for entry_key, entry_value in value.items():
        if not isinstance(entry_key, str) or not entry_key.strip():
            raise RegistryError(f"{context}.{key} keys must be non-empty strings")
        if not isinstance(entry_value, str):
            raise RegistryError(f"{context}.{key}.{entry_key} must be a string")
    return dict(value)


def _parse_depends_on(depends_on: list[str], context: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for dependency in depends_on:
        name, _, condition = dependency.partition(":")
        name = name.strip()
        condition = condition.strip() or "service_started"
        if not name:
            raise RegistryError(f"{context}.depends_on contains an empty dependency name")
        if condition not in VALID_DEPENDENCY_CONDITIONS:
            raise RegistryError(
                f"{context}.depends_on condition '{condition}' is invalid "
                f"(allowed: {', '.join(sorted(VALID_DEPENDENCY_CONDITIONS))})"
            )
        parsed.append((name, condition))
    return parsed


def _normalize_path(path_value: str) -> str:
    if path_value.startswith("./") or path_value.startswith("/"):
        return path_value
    return f"./{path_value}"


def load_services(registry_path: Path = REGISTRY_PATH) -> list[dict]:
    if not registry_path.exists():
        raise RegistryError(f"Service registry not found: {registry_path}")

    try:
        content = registry_path.read_text(encoding="utf-8")
        raw = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise RegistryError(f"Invalid TOML in {registry_path}: {error}") from error

    services = raw.get("services")
    if not isinstance(services, list) or not services:
        raise RegistryError(f"{registry_path} must define at least one [[services]] entry")

    normalized_services: list[dict] = []
    seen_ids: set[str] = set()

    for index, service in enumerate(services):
        context = f"services[{index}]"
        if not isinstance(service, dict):
            raise RegistryError(f"{context} must be a table")

        service_id = _require_string(service, "id", context)
        if service_id in seen_ids:
            raise RegistryError(f"Duplicate services.id value: {service_id}")
        seen_ids.add(service_id)

        repo = _require_table(service, "repo", context)
        repo_url = _require_string(repo, "url", f"{context}.repo")
        repo_branch = _optional_string(repo, "branch", "main", f"{context}.repo")
        repo_path = _normalize_path(_require_string(repo, "path", f"{context}.repo"))

        docker = _require_table(service, "docker", context)
        docker_context = _normalize_path(_optional_string(docker, "context", repo_path, f"{context}.docker"))
        dockerfile = _optional_string(docker, "dockerfile", ".docker/project/Dockerfile", f"{context}.docker")

        runtime = _require_table(service, "runtime", context)
        host_port = _require_string(runtime, "host_port", f"{context}.runtime")
        container_port = _optional_int(runtime, "container_port", 8080, f"{context}.runtime")
        profiles = _optional_string_list(runtime, "profiles", ["services"], f"{context}.runtime")
        depends_on_raw = _optional_string_list(runtime, "depends_on", [], f"{context}.runtime")
        depends_on = _parse_depends_on(depends_on_raw, f"{context}.runtime")

        env_file = _optional_string(service, "env_file", f"{repo_path}/.env", context)
        environment = _optional_string_map(service, "environment", context)

        database = _require_table(service, "database", context)
        database_enabled = _optional_bool(database, "enabled", False, f"{context}.database")
        database_name = _optional_string(database, "name", "", f"{context}.database")
        database_user = _optional_string(database, "user", "", f"{context}.database")
        database_password = _optional_string(database, "password", "", f"{context}.database")
        if database_enabled and (not database_name or not database_user or not database_password):
            raise RegistryError(
                f"{context}.database requires name/user/password when database.enabled=true"
            )

        auth = _require_table(service, "auth", context)
        register_client = _optional_bool(auth, "register_client", False, f"{context}.auth")

        keys = _require_table(service, "keys", context)
        inject_private_key = _optional_bool(keys, "inject_private_key", False, f"{context}.keys")

        normalized_services.append(
            {
                "id": service_id,
                "repo": {"url": repo_url, "branch": repo_branch, "path": repo_path},
                "docker": {"context": docker_context, "dockerfile": dockerfile},
                "runtime": {
                    "host_port": host_port,
                    "container_port": container_port,
                    "profiles": profiles,
                    "depends_on": depends_on,
                },
                "env_file": env_file,
                "environment": environment,
                "database": {
                    "enabled": database_enabled,
                    "name": database_name,
                    "user": database_user,
                    "password": database_password,
                },
                "auth": {"register_client": register_client},
                "keys": {"inject_private_key": inject_private_key},
            }
        )

    return normalized_services


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _compose_path(path_value: str) -> str:
    normalized = _normalize_path(path_value)
    if normalized.startswith("/"):
        return normalized
    return "${PWD}/" + normalized.removeprefix("./")


def render_compose(services: list[dict]) -> str:
    lines = ["services:"]
    for service in services:
        service_id = service["id"]
        build_context = _compose_path(service["docker"]["context"])
        env_file = _compose_path(service["env_file"])
        host_port = service["runtime"]["host_port"]
        container_port = service["runtime"]["container_port"]
        container_name = f"evoframe-{service_id}"

        lines.append(f"  {service_id}:")
        lines.append("    build:")
        lines.append(f"      context: {_yaml_quote(build_context)}")
        lines.append(f"      dockerfile: {_yaml_quote(service['docker']['dockerfile'])}")
        lines.append("    profiles:")
        for profile in service["runtime"]["profiles"]:
            lines.append(f"      - {profile}")
        lines.append(f"    container_name: {container_name}")
        lines.append("    env_file:")
        lines.append(f"      - {_yaml_quote(env_file)}")
        lines.append("    environment:")
        environment: dict[str, str] = service["environment"]
        for key in sorted(environment):
            lines.append(f"      {key}: {_yaml_quote(environment[key])}")
        lines.append("    ports:")
        lines.append(f"      - {_yaml_quote(f'127.0.0.1:{host_port}:{container_port}')}")
        if service["runtime"]["depends_on"]:
            lines.append("    depends_on:")
            for dependency_name, dependency_condition in service["runtime"]["depends_on"]:
                lines.append(f"      {dependency_name}:")
                lines.append(f"        condition: {dependency_condition}")
        lines.append("    restart: unless-stopped")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_compose(output: Path) -> None:
    services = load_services()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_compose(services), encoding="utf-8")
    print(f"Generated {output}")


def _validate_registry() -> None:
    services = load_services()
    print(f"Registry is valid ({len(services)} service(s)).")


def _print_repos() -> None:
    for service in load_services():
        repo = service["repo"]
        print(f"{service['id']}\t{repo['url']}\t{repo['branch']}\t{repo['path']}")


def _print_service_envs() -> None:
    for service in load_services():
        print(f"{service['id']}\t{service['repo']['path']}\t{service['env_file']}")


def _print_databases() -> None:
    for service in load_services():
        db = service["database"]
        if db["enabled"]:
            print(f"{service['id']}\t{db['name']}\t{db['user']}\t{db['password']}")


def _print_registrable_services() -> None:
    for service in load_services():
        if service["auth"]["register_client"]:
            print(f"{service['id']}\t{service['repo']['path']}\t{service['env_file']}")


def _print_key_services() -> None:
    for service in load_services():
        inject_private_key = "true" if service["keys"]["inject_private_key"] else "false"
        print(f"{service['id']}\t{service['repo']['path']}\t{inject_private_key}")


def _add_service(args: argparse.Namespace) -> None:
    path = REGISTRY_PATH
    services = load_services(path)
    if any(service["id"] == args.service_id for service in services):
        raise RegistryError(f"Service '{args.service_id}' already exists in {path}")

    repo_path = _normalize_path(args.repo_path or f"./repositories/{args.service_id}")
    host_port = args.host_port or "8080"
    branch = args.repo_branch or "main"

    snippet = (
        "\n"
        "[[services]]\n"
        f'id = "{args.service_id}"\n'
        f'env_file = "{repo_path}/.env"\n'
        "\n"
        "  [services.repo]\n"
        f'  url = "{args.repo_url}"\n'
        f'  branch = "{branch}"\n'
        f'  path = "{repo_path}"\n'
        "\n"
        "  [services.docker]\n"
        f'  context = "{repo_path}"\n'
        '  dockerfile = ".docker/project/Dockerfile"\n'
        "\n"
        "  [services.runtime]\n"
        f'  host_port = "{host_port}"\n'
        "  container_port = 8080\n"
        '  profiles = ["services"]\n'
        "  depends_on = []\n"
        "\n"
        "  [services.environment]\n"
        '  SERVICE_PORT = "8080"\n'
        "\n"
        "  [services.database]\n"
        "  enabled = false\n"
        "\n"
        "  [services.auth]\n"
        "  register_client = false\n"
        "\n"
        "  [services.keys]\n"
        "  inject_private_key = false\n"
    )

    path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n" + snippet, encoding="utf-8")
    print(f"Added service '{args.service_id}' to {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage EvoFrame service registry.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate config/services.toml")
    subparsers.add_parser("repos", help="Print service repo rows as TSV")
    subparsers.add_parser("service-envs", help="Print service repo path and env file rows as TSV")
    subparsers.add_parser("databases", help="Print database-enabled services as TSV")
    subparsers.add_parser("registrable-services", help="Print auth registrable services as TSV")
    subparsers.add_parser("key-services", help="Print key injection targets as TSV")

    render_compose_parser = subparsers.add_parser("render-compose", help="Render generated compose file")
    render_compose_parser.add_argument(
        "--output",
        default=str(DEFAULT_GENERATED_COMPOSE),
        help="Output path for generated docker compose file",
    )

    add_service_parser = subparsers.add_parser("add", help="Append a new service template")
    add_service_parser.add_argument("--id", dest="service_id", required=True, help="Service id")
    add_service_parser.add_argument("--repo-url", required=True, help="Git repository URL")
    add_service_parser.add_argument("--repo-branch", help="Git repository branch")
    add_service_parser.add_argument("--repo-path", help="Local repository path")
    add_service_parser.add_argument("--host-port", help="Compose host port expression")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "validate":
            _validate_registry()
        elif args.command == "repos":
            _print_repos()
        elif args.command == "service-envs":
            _print_service_envs()
        elif args.command == "databases":
            _print_databases()
        elif args.command == "registrable-services":
            _print_registrable_services()
        elif args.command == "key-services":
            _print_key_services()
        elif args.command == "render-compose":
            _write_compose(Path(args.output))
        elif args.command == "add":
            _add_service(args)
        else:
            parser.print_help()
            return 2
    except RegistryError as error:
        print(f"Registry error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
