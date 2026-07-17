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

Next action: deploy the bounded FastGPT stack to the deployment root, then rerun the preflight without recording credentials.

## Shutdown

From the deployment directory, run `docker compose down`. Do not use `-v` until the PoC decision has been recorded and no evidence is needed.
