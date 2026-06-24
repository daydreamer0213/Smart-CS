"""Chunking engine — structure-aware -> LLM semantic -> fixed-size fallback."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_CHUNK_SIZE = 1000

_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", ".", "！", "？", "；", ";", "，", ",", " "],
    keep_separator=True,
)


def _struct_chunk(text: str) -> list[str]:
    """Try to split by document structure: headings, double-newlines, rows."""
    # md/docx headings: split on ## or similar markers
    if "## " in text or "\n## " in text:
        sections = re.split(r"\n(?=#{1,4}\s)", text)
    else:
        # plain text: split on double newlines (paragraphs)
        sections = text.split("\n\n")
    return [s.strip() for s in sections if s.strip()]


async def _semantic_chunk(text: str) -> list[str]:
    """Use DeepSeek LLM to find semantic boundaries in a long text block.

    Returns a list of semantically coherent sub-blocks.
    """
    from openai import AsyncOpenAI

    from app.config import settings

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=30.0,
    )
    prompt = (
        "将以下文本按语义边界切分为多个段落（每段 300-800 字），"
        "用 \\n---\\n 分隔各段。\n\n"
        f"{text}"
    )
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=2000,
    )
    result = resp.choices[0].message.content or text
    parts = [p.strip() for p in result.split("\n---\n") if p.strip()]
    # If LLM returned just one block or empty, fall through to fixed split
    if len(parts) <= 1:
        return _fixed_chunk(text)
    return parts


def _fixed_chunk(text: str) -> list[str]:
    """Fixed-size split with overlap — last-resort fallback."""
    docs = _fallback_splitter.create_documents([text])
    return [d.page_content for d in docs if d.page_content.strip()]


async def chunk_text(text: str) -> list[str]:
    """Produce chunks from raw document text.

    Strategy:
      1. Split by document structure (headings/paragraphs)
      2. For each oversized block, try LLM semantic boundary detection
      3. If semantic chunking produces nothing useful, use fixed-size split
    """
    if not text.strip():
        return []

    chunks = []
    struct_blocks = _struct_chunk(text)

    for block in struct_blocks:
        if len(block) <= MAX_CHUNK_SIZE:
            chunks.append(block)
        else:
            try:
                sub_blocks = await _semantic_chunk(block)
            except Exception:
                sub_blocks = _fixed_chunk(block)
            chunks.extend(sub_blocks)

    return [c for c in chunks if c.strip()]
