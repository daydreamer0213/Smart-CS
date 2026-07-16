# FastGPT RAG Engine Proof of Concept Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, with fictional data and executable evidence, whether FastGPT can supply a source-backed RAG answer to SmartCS without weakening SmartCS tenant, credential, or storage controls.

**Architecture:** FastGPT runs only as a local, replaceable RAG provider. SmartCS remains the owner of employee identity, tenant authorization, audit records, support handoff, and the eventual public API. This plan creates an isolated FastGPT deployment on D:, a fictional knowledge corpus, and a small contract probe; it intentionally does not wire FastGPT into `/assistant`.

**Tech Stack:** Windows 11, Docker Desktop with WSL 2 backend, FastGPT PgVector Compose deployment, FastAPI repository, Python 3.11, `httpx`, `pytest`.

## Global Constraints

- All Docker images, WSL/Docker data, deployment files, and generated FastGPT data must remain on D: under `D:\DevData\smartcs-fastgpt-poc\`.
- Do not pull images or start containers until Docker Desktop's supported disk-image location has been checked and confirmed to use D:.
- Use only fictional employee-policy data; never import company, personal, or user-supplied confidential data.
- Never commit API keys, generated passwords, `docker-compose.yml` files containing secrets, or FastGPT IDs tied to live credentials.
- Use FastGPT only through its documented API and provider credentials held server-side.
- Keep CRM/Sales Copilot Lab untouched.
- Stop immediately and report the failed acceptance gate instead of adding a workaround that expands scope.

---

## File Structure

- Modify: `.gitignore` - prevent the local FastGPT PoC credential file from being staged.
- Create: `.env.fastgpt-poc.example` - tracked list of required local variables without values.
- Create: `docs/fixtures/fastgpt-poc/employee-leave-policy.md` - a small fictional knowledge corpus.
- Create: `docs/operations/fastgpt-poc-runbook.md` - reproducible preflight, deployment, and shutdown record with no secrets.
- Create: `app/integrations/__init__.py` - integration namespace, created without changing application routing.
- Create: `app/integrations/fastgpt_poc.py` - provider-contract request builder and response parser used only by the PoC.
- Create: `tests/test_fastgpt_poc.py` - offline unit tests for request and citation parsing.
- Create: `tests/integration/test_fastgpt_poc_live.py` - opt-in test that calls a local FastGPT instance only when all three environment variables exist.

## Task 1: Add PoC Safety Rails and Fictional Corpus

**Files:**
- Modify: `.gitignore`
- Create: `.env.fastgpt-poc.example`
- Create: `docs/fixtures/fastgpt-poc/employee-leave-policy.md`
- Create: `docs/operations/fastgpt-poc-runbook.md`

**Interfaces:**
- Produces: `FASTGPT_POC_BASE_URL`, `FASTGPT_POC_API_KEY`, and `FASTGPT_POC_APP_ID` local configuration names consumed by Tasks 4 and 5.
- Produces: the exact fictional query-answer fact used by the live acceptance test: annual leave is five working days after one year of service.

- [ ] **Step 1: Add the ignored local credential filename**

Append this exact line to `.gitignore`:

```gitignore
.env.fastgpt-poc
```

- [ ] **Step 2: Add the tracked configuration example**

Create `.env.fastgpt-poc.example` with this exact content:

```dotenv
FASTGPT_POC_BASE_URL=http://127.0.0.1:3000/api/v1
FASTGPT_POC_API_KEY=
FASTGPT_POC_APP_ID=
```

- [ ] **Step 3: Add the fictional document**

Create `docs/fixtures/fastgpt-poc/employee-leave-policy.md`:

```markdown
# 北辰科技员工年假制度（演示数据）

本文件仅用于 SmartCS FastGPT PoC，不代表真实公司制度。

## 适用范围

本制度适用于北辰科技已通过试用期的正式员工。

## 年假

员工连续服务满一年后，每个自然年享有 5 个工作日带薪年假。年假需至少提前 3 个工作日在内部系统提交申请，并经直属主管批准。

## 无法回答的情况

