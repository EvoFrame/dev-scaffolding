# Dev Scaffolding

This repository is a quick local scaffolding for Evoframe microservices.

## 5-minute quickstart

1. `mise run setup`
2. `mise run stack-up`
3. Open API gateway at `http://127.0.0.1:8000`

For observability:

1. `mise run stack-up -- --monitoring`
2. Open Grafana at `http://127.0.0.1:3000`
3. Open Prometheus at `http://127.0.0.1:9090`

## Service contract matrix

| Service | Repository path | Host port | Container port | Dependencies | RSA key |
| --- | --- | --- | --- | --- | --- |
| api-gateway | `./repositories/api-gateway` | `API_GATEWAY_HOST_PORT` (default `8000`) | `8080` | redis, auth-service, user-service | public |
| auth-service | `./repositories/auth-service` | `AUTH_SERVICE_HOST_PORT` (default `8081`) | `8080` | postgres, redis | public + private |
| user-service | `./repositories/user-service` | `USER_SERVICE_HOST_PORT` (default `8082`) | `8080` | postgres, redis, auth-service | public |

## Daily commands

- `mise run setup`: bootstrap env files, clone repos, generate keys, and boot infra.
- `mise run doctor`: run environment diagnostics (docker/tooling/files/compose).
- `mise run repo:clone`: clone/update repositories from `.env` (or `.env.example`).
- `mise run rotate-keys`: regenerate RSA keys and reinject key env vars.
- `mise run pre-register-services`: register non-auth service clients in auth-service and ensure `SERVICE_SECRET` exists in each service `.env`.
- `mise run stack-up`: build/start full stack (infra + app services).
- `mise run stack-up -- --ui`: full stack + UIs (pgAdmin, RedisInsight).
- `mise run stack-up -- --monitoring`: full stack + monitoring (Grafana/Prometheus/Loki).
- `mise run stack-down`: stop all stack containers.

## Reset commands

- `mise run repo:clean`: remove cloned repositories listed in env.
- `mise run clean-volumes`: remove compose volumes and generated postgres init SQL.
- `mise run monitoring:down`: stop monitoring stack containers.

## Stack endpoints

- API gateway: `http://127.0.0.1:${API_GATEWAY_HOST_PORT:-8000}`
- pgAdmin: `http://127.0.0.1:${PGADMIN_HOST_PORT:-5050}`
- RedisInsight: `http://127.0.0.1:${REDIS_UI_HOST_PORT:-5540}`
- Grafana: `http://127.0.0.1:${GRAFANA_HOST_PORT:-3000}`
- Prometheus: `http://127.0.0.1:${PROMETHEUS_HOST_PORT:-9090}`
