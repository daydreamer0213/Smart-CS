# M2-4 Document Governance Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add governed HR document versions, D-drive source retention, immutable index generations, explicit approval, and failure-safe reindex switching without replacing the existing FastAPI, SQLAlchemy, ChromaDB, BM25, parser, or authorization boundaries.

**Architecture:** `DocumentFamily` is the stable logical policy identity and owns a single `current_document_id` publication pointer. Every `Document` row is an immutable business-version/index-generation snapshot; its chunks are indexed while SQL-invisible, then approval or a successful reindex changes the family pointer in one SQL transaction. External index cleanup is best effort because SQL remains the authoritative tenant, role, lifecycle, and current-version filter.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, Alembic, SQLite-compatible schema, ChromaDB, BM25, pytest.

## Global Constraints

- Keep FastAPI, SQLAlchemy, ChromaDB, BM25, Docling/Tesseract, and the current HR Agent boundaries.
- Do not add LlamaIndex, a workflow engine, object storage, a background queue, or a complete HRIS.
- Store original files below configured `D:/DevData/smartcs/documents`; never default large or generated data to `C:`.
- New uploads are indexed but not employee-searchable until an owner/admin approves them.
- A successful reindex creates a new immutable generation and changes visibility only after SQL chunks, ChromaDB, and BM25 all succeed.
- Any parse, quality, embedding, vector, or BM25 failure leaves the previous family publication pointer unchanged.
- SQL is the final authorization and publication boundary; ChromaDB metadata and BM25 candidates are untrusted.
- Legacy rows without a family remain searchable under the existing `ready + active + tenant + audience role` contract.
- Use deterministic, dependency-free filesystem and lifecycle helpers; no speculative scheduling or multi-level approval workflow.
- Follow test-driven development: each behavior test must fail for the expected missing capability before production code is added.

---

### Task 1: Governance schema and migration

**Files:**
- Modify: `app/models/document.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/a7b8c9d0e1f2_add_document_governance_lifecycle.py`
- Create: `tests/test_document_governance_migration.py`

**Interfaces:**
- Produces: `DocumentFamily`, `Document.family_id`, `version`, `index_generation`, lifecycle/source/lineage fields, and chunk generation lineage.
- Preserves: nullable `family_id` compatibility for manually created and pre-governance rows.

- [ ] **Step 1: Write migration tests that fail before the revision exists**

```python
def test_governance_migration_backfills_ready_document_as_current(connection):
    command.upgrade(config, "f6a7b8c9d0e1")
    document_id = insert_legacy_ready_document(connection)
    command.upgrade(config, "head")
    row = connection.execute(sa.text("SELECT family_id, version, index_generation, review_status FROM documents WHERE id=:id"), {"id": document_id}).one()
    family = connection.execute(sa.text("SELECT current_document_id FROM document_families WHERE id=:id"), {"id": row.family_id}).one()
    assert (row.version, row.index_generation, row.review_status) == (1, 1, "approved")
    assert family.current_document_id == document_id
```

- [ ] **Step 2: Run the focused migration test and confirm failure because the governance revision/columns do not exist**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_governance_migration.py -q`

- [ ] **Step 3: Add the minimum schema**

```python
class DocumentFamily(Base, TimestampMixin):
    __tablename__ = "document_families"
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    current_document_id = Column(String(36), nullable=True, index=True)

