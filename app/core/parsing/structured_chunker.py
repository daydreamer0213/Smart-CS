"""Deterministic structural chunking for normalized parsed documents."""

import tiktoken

from app.core.parsing.contracts import KnowledgeChunk, ParsedDocument, ParsedElement


MAX_TOKENS = 800
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_count(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_text(text: str) -> list[str]:
    tokens = _ENCODING.encode(text)
    return [
        _ENCODING.decode(tokens[start : start + MAX_TOKENS]).strip()
        for start in range(0, len(tokens), MAX_TOKENS)
    ]


def _split_table(text: str) -> list[str]:
    lines = text.splitlines()
    if len(lines) < 3:
        return _split_text(text)

    header = "\n".join(lines[:2])
    chunks: list[str] = []
    rows: list[str] = []
    for row in lines[2:]:
        candidate = "\n".join([header, *rows, row])
        if rows and _token_count(candidate) > MAX_TOKENS:
            chunks.append("\n".join([header, *rows]))
            rows = [row]
        else:
            rows.append(row)
    if rows:
        chunks.append("\n".join([header, *rows]))
    return chunks or _split_text(text)


def _element_parts(element: ParsedElement) -> list[str]:
    content = element.table_markdown or element.text
    if _token_count(content) <= MAX_TOKENS:
        return [content]
    if element.element_type == "table":
        return _split_table(content)
    return _split_text(content)


def _contextualized_content(title: str, section_path: list[str], content: str) -> str:
    context = "\n".join(part for part in (title.strip(), " > ".join(section_path)) if part)
    return f"{context}\n\n{content}" if context else content


def _chunk(
    content: str,
    element: ParsedElement,
    source_element_indexes: list[int],
) -> KnowledgeChunk:
    return KnowledgeChunk(
        content=content,
        contextualized_content=_contextualized_content("", element.section_path, content),
        page_start=element.page_start,
        page_end=element.page_end,
        section_path=element.section_path,
        element_types=[element.element_type],
        source_element_indexes=source_element_indexes,
        token_count=_token_count(content),
    )


def chunk_document(document: ParsedDocument, title: str) -> list[KnowledgeChunk]:
    """Create tokenizer-bounded chunks without calling a language model."""
    chunks: list[KnowledgeChunk] = []
    for index, element in enumerate(document.elements):
        for content in _element_parts(element):
            chunk = _chunk(content, element, [index])
            chunk.contextualized_content = _contextualized_content(title, chunk.section_path, content)
            if (
                chunks
                and element.element_type in {"paragraph", "list"}
                and chunk.element_types == chunks[-1].element_types
                and chunk.section_path == chunks[-1].section_path
                and _token_count(f"{chunks[-1].content}\n\n{content}") <= MAX_TOKENS
            ):
                previous = chunks[-1]
                previous.content = f"{previous.content}\n\n{content}"
                previous.contextualized_content = _contextualized_content(
                    title, previous.section_path, previous.content
                )
                previous.page_start = previous.page_start or chunk.page_start
                previous.page_end = chunk.page_end or previous.page_end
                previous.source_element_indexes.append(index)
                previous.token_count = _token_count(previous.content)
            else:
                chunks.append(chunk)
    return chunks
