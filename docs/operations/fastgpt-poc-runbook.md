# FastGPT PoC Runbook

## Scope

This local proof of concept uses only `docs/fixtures/fastgpt-poc/employee-leave-policy.md`.
SmartCS remains the owner of tenant authorization, audit, and support handoff.

## Storage

- Deployment root: `D:\DevData\smartcs-fastgpt-poc\deployment`
- Docker Desktop disk image: record the supported Docker Desktop setting before image pulls.
- Local credentials: `.env.fastgpt-poc` at repository root; this file is ignored by Git.

## Required preflight output

Record Docker Desktop version, Docker Engine version, Compose version, the D: free space before deployment, and the configured Docker disk-image location. Do not record passwords, API keys, app IDs, or private IP addresses.

## Preflight result (2026-07-16)

Status: blocked before deployment.

- `D:` has 81.36 GiB free, which is sufficient for this bounded PoC.
- Docker Desktop is not installed on this Windows system: `docker version` and `docker compose version` are unavailable.
- WSL is not yet usable for Docker Desktop initialization.
- A copied legacy Docker Desktop 4.79.0 directory and a 7.15 GiB `docker_data.vhdx` exist under `D:\2026.07.09\docker`. Leave them untouched; do not run the copied binaries or attach the old data disk directly.

Next action: reinstall Docker Desktop, complete WSL 2 initialization, and set its supported disk-image location to `D:\DevData\docker-desktop` before pulling images. Then rerun the required preflight and update this section without recording credentials.

## Shutdown

From the deployment directory, run `docker compose down`. Do not use `-v` until the PoC decision has been recorded and no evidence is needed.
