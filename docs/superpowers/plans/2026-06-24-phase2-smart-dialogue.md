# SmartCS Phase 2 — Smart Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Implement full chat pipeline: intent classification → hybrid retrieval → LLM generation → caching → persistence.

**Architecture:** Night 3 builds LLM client, prompts, intent classifier, chat_service pipeline (intent→retrieval→LLM→return). Night 4 adds L1/L2 cache, sliding window, conversation persistence.

**Tech Stack:** FastAPI + openai SDK + structlog + ChromaDB + BM25 + RRF + tiktoken

## Global Constraints

- Python 3.12, conda `smart-cs`, Python at `C:/Users/39823/.conda/envs/smart-cs/python.exe`
- LLM: DeepSeek API (OpenAI-compatible), model: deepseek-chat
- Intent labels: "faq" / "human" only (not ShopMind's 5-class)
- Human keywords from `tenant.config_json.human_keywords`, NOT globals
- 3 retry on LLM failure (timeout/429/5xx), exponential backoff 1s/2s/4s
- L1 cache TTL 300s, L2 threshold 0.85
- Sliding window: max_tokens=2000, max_turns=10
- Chat endpoint: `POST /api/v1/{tenant_slug}/chat`, no admin auth required

---

### Task 0: Install tiktoken

```bash
C:/Users/39823/.conda/envs/smart-cs/python.exe -m pip install tiktoken
```

---

### Task 1: schemas/chat.py — ChatRequest + ChatResponse

**Files:** Modify `app/schemas/chat.py`

```python
"""Chat request/response schemas."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field("", description="Client-generated UUID, empty on first message")
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    intent: str  # "faq" | "human"
    confidence: float
    sources: list[dict]  # [{"question": "...", "answer": "...", "score": 0.95}, ...]
    cache_hit: str  # "L1" | "L2" | "miss"
    session_id: str
```

Verification: `python -c "from app.schemas.chat import ChatRequest, ChatResponse; print('OK')"`

---

### Task 2: app/core/llm/client.py — LLM Client with Retry

**Files:** Modify `app/core/llm/client.py`

```python
"""LLM client with retry and structured output."""

import asyncio
import time

import structlog
from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel

logger = structlog.get_logger()

RETRYABLE = (APITimeoutError, RateLimitError)


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
        self._model = model
        self._max_retries = 3

    async def chat(
        self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 1000
    ) -> str:
        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content or ""
            except RETRYABLE as e:
                wait = 2 ** attempt
                logger.warning("llm_retry", attempt=attempt + 1, wait=wait, error=str(e))
                if attempt == self._max_retries - 1:
                    raise
                await asyncio.sleep(wait)
            except Exception:
                raise

    async def chat_structured(
        self, messages: list[dict], output_class: type[BaseModel]
    ) -> BaseModel:
        completion = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=output_class,
            temperature=0.0,
        )
        result = completion.choices[0].message.parsed
        if result is None:
            content = completion.choices[0].message.content or "{}"
            return output_class.model_validate_json(content)
        return result
```

Verification: `python -c "from app.core.llm.client import LLMClient; print('OK')"`

---

### Task 3: app/core/llm/prompts.py — Prompt Templates

**Files:** Modify `app/core/llm/prompts.py`

```python
"""Prompt templates — multi-tenant, adapted from ShopMind."""

HANDOFF_MESSAGE = "已为您记录问题并转接人工客服，请稍等。"


def build_system_prompt(tenant_name: str, append: str = "") -> str:
    base = (
        f"你是 {tenant_name} 的智能客服。"
        "你只能根据提供的知识库内容回答问题，不要编造信息。"
        "回答要简洁、礼貌、专业。"
        "如果知识库中没有相关信息，请如实告知用户。"
    )
    if append:
        base = f"{base}\n\n{append}"
    return base


def intent_prompt(user_input: str, human_keywords: list[str]) -> str:
    keywords_text = "、".join(human_keywords) if human_keywords else "转人工、人工客服"
    return (
        f"用户输入：{user_input}\n\n"
        f"请判断用户意图。只能返回 faq 或 human。\n"
        f"faq：用户咨询知识库可回答的问题。\n"
        f"human：用户触发以下关键词需要转人工：{keywords_text}；"
        f"或者用户情绪激烈、要求投诉、问题超出知识库范围。\n"
        f'返回格式：{{"intent": "faq或human", "confidence": 0.0到1.0之间的数字}}'
    )


def response_prompt(
    intent: str,
    context_docs: list[dict],
    history: list[dict],
    user_input: str,
) -> str:
    ctx = ""
    if context_docs:
        parts = []
        for i, doc in enumerate(context_docs, 1):
            parts.append(
                f"[{i}] 问题：{doc.get('question', '')}\n"
                f"    答案：{doc.get('answer', '')}"
            )
        ctx = "\n".join(parts)
    else:
        ctx = "未找到相关知识条目。"

    history_text = ""
    for m in history[-10:]:
        role = m.get("role", "user")
        content = m.get("content", "")
        history_text += f"{role}: {content}\n"

    return (
        f"知识库检索结果：\n{ctx}\n\n"
        f"对话历史：\n{history_text}\n"
        f"用户输入：{user_input}\n\n"
        f"请根据检索结果生成简洁、礼貌的中文回复。"
        f"如果检索结果为'未找到'，请告知用户暂时无法回答该问题并建议联系人工客服。"
    )
```

Verification: `python -c "from app.core.llm.prompts import build_system_prompt, intent_prompt, response_prompt; print('OK')"`

---

### Task 4: app/core/intent/classifier.py — Intent Classifier

**Files:** Modify `app/core/intent/classifier.py`

```python
"""Rule + LLM hybrid intent classifier — per-tenant keyword configuration."""

import structlog
from pydantic import BaseModel, Field

from app.core.llm.client import LLMClient

logger = structlog.get_logger()


class IntentOutput(BaseModel):
    intent: str = Field(..., description="faq or human")
    confidence: float = Field(..., ge=0.0, le=1.0)


async def classify_intent(
    user_input: str,
    human_keywords: list[str],
    retrieval_results: list[dict],
    llm_client: LLMClient | None = None,
    confidence_threshold: float = 0.6,
) -> tuple[str, str, float]:
    """
    Returns (intent, source, confidence)
    intent ∈ {"faq", "human"}
    source ∈ {"rule_human", "rule_faq", "llm"}
    """
    lowered = user_input.lower()

    for kw in human_keywords:
        if kw in lowered:
            logger.info("intent_rule_human", keyword=kw, input=user_input[:50])
            return ("human", "rule_human", 1.0)

    if retrieval_results:
        logger.info("intent_rule_faq", results=len(retrieval_results))
        return ("faq", "rule_faq", 0.8)

    if llm_client:
        from app.core.llm.prompts import intent_prompt
        try:
            result = await llm_client.chat_structured(
                [
                    {"role": "system", "content": "你是一个意图分类器，只返回JSON。"},
                    {"role": "user", "content": intent_prompt(user_input, human_keywords)},
                ],
                IntentOutput,
            )
            if result.confidence >= confidence_threshold:
                return (result.intent, "llm", result.confidence)
        except Exception as e:
            logger.error("intent_llm_failed", error=str(e))

    return ("human", "llm", 0.0)
```

Verification: `python -c "from app.core.intent.classifier import classify_intent, IntentOutput; print('OK')"`

---

### Task 5: app/services/chat_service.py — Chat Pipeline (Night 3)

**Files:** Modify `app/services/chat_service.py`

Night 3 version: intent → retrieval → LLM → return. No cache, no persistence.

```python
"""Chat pipeline orchestrator."""

import time

import structlog

from app.config import settings
from app.core.intent.classifier import classify_intent
from app.core.llm.client import LLMClient
from app.core.llm.prompts import HANDOFF_MESSAGE, build_system_prompt, response_prompt
from app.core.retrieval_module import get_bm25_manager, get_embedding_provider, get_vector_store
from app.core.retrieval.fusion import rrf_fusion
from app.schemas.chat import ChatResponse

logger = structlog.get_logger()

_llm_client: LLMClient | None = None


def _get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    return _llm_client


async def _retrieve(tenant_slug: str, query: str) -> list[dict]:
    vs = get_vector_store()
    bm = get_bm25_manager()
    emb = get_embedding_provider()

    query_vec = (await emb.embed([query]))[0]
    vector_results = vs.search(tenant_slug, query_vec, top_k=5)
    bm25_results = bm.search(tenant_slug, query, top_k=5)

    fused = rrf_fusion(vector_results, bm25_results, top_k=5)

    # Enrich with knowledge item content
    return [
        {
            "doc_id": r["doc_id"],
            "score": r["score"],
            "sources": r["sources"],
        }
        for r in fused
    ]


async def process_chat(
    tenant_slug: str,
    tenant_name: str,
    tenant_config: dict,
    session_id: str,
    message: str,
) -> ChatResponse:
    t0 = time.monotonic()

    # Step 1: Hybrid retrieval
    retrieval_results = await _retrieve(tenant_slug, message)

    # Step 2: Intent classification
    intent, source, confidence = await classify_intent(
        user_input=message,
        human_keywords=tenant_config.get("human_keywords", []),
        retrieval_results=retrieval_results,
        llm_client=_get_llm(),
        confidence_threshold=tenant_config.get(
            "intent_threshold_override", settings.intent_confidence_threshold
        ),
    )

    # Step 3: Human handoff
    if intent == "human":
        return ChatResponse(
            answer=HANDOFF_MESSAGE,
            intent="human",
            confidence=confidence,
            sources=[],
            cache_hit="miss",
            session_id=session_id,
        )

    # Step 4: LLM generation
    llm = _get_llm()
    system_prompt = build_system_prompt(
        tenant_name,
        tenant_config.get("system_prompt_append", ""),
    )
    prompt = response_prompt(intent, retrieval_results[:3], [], message)
    answer = await llm.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ])

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "chat_completed",
        intent=intent,
        source=source,
        results=len(retrieval_results),
        latency_ms=round(elapsed, 2),
    )

    return ChatResponse(
        answer=answer,
        intent=intent,
        confidence=confidence,
        sources=retrieval_results[:3],
        cache_hit="miss",
        session_id=session_id,
    )
```

---

### Task 6: app/api/chat.py — Chat Endpoint

**Files:** Modify `app/api/chat.py`

```python
"""Customer chat endpoint."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.middleware.tenant import TenantMiddleware
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import process_chat

router = APIRouter()


@router.post("/api/v1/{tenant_slug}/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    tenant = request.state.tenant
    session_id = body.session_id or str(uuid.uuid4())

    return await process_chat(
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        tenant_config=tenant.config_json or {},
        session_id=session_id,
        message=body.message,
    )
```

---

### Task 7: tests/test_intent.py + test_llm_client.py — Night 3 Tests

**test_intent.py** — 4 tests:
- `test_rule_human_keyword_match`: input "我要投诉", keywords=["投诉"] → ("human", "rule_human", 1.0)
- `test_rule_faq_has_results`: retrieval has 1 result → ("faq", "rule_faq", 0.8)
- `test_rule_no_match_no_results_no_llm`: no keywords, no results, no llm → ("human", "llm", 0.0)
- `test_llm_classifier_called`: no keywords, no results, mock llm returns faq with 0.9 → ("faq", "llm", 0.9)

**test_llm_client.py** — 3 tests:
- `test_chat_structured_parses_json`: mock response with `{"intent": "faq", "confidence": 0.85}`
- `test_retry_on_timeout`: mock APITimeoutError 2x then success
- `test_no_retry_on_4xx`: mock 401 → raises immediately

All tests mock the DeepSeek API (no real calls).

---

### Task 8: app/core/cache/exact.py — L1 Exact Cache

**Files:** Modify `app/core/cache/exact.py`

```python
"""L1 exact-match cache — per-tenant, TTL-based."""

import time


class ExactCache:
    def __init__(self):
        self._store: dict[str, tuple[float, str]] = {}

    def _key(self, tenant_id: str, question: str) -> str:
        return f"{tenant_id}:{question.strip().lower()}"

    def get(self, tenant_id: str, question: str) -> str | None:
        entry = self._store.get(self._key(tenant_id, question))
        if entry and time.time() < entry[0]:
            return entry[1]
        return None

    def set(self, tenant_id: str, question: str, answer: str, ttl: int = 300):
        self._store[self._key(tenant_id, question)] = (time.time() + ttl, answer)

    def invalidate(self, tenant_id: str):
        prefix = f"{tenant_id}:"
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
```

---

### Task 9: app/core/cache/semantic.py — L2 Semantic Cache

**Files:** Modify `app/core/cache/semantic.py`

```python
"""L2 semantic cache — per-tenant, cosine similarity."""

import math


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticCache:
    def __init__(self):
        self._store: dict[str, list[tuple[list[float], str]]] = {}

    def get(self, tenant_id: str, query_emb: list[float], threshold: float = 0.85) -> str | None:
        entries = self._store.get(tenant_id, [])
        best_score, best_answer = 0.0, None
        for emb, answer in entries:
            score = _cosine(query_emb, emb)
            if score > best_score:
                best_score, best_answer = score, answer
        return best_answer if best_score >= threshold else None

    def set(self, tenant_id: str, embedding: list[float], answer: str):
        self._store.setdefault(tenant_id, []).append((embedding, answer))

    def invalidate(self, tenant_id: str):
        self._store.pop(tenant_id, None)
```

---

### Task 10: app/core/conversation/memory.py — Sliding Window

**Files:** Modify `app/core/conversation/memory.py`

```python
"""Sliding window context management with tiktoken counting."""

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += len(_enc.encode(m.get("content", "")))
        total += 4  # role + message overhead
    return total


def build_context(
    history: list[dict],
    max_tokens: int = 2000,
    max_turns: int = 10,
) -> list[dict]:
    result = history[-max_turns * 2:]  # each turn = user + assistant
    while count_tokens(result) > max_tokens and len(result) > 2:
        result = result[2:]  # drop oldest turn
    return result
```

---

### Task 11: Update chat_service + retrieval_module for caches

**Files:** Modify `app/services/chat_service.py` — add cache + persistence.
Modify `app/core/retrieval_module.py` — add cache singletons.

**chat_service.py Night 4 additions:**
- Before retrieval: check L1 → L2 cache
- After LLM generation: set L1 + L2 cache
- After response: persist Conversation + Message

**retrieval_module.py additions:**
```python
_l1_cache = None
_l2_cache = None

def get_l1_cache():
    ...
def get_l2_cache():
    ...
# + set methods
```

**main.py lifespan:** Initialize `ExactCache()` + `SemanticCache()` on `retrieval_module`.

---

### Task 12: Tests — Cache + Memory + Chat API + E2E

**test_cache.py** — 4 tests: L1 get/set/invalidate, L2 get/set/similarity  
**test_memory.py** — 3 tests: token count, turn limit, empty history  
**test_chat_api.py** — 5 tests: chat with seeded FAQ, human handoff, missing tenant, invalid body, session_id generated  
**test_e2e.py** — 2 tests: multi-turn conversation, cache hit on repeated question  

---

### Task 13: Final Integration Verification

```bash
# Full test suite
python -m pytest tests/ -v

# Manual curl
curl -X POST http://127.0.0.1:8000/api/v1/demo/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"","message":"退货要几天？"}'
# Expected: {"answer":"...7天...", "intent":"faq", "sources":[...], "cache_hit":"miss"}
```

Expected: 40+ tests pass, chat endpoint returns FAQ answer with sources.