涉及跨境雇佣、特殊工时或未在本制度列明的例外情况，员工应提交人力资源支持工单，不应由系统自行解释。
```

- [ ] **Step 4: Add the runbook skeleton**

Create `docs/operations/fastgpt-poc-runbook.md` with this exact initial content:

```markdown
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
```

- [ ] **Step 5: Verify the secret guard and fixture**

Run:

```powershell
git check-ignore -v --no-index .env.fastgpt-poc
Get-Content docs/fixtures/fastgpt-poc/employee-leave-policy.md
```

Expected: the first command prints `.env.fastgpt-poc`; the second shows the five-working-day policy and the HR handoff condition.

- [ ] **Step 6: Commit the safety rails**

```powershell
git add .gitignore .env.fastgpt-poc.example docs/fixtures/fastgpt-poc/employee-leave-policy.md docs/operations/fastgpt-poc-runbook.md
git commit -m "docs: add FastGPT PoC safety rails"
```

## Task 2: Pass the Docker and D: Storage Gate

**Files:**
- Modify: `docs/operations/fastgpt-poc-runbook.md`

**Interfaces:**
- Consumes: the D: storage requirement from Task 1.
- Produces: a recorded pass/fail preflight decision before any image is downloaded.

- [ ] **Step 1: Inspect Docker, WSL, and D: without changing them**

Run:

```powershell
$ErrorActionPreference = 'Stop'
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
docker compose version
wsl --status
Get-PSDrive D | Select-Object Name,Used,Free
```

Expected: Docker reports both client and server versions, Compose is version 2.17 or newer, WSL is available, and D: has at least 30 GB free before the PoC.

- [ ] **Step 2: Check Docker Desktop's disk-image location in the supported UI**

Open Docker Desktop, then inspect `Settings -> Resources -> Advanced -> Disk image location`.

Expected: the location is on D:. Record only `D:` as the location class in the runbook, not the complete machine path.

- [ ] **Step 3: Stop on an unmet storage prerequisite**

If Docker is unavailable, its server is stopped, or its disk image is on C:, do not run any FastGPT install command. Add this result to the runbook:

```markdown
## Preflight result

Status: blocked
Reason: Docker Desktop disk image is not confirmed on D:.
Next action: change the location through Docker Desktop while Docker is stopped, then rerun the preflight commands.
```

Expected: no Docker image download has occurred.

- [ ] **Step 4: Record a passed preflight**

If every check passes, append this section, replacing only bracketed values with non-sensitive version or capacity values:

```markdown
## Preflight result

Status: passed
Docker Engine: copy the exact non-sensitive version string from the preflight command
Docker Compose: copy the exact non-sensitive version string from the preflight command
WSL: available
D: free space before deployment: copy the capacity printed by `Get-PSDrive D`
Docker disk image location: D:
```

- [ ] **Step 5: Commit the preflight evidence**

```powershell
git add docs/operations/fastgpt-poc-runbook.md
git commit -m "docs: record FastGPT PoC preflight"
```

## Task 3: Create a Pinned Local FastGPT PgVector Deployment

**Files:**
- Modify: `docs/operations/fastgpt-poc-runbook.md`
- Create outside Git: `D:\DevData\smartcs-fastgpt-poc\deployment\docker-compose.source.yml`
- Create outside Git: `D:\DevData\smartcs-fastgpt-poc\deployment\install.sh`
- Create outside Git: `D:\DevData\smartcs-fastgpt-poc\deployment\docker-compose.yml`

**Interfaces:**
- Consumes: the passed Docker and D: storage gate from Task 2.
- Produces: a local FastGPT base URL at `http://127.0.0.1:3000` and an ignored deployment directory containing generated credentials.

