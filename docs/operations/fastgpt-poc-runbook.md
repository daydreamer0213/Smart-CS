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

## Shutdown

From the deployment directory, run `docker compose down`. Do not use `-v` until the PoC decision has been recorded and no evidence is needed.
