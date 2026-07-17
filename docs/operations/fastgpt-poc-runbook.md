# FastGPT PoC Runbook

## Scope

This local proof of concept uses only `docs/fixtures/fastgpt-poc/employee-leave-policy.md`.
SmartCS remains the owner of tenant authorization, audit, and support handoff.

## Storage

- Deployment root: `D:\DevData\smartcs-fastgpt-poc\deployment`
- Docker Desktop program files and disk image must remain on `D:`.
- Local credentials: `.env.fastgpt-poc` at repository root; this file is ignored by Git.

## Required preflight output

Record Docker Desktop version, Docker Engine version, Compose version, the D: free space before deployment, and the configured Docker disk-image location. Do not record passwords, API keys, app IDs, or private IP addresses.

## Preflight result (2026-07-17)

Status: passed.

- Docker Desktop 4.82.0 is running with Engine 29.6.1 and Compose v5.3.0.
- The `desktop-linux` context uses the WSL 2 backend. `docker version`, `docker compose version`, `docker info`, and `docker ps` all return successfully.
- `D:` has 75.89 GiB free after installation, which is sufficient for this bounded PoC.
- Docker disk image location: `D:`.
- No FastGPT or PoC images have been pulled.
- A copied legacy Docker Desktop 4.79.0 directory and a 7.15 GiB `docker_data.vhdx` exist under `D:\2026.07.09\docker`. Leave them untouched; do not run the copied binaries or attach the old data disk directly.

## Deployment result (2026-07-17)

Status: passed.

- Compose source: FastGPT documented v4.15 PgVector deployment.
- Image tags: `registry.cn-hangzhou.aliyuncs.com/fastgpt/mongo:5.0.32`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/pgvector:0.8.0-pg15`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/fastgpt-plugin:v1.0.1`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/minio:RELEASE.2025-09-07T16-13-09Z`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/redis:7.2-alpine`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/fastgpt:v4.15.1`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/fastgpt-code-sandbox:v4.15.0`, `registry.cn-hangzhou.aliyuncs.com/fastgpt/fastgpt-mcp_server:v4.14.23`, and `registry.cn-hangzhou.aliyuncs.com/labring/aiproxy:v0.6.5`.
- FastGPT local endpoint: `http://127.0.0.1:3000` returned HTTP 200.
- Container health: passed. All required containers are running; components with health checks report healthy, and FastGPT/AIProxy both have zero restarts after an observation window.
- Generated credentials: stored only under `D:\DevData\smartcs-fastgpt-poc\deployment`.
- `D:` retained 67.23 GiB free after deployment.

Next action: configure a local model provider, import the one fictional policy document, and create the bounded knowledge-base Q&A application.

## Shutdown

From the deployment directory, run `docker compose down`. Do not use `-v` until the PoC decision has been recorded and no evidence is needed.