- [ ] **Step 1: Create the D: deployment root**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'D:\DevData\smartcs-fastgpt-poc\deployment' | Out-Null
Get-PSDrive D | Select-Object Name,Free
```

Expected: the directory exists on D: and the remaining free space is still at least 30 GB.

- [ ] **Step 2: Download the documented PgVector Compose source and installer through WSL**

Run in a WSL distribution selected by `wsl -l -q`:

```bash
set -euo pipefail
cd /mnt/d/DevData/smartcs-fastgpt-poc/deployment
curl -fsSL https://doc.fastgpt.cn/deploy/docker/v4.15/cn/docker-compose.pg.yml -o docker-compose.source.yml
curl -fsSL https://doc.fastgpt.cn/deploy/install.sh -o install.sh
chmod +x install.sh
grep -E '^\s*image:' docker-compose.source.yml
```

Expected: the compose source lists FastGPT, MongoDB, PgVector, and object-storage images. Record the displayed image tags in the runbook; do not replace them with `latest`.

- [ ] **Step 3: Generate local configuration and secrets with FastGPT's installer**

Run from the same WSL directory:

```bash
set -euo pipefail
cd /mnt/d/DevData/smartcs-fastgpt-poc/deployment
FASTGPT_LOCAL_COMPOSE_PATH=./docker-compose.source.yml bash ./install.sh
```

During the interactive prompts, select the local PgVector deployment and enter only the LAN address required by FastGPT object storage. Do not use `localhost` or `127.0.0.1` for the object-storage external endpoint. Keep generated credentials only inside the D: deployment directory.

Expected: `docker-compose.yml` is created, contains generated credentials, and is never copied into the repository.

- [ ] **Step 4: Validate the generated Compose file before starting containers**

Run:

```bash
set -euo pipefail
cd /mnt/d/DevData/smartcs-fastgpt-poc/deployment
docker compose config --quiet
docker compose config --images
```

Expected: `config --quiet` exits with code 0 and the image list contains pinned tags rather than `latest`.

- [ ] **Step 5: Start and inspect the local deployment**

Run:

```bash
set -euo pipefail
cd /mnt/d/DevData/smartcs-fastgpt-poc/deployment
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

Expected: all required containers report `running` or `healthy`; logs contain no repeating database connection failure or Mongo replica-set initialization failure.

- [ ] **Step 6: Record deployment facts without secrets**

Append this section to the runbook, replacing only bracketed values:

```markdown
## Deployment result

Compose source: FastGPT documented PgVector deployment
Image tags: copy the non-sensitive output of `docker compose config --images`
FastGPT local endpoint: http://127.0.0.1:3000
Container health: write `passed` only when every required container is running or healthy; otherwise write `failed`
Generated credentials: stored only under D:\DevData\smartcs-fastgpt-poc\deployment
```

- [ ] **Step 7: Commit the redacted deployment record**

```powershell
git add docs/operations/fastgpt-poc-runbook.md
git commit -m "docs: record FastGPT PoC deployment"
```

## Task 4: Build the Fictional Knowledge Assistant and Capture API Credentials Locally

**Files:**
- Create outside Git: `.env.fastgpt-poc`
- Modify: `docs/operations/fastgpt-poc-runbook.md`

**Interfaces:**
- Consumes: the fixture from Task 1 and the local FastGPT endpoint from Task 3.
- Produces: a local `FASTGPT_POC_APP_ID` and a local API key for the contract probe, neither tracked by Git.

- [ ] **Step 1: Configure a language model and an index model through FastGPT's local UI**

Open `http://127.0.0.1:3000`, sign in with the installer-generated root password, and configure one language model plus one index model using a locally supplied provider credential.

Expected: FastGPT no longer shows the missing-model warning. The provider credential is stored only in FastGPT's local D: deployment data.

- [ ] **Step 2: Import the fictional policy document**

Create a knowledge base named `SmartCS PoC Employee Policies` and import:

```text
docs/fixtures/fastgpt-poc/employee-leave-policy.md
```

Wait until processing completes successfully. Do not import any other document.

Expected: the knowledge base shows a ready document with searchable chunks.

- [ ] **Step 3: Create a minimal knowledge-base Q&A application**

Create an application named `SmartCS Internal Knowledge Assistant PoC` using FastGPT's knowledge-base Q&A flow. Attach only `SmartCS PoC Employee Policies`, enable citations, and instruct the application to direct unlisted exceptions to HR support instead of inventing policy.

Expected: asking `员工年假规则是什么？` returns `5 个工作日` and displays a citation from `employee-leave-policy.md`.

- [ ] **Step 4: Create a least-lived API key and local PoC configuration**

Create a FastGPT API key with an expiry or quota when the UI provides either option. Copy the application ID and key into the ignored repository-root file `.env.fastgpt-poc`:

```dotenv
FASTGPT_POC_BASE_URL=http://127.0.0.1:3000/api/v1
FASTGPT_POC_API_KEY=local-fastgpt-api-key
FASTGPT_POC_APP_ID=local-fastgpt-application-id
```

Expected: `git status --short .env.fastgpt-poc` prints nothing because the file is ignored.

- [ ] **Step 5: Record only non-sensitive application evidence**

Append this section to the runbook:

```markdown
## Knowledge-base result

Corpus: one fictional employee leave-policy document
Question: 员工年假规则是什么？
Expected answer fact: 5 个工作日
Citation visible in FastGPT UI: [passed or failed]
API key stored only in ignored local configuration: passed
```