class Document(Base, TimestampMixin):
    family_id = Column(String(36), ForeignKey("document_families.id"), nullable=True, index=True)
    version = Column(Integer, default=1, nullable=False)
    index_generation = Column(Integer, default=1, nullable=False)
    review_status = Column(String(20), default="approved", nullable=False)
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    source_type = Column(String(30), default="upload", nullable=False)
    source_ref = Column(String(500), nullable=True)
    storage_key = Column(String(1000), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    chunker_version = Column(String(100), nullable=True)
    embedding_provider = Column(String(100), nullable=True)
    embedding_model = Column(String(200), nullable=True)
```

- [ ] **Step 4: Implement online migration and deterministic legacy backfill**

Create one family per legacy document. Point ready families at their ready document, mark ready rows approved, leave non-ready family pointers null, and set all legacy chunk generations to `1`. Keep offline migration structural only.

- [ ] **Step 5: Run migration tests, model tests, and migration smoke tests**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_governance_migration.py tests/test_migrations.py tests/test_document_provenance_migration.py -q`

- [ ] **Step 6: Commit**

```powershell
git add app/models/document.py app/models/__init__.py migrations/versions/a7b8c9d0e1f2_add_document_governance_lifecycle.py tests/test_document_governance_migration.py
git commit -m "feat(documents): add governance lifecycle schema"
```

---

### Task 2: D-drive original-file storage and governed upload snapshots

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Create: `app/services/document_storage.py`
- Modify: `app/services/document_service.py`
- Modify: `app/schemas/document.py`
- Modify: `app/api/admin/document.py`
- Create: `tests/test_document_storage.py`
- Modify: `tests/test_document_service.py`
- Modify: `tests/test_admin_document_api.py`

**Interfaces:**
- Produces: `store_original(tenant_id, file_hash, suffix, data) -> str`, `read_original(storage_key) -> bytes`, governed upload form fields, and governance response fields.
- Consumes: Task 1 models and existing `upload_document` parse/chunk/index path.

- [ ] **Step 1: Write failing filesystem tests**

```python
def test_store_original_returns_relative_content_addressed_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))
    key = store_original("tenant-1", "a" * 64, ".pdf", b"content")
    assert key == f"tenant-1/{'a' * 64}.pdf"
    assert read_original(key) == b"content"

def test_read_original_rejects_parent_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))
    with pytest.raises(ValueError, match="Invalid storage key"):
        read_original("../secret")
```

- [ ] **Step 2: Run storage tests and confirm import failure**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_storage.py -q`

- [ ] **Step 3: Implement content-addressed atomic storage with stdlib**

Use `pathlib.Path`, `tempfile.NamedTemporaryFile`, `os.replace`, relative keys, root containment checks, and the configured `document_storage_dir`. Do not return absolute server paths through the API.

- [ ] **Step 4: Write failing governed-upload tests**

Cover new-family creation, sequential version allocation within a tenant/family, `pending_review`, retained source key after parse failure, uploader ownership for JWT users, nullable owner for API-key uploads, expiry-before-effective rejection, and cross-tenant family rejection.

- [ ] **Step 5: Extend upload without changing parser/index behavior**

```python
async def upload_document(
    db: Session,
    tenant_id: str,
    tenant_slug: str,
    filename: str,
    file_data: bytes,
    audience_roles: list[str] | None = None,
    *,
    family_id: str | None = None,
    family_name: str | None = None,
    effective_date: date | None = None,
    expiry_date: date | None = None,
    owner_user_id: str | None = None,
) -> Document:
    ...
```

New snapshots explicitly set `review_status="pending_review"`, `index_generation=1`, `source_type="upload"`, source/storage/lineage fields, and chunk lineage. Existing parse, quality, embedding retry, and inactive-to-active index publication remain intact.

- [ ] **Step 6: Add safe API governance projection**

Expose family id/name, version, generation, dates, review status, owner/reviewer ids, current flag, source type/ref, and `original_file_available`; never expose `storage_key` or absolute paths.

- [ ] **Step 7: Run focused upload/storage/API tests**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_storage.py tests/test_document_service.py tests/test_admin_document_api.py -q`

- [ ] **Step 8: Commit**

```powershell
git add app/config.py .env.example app/services/document_storage.py app/services/document_service.py app/schemas/document.py app/api/admin/document.py tests/test_document_storage.py tests/test_document_service.py tests/test_admin_document_api.py
git commit -m "feat(documents): retain governed source snapshots"
```

---

### Task 3: Approval publication and SQL lifecycle authorization

**Files:**
- Modify: `app/schemas/document.py`
- Modify: `app/services/document_service.py`
- Modify: `app/api/admin/document.py`
- Modify: `app/core/agent/tools.py`
- Create: `tests/test_document_governance_service.py`
- Modify: `tests/test_admin_document_api.py`
- Modify: `tests/test_agent_tools.py`
- Modify: `tests/test_security.py`

**Interfaces:**
- Produces: `review_document(..., decision, reviewer_user_id) -> Document` and current-family SQL visibility filtering.
- Consumes: Task 1 family pointer and Task 2 pending snapshots.

- [ ] **Step 1: Write failing service tests for approval/rejection**

```python
def test_approval_atomically_switches_family_pointer(db, family, old_ready, new_ready):
    family.current_document_id = old_ready.id
    reviewed = review_document(db, tenant_id=family.tenant_id, document_id=new_ready.id, decision="approved", reviewer_user_id="reviewer")
    assert reviewed.review_status == "approved"
    assert family.current_document_id == new_ready.id

def test_failed_or_expired_document_cannot_be_approved(...):
    with pytest.raises(DocumentLifecycleError):
        review_document(...)
```

- [ ] **Step 2: Run focused tests and confirm missing lifecycle API failure**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_governance_service.py -q`

- [ ] **Step 3: Implement one review endpoint and lifecycle rules**

`POST /api/v1/admin/{tenant_slug}/documents/{document_id}/review` accepts `{"decision": "approved"}` or `{"decision": "rejected"}`. Approval requires `status=ready`, parse quality `passed`, a non-future effective date, and no expired date; rejection never changes the family pointer. The endpoint remains owner/admin and tenant scoped.

- [ ] **Step 4: Write failing SQL-boundary tests**

Prove pending, rejected, expired, future-effective, non-current, cross-tenant, and role-restricted candidates are absent even when both retrievers return their chunk ids. Prove a legacy family-less ready document remains visible.

- [ ] **Step 5: Add the lifecycle filter to the existing joined SQL query**

Use an outer join to `DocumentFamily` and require either legacy `family_id IS NULL` or `DocumentFamily.current_document_id == Document.id`, plus approved/effective/unexpired checks for governed rows. Keep `ready`, active chunk, tenant, and audience-role filtering unchanged.

- [ ] **Step 6: Prevent destructive deletion of the current published snapshot**

Return conflict for a current document. Deleting a non-current snapshot removes its external entries and deletes its original file only when no other row references the same storage key.

- [ ] **Step 7: Run lifecycle, API, retrieval, and security tests**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_governance_service.py tests/test_admin_document_api.py tests/test_agent_tools.py tests/test_security.py tests/test_primary_boundary.py -q`

- [ ] **Step 8: Commit**

```powershell
git add app/schemas/document.py app/services/document_service.py app/api/admin/document.py app/core/agent/tools.py tests/test_document_governance_service.py tests/test_admin_document_api.py tests/test_agent_tools.py tests/test_security.py
git commit -m "feat(documents): enforce governed publication"
```

---

### Task 4: Immutable reindex generation and failure-safe switch

**Files:**
- Modify: `app/services/document_service.py`
- Modify: `app/api/admin/document.py`
- Modify: `app/schemas/document.py`
- Create: `tests/test_document_reindex.py`

**Interfaces:**
- Produces: `reindex_document(db, tenant_id, tenant_slug, document_id, actor_user_id) -> Document`.
- Consumes: stored source from Task 2 and publication pointer from Task 3.

- [ ] **Step 1: Write failing successful-reindex test**

Assert a current document at `(version=2, index_generation=1)` creates a new row at `(2, 2)`, creates new chunk ids with generation/lineage, keeps source/business metadata, indexes all new chunks, then switches the family pointer to the new row.

- [ ] **Step 2: Write failing rollback tests**

For parse failure, review-required quality, embedding failure, vector failure, and BM25 failure, assert the old pointer and old active chunks remain unchanged. Assert partially added new external ids are cleaned best effort and new SQL chunks never become retrievable.

- [ ] **Step 3: Run reindex tests and confirm missing service failure**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_reindex.py -q`

- [ ] **Step 4: Extract a shared snapshot processing path**

Reuse one private parse/chunk/embed/index function from upload and reindex. Parameterize only the required final activation callback/flag; do not introduce a generic pipeline framework or plugin abstraction.

- [ ] **Step 5: Implement reindex and endpoint**

Only the current approved snapshot can be reindexed. Read its stored source, allocate `max(index_generation)+1` for the same family/version, build the new snapshot invisibly, then change `current_document_id` in the same commit that marks the new chunks active and document ready. Clean old external ids after the SQL switch; failures are logged and remain non-retrievable through SQL.

- [ ] **Step 6: Run reindex and document regression tests**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_reindex.py tests/test_document_service.py tests/test_parse_quality_gate.py tests/test_agent_tools.py -q`

- [ ] **Step 7: Commit**

```powershell
git add app/services/document_service.py app/api/admin/document.py app/schemas/document.py tests/test_document_reindex.py
git commit -m "feat(documents): add failure-safe reindex generations"
```

---

### Task 5: Demo, documentation, and stage acceptance

**Files:**
- Modify: `scripts/demo_enterprise_flow.py`
- Modify: `tests/test_demo_enterprise_flow.py`
- Modify: `docs/planning/ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-07-18-document-intelligence-knowledge-governance-design.md`
- Modify: `README.md`
- Modify: `docs/operations/local-hr-agent-demo.md`

**Interfaces:**
- Produces: an executable upload -> review -> employee query -> cited source -> reindex/rollback demonstration and evidence-backed stage report.

- [ ] **Step 1: Write failing demo-contract tests**

Require the script to upload a governed policy, approve it before employee chat, display family/version/generation, and invoke reindex without printing credentials or storage paths.

- [ ] **Step 2: Update the demo and operational docs**

Keep the existing enterprise flow, add the review call between upload and employee query, add a reindex call after the cited answer, and document the `D:` source directory plus the failed-reindex invariant.

- [ ] **Step 3: Run focused demo tests**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_demo_enterprise_flow.py -q`

- [ ] **Step 4: Run migration smoke on a fresh D-drive database**

```powershell
$root = 'D:/DevData/smartcs/m2-4-acceptance'
New-Item -ItemType Directory -Force $root | Out-Null
$env:DATABASE_URL = "sqlite:///$root/smartcs.db"
& D:/2026.07.09/conda-envs/smart-cs/python.exe -m alembic upgrade head
```

- [ ] **Step 5: Run focused M2-4 suite and full regression suite**

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_document_governance_migration.py tests/test_document_storage.py tests/test_document_governance_service.py tests/test_document_reindex.py tests/test_admin_document_api.py tests/test_agent_tools.py tests/test_security.py tests/test_demo_enterprise_flow.py -q`

Run: `D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest -q`

- [ ] **Step 6: Run repository hygiene and secret checks**

Run: `git diff --check`

Run: `git status --short`

Run: `git grep -n -E 'sk-ws-|LLM_API_KEY=.+|EMBEDDING_API_KEY=.+' -- ':!*.example'`

- [ ] **Step 7: Commit delivery artifacts**

```powershell
git add scripts/demo_enterprise_flow.py tests/test_demo_enterprise_flow.py docs/planning/ROADMAP.md docs/superpowers/specs/2026-07-18-document-intelligence-knowledge-governance-design.md README.md docs/operations/local-hr-agent-demo.md
git commit -m "docs: deliver M2-4 governance lifecycle"
```

- [ ] **Step 8: Request whole-branch review, fix Critical/Important findings, re-run full verification, fast-forward main, and push**

Expected final evidence: migration succeeds on a fresh D-drive SQLite database; all tests pass; a failed reindex leaves the previous approved source searchable; no secrets or absolute storage paths are tracked.

