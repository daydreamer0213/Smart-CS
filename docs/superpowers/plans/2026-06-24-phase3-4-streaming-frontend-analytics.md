# SmartCS Phase 3+4 — Streaming + Frontend + Analytics + Production

> **For agentic workers:** Use superpowers:subagent-driven-development.

**Goal:** SSE streaming chat + chat widget + admin panel + analytics dashboard + rate limiting + Docker.

## Global Constraints

- Python 3.12, conda `smart-cs`, Python at `C:/Users/39823/.conda/envs/smart-cs/python.exe`
- All frontends: vanilla HTML/CSS/JS, zero build steps
- SSE format: `text/event-stream`, events: `delta`, `sources`, `done`
- Rate limit: token bucket per tenant, `X-RateLimit-Remaining` header
- Docker: Python 3.12-slim base, uvicorn, docker-compose with ChromaDB volume

---

### Task 0: Add SSE streaming to LLM client + chat_service

**Files:** `app/core/llm/client.py`, `app/services/chat_service.py`, `app/api/chat.py`

- [ ] Add `chat_stream()` method to `LLMClient`:
```python
async def chat_stream(self, messages, **kwargs):
    stream = await self._client.chat.completions.create(
        model=self._model, messages=messages, stream=True, **kwargs
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

- [ ] Add `process_chat_stream()` to `chat_service` — same pipeline as `process_chat` but yields SSE events:
```python
async def process_chat_stream(db, tenant, session_id, message):
    # Same: L1/L2 cache check, intent, retrieval
    # Different: LLM generation → yield SSE deltas
    yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
    async for token in llm.chat_stream(messages):
        yield f"data: {json.dumps({'type': 'delta', 'data': token})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'data': response_dict})}\n\n"
```

- [ ] Add SSE endpoint to `app/api/chat.py`:
```python
@router.get("/api/v1/{tenant_slug}/chat/stream")
async def chat_stream(request, session_id, message, db=Depends(get_db)):
    return StreamingResponse(
        process_chat_stream(db, request.state.tenant, session_id, message),
        media_type="text/event-stream",
    )
```

---

### Task 1: Chat widget frontend (`static/chat.html`)

Single-file vanilla HTML/CSS/JS chat widget with:
- Clean chat UI with message bubbles (user right, assistant left)
- Text input + send button
- SSE streaming response display (tokens appear as they arrive)
- Source references shown below assistant messages
- session_id persistence via localStorage
- Responsive design, embeddable in iframe

---

### Task 2: Admin panel frontend (`admin-static/`)

Two-tab admin SPA:

**Tab 1 — Knowledge Management:**
- Table with pagination, search bar, category filter
- "Add New" button → modal form (question, answer, keywords, category)
- Edit button on each row → pre-filled modal form
- Delete button → confirm dialog
- Batch import textarea (JSON array)

**Tab 2 — Analytics Dashboard:**
- Overview cards (total conversations, avg latency, cache hit rate)
- Simple bar chart for intent distribution (HTML canvas)
- Simple line chart for daily trend (HTML canvas)
- Knowledge hit ranking table

All API calls use X-Admin-Key from localStorage.

---

### Task 3: Analytics service + API endpoints

**Files:** `app/services/analytics_service.py`, `app/api/admin/analytics.py`

```python
def get_overview(db, tenant_id, days=7):
    return {"total_conversations": ..., "avg_latency_ms": ..., "cache_hit_rate": ..., "handoff_rate": ...}

def get_intent_distribution(db, tenant_id, days=7):
    return [{"intent": "faq", "count": 150}, {"intent": "human", "count": 30}]

def get_daily_trend(db, tenant_id, days=30):
    return [{"date": "2026-06-24", "total": 45, "hits": 30}, ...]

def get_top_knowledge(db, tenant_id, days=7, limit=10):
    return [{"question": "...", "count": 25}, ...]
```

Admin analytics endpoints already have stub routes — replace with real implementations.

---

### Task 4: Rate limiting middleware

**Files:** `app/middleware/ratelimit.py`, `app/main.py`

Simple in-memory token bucket per tenant:
```python
class RateLimiter:
    def __init__(self, rpm=30):
        self._buckets: dict[str, tuple[float, int]] = {}  # tenant → (last_refill, tokens)
    
    async def check(self, tenant_slug) -> tuple[bool, int]:
        # Refill tokens, consume 1, return (allowed, remaining)
```

Middleware adds `X-RateLimit-Remaining` header. Register in main.py.

---

### Task 5: Dockerfile + docker-compose.yml

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
version: "3.8"
services:
  app:
    build: .
    ports: ["8000:8000"]
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
    volumes:
      - ./chroma_data:/app/chroma_data
      - ./smartcs.db:/app/smartcs.db
```

---

### Task 6: Final tests + verification

- Update test_e2e.py with actual end-to-end chat flow test
- Add test_ratelimit.py
- Run full test suite
- Manual: open chat.html in browser, send message, verify streaming response
- Manual: open admin panel, CRUD knowledge item, verify analytics dashboard shows data