- [ ] **Step 6: Commit the redacted knowledge-base result**

```powershell
git add docs/operations/fastgpt-poc-runbook.md
git commit -m "docs: record FastGPT knowledge-base setup"
```

## Task 5: Add an Offline-Tested FastGPT Provider Contract Probe

**Files:**
- Create: `app/integrations/__init__.py`
- Create: `app/integrations/fastgpt_poc.py`
- Create: `tests/test_fastgpt_poc.py`
- Create: `tests/integration/test_fastgpt_poc_live.py`

**Interfaces:**
- Consumes: `FASTGPT_POC_BASE_URL`, `FASTGPT_POC_API_KEY`, and `FASTGPT_POC_APP_ID` from Task 4.
- Produces: `build_chat_request(app_id, chat_id, question) -> dict`, `parse_detail_response(payload) -> FastGPTPocAnswer`, and `call_fastgpt_poc(...) -> FastGPTPocAnswer`.
- Does not change the SmartCS `/assistant` route or its existing RAG provider.

- [ ] **Step 1: Write the failing offline unit tests**

Create `tests/test_fastgpt_poc.py`:

```python
from app.integrations.fastgpt_poc import build_chat_request, parse_detail_response


def test_build_chat_request_requests_non_stream_detail_response():
    payload = build_chat_request("app-1", "tenant-demo-user-demo", "员工年假规则是什么？")

    assert payload == {
        "appId": "app-1",
        "chatId": "tenant-demo-user-demo",
        "stream": False,
        "detail": True,
        "messages": [{"role": "user", "content": "员工年假规则是什么？"}],
    }


def test_parse_detail_response_extracts_answer_and_quotes():
    result = parse_detail_response({
        "choices": [{"message": {"content": "连续服务满一年后有 5 个工作日年假。"}}],
        "responseData": [{
            "moduleName": "AI Chat",
            "quoteList": [{
                "id": "chunk-1",
                "datasetId": "dataset-1",
                "sourceName": "employee-leave-policy.md",
                "a": "每个自然年享有 5 个工作日带薪年假。",
                "score": 0.93,
            }],
        }],
    })

    assert result.answer == "连续服务满一年后有 5 个工作日年假。"
    assert result.sources == [{
        "id": "chunk-1",
        "dataset_id": "dataset-1",
        "source_name": "employee-leave-policy.md",
        "content": "每个自然年享有 5 个工作日带薪年假。",
        "score": 0.93,
    }]
```

- [ ] **Step 2: Run the unit tests to verify failure**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_fastgpt_poc.py -q
```

Expected: collection fails because `app.integrations.fastgpt_poc` does not exist.

- [ ] **Step 3: Add the minimal provider-contract implementation**

Create `app/integrations/__init__.py` as an empty file. Create `app/integrations/fastgpt_poc.py`:

```python
"""FastGPT proof-of-concept contract helpers; not wired into the Assistant API."""

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class FastGPTPocAnswer:
    answer: str
    sources: list[dict[str, str | float]]


def build_chat_request(app_id: str, chat_id: str, question: str) -> dict[str, Any]:
    return {
        "appId": app_id,
        "chatId": chat_id,
        "stream": False,
        "detail": True,
        "messages": [{"role": "user", "content": question}],
    }


def parse_detail_response(payload: dict[str, Any]) -> FastGPTPocAnswer:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("FastGPT response has no choices")
    answer = choices[0].get("message", {}).get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("FastGPT response has no text answer")

    sources: list[dict[str, str | float]] = []
    for module in payload.get("responseData") or []:
        for quote in module.get("quoteList") or []:
            sources.append({
                "id": str(quote.get("id", "")),
                "dataset_id": str(quote.get("datasetId") or quote.get("dataset_id") or ""),
                "source_name": str(quote.get("sourceName") or quote.get("source") or ""),
                "content": str(quote.get("a") or quote.get("text") or quote.get("q") or ""),
                "score": float(quote.get("score", 0.0)),
            })
    return FastGPTPocAnswer(answer=answer, sources=sources)


def call_fastgpt_poc(
    base_url: str, api_key: str, app_id: str, chat_id: str, question: str
) -> FastGPTPocAnswer:
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=build_chat_request(app_id, chat_id, question),
        timeout=60.0,
    )
    response.raise_for_status()
    return parse_detail_response(response.json())
```

- [ ] **Step 4: Run the unit tests to verify success**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_fastgpt_poc.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add the opt-in live acceptance test**

Create `tests/integration/test_fastgpt_poc_live.py`:

```python
import os

import pytest

from app.integrations.fastgpt_poc import call_fastgpt_poc


REQUIRED = ("FASTGPT_POC_BASE_URL", "FASTGPT_POC_API_KEY", "FASTGPT_POC_APP_ID")
pytestmark = pytest.mark.skipif(
    not all(os.getenv(name) for name in REQUIRED),
    reason="FastGPT PoC credentials are not configured locally",
)


def test_fastgpt_returns_a_cited_leave_policy_answer():
    result = call_fastgpt_poc(
        os.environ["FASTGPT_POC_BASE_URL"],
        os.environ["FASTGPT_POC_API_KEY"],
        os.environ["FASTGPT_POC_APP_ID"],
        "smartcs-poc-demo-001",
        "员工年假规则是什么？",
    )

    assert "5 个工作日" in result.answer
    assert result.sources
    assert any(source["source_name"] == "employee-leave-policy.md" for source in result.sources)
```

- [ ] **Step 6: Verify the default suite stays offline**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_fastgpt_poc.py tests/integration/test_fastgpt_poc_live.py -q
```

Expected: `2 passed, 1 skipped` when the three PoC environment variables are absent.

- [ ] **Step 7: Commit the contract probe**

```powershell
git add app/integrations tests/test_fastgpt_poc.py tests/integration/test_fastgpt_poc_live.py
git commit -m "test: add FastGPT PoC provider contract"
```

## Task 6: Run the Live Gate and Record the Go/No-Go Decision

**Files:**
- Modify: `docs/operations/fastgpt-poc-runbook.md`

**Interfaces:**
- Consumes: the local FastGPT configuration from Task 4 and the live test from Task 5.
- Produces: a recorded `go` or `no-go` decision. A `go` permits a separate, later adapter-integration design and plan; it does not authorize implementation automatically.

- [ ] **Step 1: Load the ignored local variables into the current PowerShell session**

Run:

```powershell
Get-Content .env.fastgpt-poc | ForEach-Object {
    if ($_ -match '^(?<name>[^#=]+)=(?<value>.*)$') {
        [Environment]::SetEnvironmentVariable($matches.name, $matches.value, 'Process')
    }
}
```

Expected: the command prints no credential values.

- [ ] **Step 2: Run the live citation test**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/integration/test_fastgpt_poc_live.py -q
```

Expected: `1 passed`. A failed answer, missing quote list, request error, or source-name mismatch is a `no-go` result.

- [ ] **Step 3: Run the full SmartCS regression suite**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest -q
```

Expected: all existing tests pass, including the live FastGPT test because Step 1 loaded its three local variables. In a fresh shell without those variables, that one test is skipped.

- [ ] **Step 4: Record a go decision only when every gate passed**

Append one of these exact records to the runbook.

For success:

```markdown
## Go/No-Go decision

Decision: go
Evidence: fictional document ingestion passed; API response included a non-empty answer and source list; source name matched `employee-leave-policy.md`; local credentials remained ignored; Docker data stayed on D:.
Next step: write a separate SmartCS FastGPT adapter integration design. Do not modify `/assistant` before that design is approved.
```

For failure:

```markdown
## Go/No-Go decision

Decision: no-go
Failed gate: copy the literal failed acceptance criterion from the approved FastGPT selection design
Evidence: describe the observed behavior without copying credentials, app IDs, LAN addresses, or document content beyond the fictional policy
Fallback: retain the existing SmartCS RAG path and do not create a FastGPT adapter.
```

- [ ] **Step 5: Commit only redacted evidence**

```powershell
git add docs/operations/fastgpt-poc-runbook.md
git commit -m "docs: record FastGPT PoC decision"
```

## Plan Self-Review

- Spec coverage: Tasks 1-2 enforce fictional-data, secret, and D: controls; Tasks 3-4 prove reproducible deployment, ingestion, API access, and citation visibility; Task 5 proves the documented `detail=true` response contract offline and live; Task 6 records the six acceptance gates and retains the existing RAG fallback on failure.
- Placeholder scan: no placeholder marker remains; every evidence record specifies exactly which command output or acceptance criterion to record.
- Type consistency: the live test consumes only `call_fastgpt_poc`, which returns `FastGPTPocAnswer`; all request and response functions are defined in Task 5.
