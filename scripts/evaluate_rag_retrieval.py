"""Deterministic real-corpus evaluator for the M2-5 RAG retrieval gate."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
import unicodedata
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def load_rag_manifest(fixture_dir: Path, manifest_path: Path | None = None) -> dict:
    """Load golden retrieval cases and resolve their approved fixture evidence."""
    fixture_dir = Path(fixture_dir)
    manifest_path = Path(manifest_path) if manifest_path else fixture_dir / "rag_manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    document_manifest = json.loads(
        (fixture_dir / raw_manifest["document_manifest"]).read_text(encoding="utf-8")
    )
    fixtures = {item["id"]: item for item in document_manifest["fixtures"]}
    queries = raw_manifest["queries"]
    query_labels = {
        (item.get("fixture_id"), item.get("required_text")) for item in queries
    }
    indexable_fixture_ids = {
        fixture_id
        for fixture_id, fixture in fixtures.items()
        if fixture.get("expected_indexable") is True
    }
    query_fixture_ids = {item.get("fixture_id") for item in queries}

    if (
        raw_manifest.get("top_k") != 3
        or raw_manifest.get("minimum_recall_at_k") != 0.90
        or raw_manifest.get("minimum_provenance_accuracy") != 1.00
        or len(queries) != 12
        or len({item.get("id") for item in queries}) != 12
    ):
        raise ValueError("Invalid RAG evaluation manifest")
    if len(query_labels) != len(queries):
        raise ValueError("RAG queries must use unique fixture facts")
    if query_fixture_ids != indexable_fixture_ids:
        raise ValueError("RAG queries must cover all indexable fixtures")

    resolved_queries = []
    for query in queries:
        fixture = fixtures.get(query.get("fixture_id"))
        required_text = query.get("required_text")
        if not fixture or not fixture.get("expected_indexable") or required_text not in fixture.get("required_facts", []):
            raise ValueError("RAG query must reference an indexable fixture fact")
        provenance = next(
            (item for item in fixture["expected_fact_provenance"] if item["fact"] == required_text),
            None,
        )
        if not isinstance(query.get("id"), str) or not isinstance(query.get("question"), str) or provenance is None:
            raise ValueError("Invalid RAG query")
        resolved_queries.append(
            {
                "id": query["id"],
                "question": query["question"],
                "expected": {
                    "title": fixture["filename"],
                    "required_text": required_text,
                    "page_start": provenance["page_start"],
                    "page_end": provenance["page_end"],
                    "section_path": provenance["section_path"],
                    "indexable": True,
                },
            }
        )
    return {
        "schema_version": raw_manifest.get("schema_version"),
        "top_k": raw_manifest["top_k"],
        "minimum_recall_at_k": raw_manifest["minimum_recall_at_k"],
        "minimum_provenance_accuracy": raw_manifest["minimum_provenance_accuracy"],
        "queries": resolved_queries,
    }


def _covers_provenance(chunk: dict[str, Any], evidence: dict[str, Any]) -> bool:
    expected_start = evidence.get("page_start")
    expected_end = evidence.get("page_end")
    if expected_start is None or expected_end is None:
        pages_match = chunk.get("page_start") is None and chunk.get("page_end") is None
    else:
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        pages_match = (
            isinstance(page_start, int)
            and isinstance(page_end, int)
            and page_start <= expected_start
            and page_end >= expected_end
        )
    return pages_match and chunk.get("section_path") == evidence.get("section_path")


def load_rag_corpus(fixture_dir: Path, corpus_path: Path | None = None) -> dict:
    """Load the curated retrieval corpus and validate it against parser-gate facts."""
    fixture_dir = Path(fixture_dir)
    corpus_path = Path(corpus_path) if corpus_path else fixture_dir / "rag_corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    document_manifest = json.loads(
        (fixture_dir / "manifest.json").read_text(encoding="utf-8")
    )
    fixtures = {item["id"]: item for item in document_manifest["fixtures"]}
    indexable = {
        fixture_id: fixture
        for fixture_id, fixture in fixtures.items()
        if fixture.get("expected_indexable") is True
    }
    chunks = corpus.get("chunks")
    if (
        corpus.get("schema_version") != 1
        or corpus.get("origin") != "curated-retrieval-corpus"
        or corpus.get("source_parser_gate") != "smartcs-structured-parser"
        or not isinstance(chunks, list)
    ):
        raise ValueError("Invalid curated RAG corpus")

    chunk_ids = [chunk.get("id") for chunk in chunks]
    if len(chunks) != 12 or len(set(chunk_ids)) != 12 or not all(
        isinstance(chunk_id, str) and chunk_id for chunk_id in chunk_ids
    ):
        raise ValueError("RAG corpus must contain 12 unique chunks")

    chunks_by_fixture: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        fixture_id = chunk.get("fixture_id")
        fixture = indexable.get(fixture_id)
        if (
            fixture is None
            or chunk.get("title") != fixture["filename"]
            or not isinstance(chunk.get("content"), str)
            or not isinstance(chunk.get("section_path"), list)
            or not isinstance(chunk.get("element_types"), list)
            or not chunk["element_types"]
        ):
            raise ValueError("RAG corpus must contain only indexable fixtures")
        chunks_by_fixture.setdefault(fixture_id, []).append(chunk)

    expected_chunk_counts = {
        "clean-policy": 1,
        "repeated-headers": 1,
        "leave-table": 2,
        "scanned-policy": 1,
        "mixed-policy": 1,
        "two-column-policy": 1,
        "headed-docx": 3,
        "multi-sheet-xlsx": 2,
    }
    if {
        fixture_id: len(items) for fixture_id, items in chunks_by_fixture.items()
    } != expected_chunk_counts:
        raise ValueError("RAG corpus must cover all indexable fixtures")

    for fixture_id, fixture in indexable.items():
        fixture_chunks = chunks_by_fixture[fixture_id]
        for evidence in fixture["expected_fact_provenance"]:
            matching_chunks = [
                chunk for chunk in fixture_chunks
                if _normalized_text(evidence["fact"]) in _normalized_text(chunk["content"])
            ]
            if not matching_chunks:
                raise ValueError(f"Missing required fact for fixture {fixture_id}")
            if not any(_covers_provenance(chunk, evidence) for chunk in matching_chunks):
                raise ValueError(f"Invalid fact provenance for fixture {fixture_id}")
    return corpus


def _matches_expected(result: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        result.get("title") == expected["title"]
        and _normalized_text(expected["required_text"]) in _normalized_text(result.get("content"))
    )


def _has_expected_provenance(result: dict[str, Any], expected: dict[str, Any]) -> bool:
    return _covers_provenance(result, expected)


def evaluate_results(manifest: dict, results_by_query: dict[str, list[dict]]) -> dict:
    """Evaluate retrieval output without retaining source text or file paths."""
    rows = []
    failed_query_ids = []
    reciprocal_ranks = []
    provenance_matches = 0
    for query in manifest["queries"]:
        expected = query["expected"]
        rank = next(
            (
                index
                for index, result in enumerate(results_by_query.get(query["id"], [])[: manifest["top_k"]], start=1)
                if _matches_expected(result, expected)
            ),
            None,
        )
        if rank is None:
            failed_query_ids.append(query["id"])
            reciprocal_ranks.append(0.0)
            rows.append({
                "query_id": query["id"],
                "rank": None,
                "retrievers": [],
            })
            continue
        result = results_by_query[query["id"]][rank - 1]
        provenance_passed = _has_expected_provenance(result, expected)
        reciprocal_ranks.append(1 / rank)
        provenance_matches += int(provenance_passed)
        if not provenance_passed:
            failed_query_ids.append(query["id"])
        rows.append(
            {
                "query_id": query["id"],
                "rank": rank,
                "retrievers": [
                    source for source in result.get("retrievers", []) if source in {"vector", "bm25"}
                ],
            }
        )

    query_count = len(manifest["queries"])
    recall = sum(rank > 0 for rank in reciprocal_ranks) / query_count
    provenance_accuracy = provenance_matches / query_count
    gate_passed = (
        recall >= manifest["minimum_recall_at_k"]
        and provenance_accuracy >= manifest["minimum_provenance_accuracy"]
    )
    return {
        "results": rows,
        "failed_query_ids": failed_query_ids,
        "summary": {
            "recall_at_k": recall,
            "mrr": sum(reciprocal_ranks) / query_count,
            "provenance_accuracy": provenance_accuracy,
            "gate": "passed" if gate_passed else "failed",
        },
    }


def _require_d_drive(path: Path, label: str) -> Path:
    resolved = Path(path).resolve()
    if os.name == "nt" and resolved.drive.upper() != "D:":
        raise ValueError(f"{label} must be on D: on Windows")
    return resolved


def _load_corpus_manifests(fixture_dir: Path) -> tuple[dict, dict[str, bytes]]:
    sources = {
        "manifest": (fixture_dir / "manifest.json").read_bytes(),
        "rag_manifest": (fixture_dir / "rag_manifest.json").read_bytes(),
        "rag_corpus": (fixture_dir / "rag_corpus.json").read_bytes(),
    }
    return json.loads(sources["manifest"]), sources


async def _index_and_search(
    *,
    session,
    tenant,
    indexed_chunks: list[tuple[Any, str]],
    manifest: dict,
    embedding,
    vector_store,
    bm25,
    search_tool,
    set_runtime,
) -> dict[str, list[dict]]:
    texts = [text for _, text in indexed_chunks]
    vectors = await embedding.embed(texts)
    for (chunk, contextualized_content), vector in zip(indexed_chunks, vectors):
        vector_store.add(
            tenant.slug,
            chunk.id,
            vector,
            metadata={"source": "document", "document_id": chunk.document_id},
        )
        bm25.add(tenant.slug, chunk.id, chunk.content)

    set_runtime(tenant.slug, session, role="employee", tenant_id=tenant.id)
    results_by_query = {}
    for query in manifest["queries"]:
        payload = json.loads(
            await search_tool.ainvoke({"query": query["question"]})
        )
        results_by_query[query["id"]] = payload.get("results", [])
    return results_by_query


def run_evaluation(
    fixture_dir: Path,
    work_dir: Path,
    environment_label: str,
) -> dict:
    """Build an isolated governed corpus and run the production retrieval tool."""
    fixture_dir = Path(fixture_dir).resolve()
    work_dir = _require_d_drive(work_dir, "work-dir")
    work_dir.mkdir(parents=True, exist_ok=True)
    run_dir = work_dir / f"run-{uuid4().hex}"
    run_dir.mkdir()
    database_path = run_dir / "evaluation.db"
    chroma_path = run_dir / "chroma"

    corpus_manifest, manifest_sources = _load_corpus_manifests(fixture_dir)
    manifest = load_rag_manifest(fixture_dir)
    corpus = load_rag_corpus(fixture_dir)
    indexable = [
        item for item in corpus_manifest["fixtures"]
        if item.get("expected_indexable") is True
    ]
    excluded_fixture_ids = [
        item["id"] for item in corpus_manifest["fixtures"]
        if item.get("expected_indexable") is not True
    ]
    if "encrypted-policy" not in excluded_fixture_ids:
        raise ValueError("Encrypted fixture must be excluded")
    chunks_by_fixture: dict[str, list[dict[str, Any]]] = {}
    for item in corpus["chunks"]:
        chunks_by_fixture.setdefault(item["fixture_id"], []).append(item)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.core.retrieval_module as retrieval_module
    from app.core.agent import tools as agent_tools
    from app.core.embedding.hash_provider import HashEmbeddingProvider
    from app.core.retrieval.bm25_index import BM25IndexManager
    from app.core.retrieval.vector_store import VectorStore
    from app.models import Base, Document, DocumentChunk, DocumentFamily, Tenant

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    tenant = Tenant(slug="m25-eval", name="M2-5 Evaluation")
    session.add(tenant)
    session.flush()

    indexed_chunks: list[tuple[Any, str]] = []
    try:
        for fixture in indexable:
            filename = fixture["filename"]
            source_path = fixture_dir / filename
            source_bytes = source_path.read_bytes()
            curated_chunks = chunks_by_fixture[fixture["id"]]
            family = DocumentFamily(tenant_id=tenant.id, name=filename)
            session.add(family)
            session.flush()
            document = Document(
                tenant_id=tenant.id,
                family_id=family.id,
                filename=filename,
                file_type=source_path.suffix.lstrip(".").lower(),
                file_size=len(source_bytes),
                file_hash=hashlib.sha256(source_bytes).hexdigest(),
                chunk_count=len(curated_chunks),
                status="ready",
                audience_roles=["employee"],
                parser_name=corpus["source_parser_gate"],
                parser_version="m2-2-gate",
                page_count=max((item["page_end"] or 0 for item in curated_chunks), default=0),
                parse_quality_status="passed",
                parse_quality_details={
                    "source_parser_gate": corpus["source_parser_gate"],
                    "corpus_origin": corpus["origin"],
                },
                version=1,
                index_generation=1,
                review_status="approved",
                source_type="evaluation",
                chunker_version="curated-retrieval-corpus-v1",
                embedding_provider="hash",
                embedding_model="hash-64",
            )
            session.add(document)
            session.flush()
            family.current_document_id = document.id
            for index, curated_chunk in enumerate(curated_chunks, start=1):
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=curated_chunk["content"],
                    token_count=len(curated_chunk["content"]),
                    status="active",
                    page_start=curated_chunk["page_start"],
                    page_end=curated_chunk["page_end"],
                    section_path=curated_chunk["section_path"],
                    element_types=curated_chunk["element_types"],
                    source_element_indexes=[],
                    index_generation=1,
                    chunker_version="curated-retrieval-corpus-v1",
                    embedding_model="hash-64",
                )
                session.add(chunk)
                session.flush()
                chunk.embedding_id = chunk.id
                indexed_chunks.append((chunk, f"{filename}\n{curated_chunk['content']}"))
        session.commit()

        embedding = HashEmbeddingProvider(dim=64)
        vector_store = VectorStore(str(chroma_path))
        bm25 = BM25IndexManager()
    except Exception:
        session.close()
        engine.dispose()
        raise
    previous_services = (
        retrieval_module._vector_store,
        retrieval_module._bm25_manager,
        retrieval_module._embedding_provider,
    )
    previous_runtime = agent_tools._runtime.get()
    retrieval_module.set_vector_store(vector_store)
    retrieval_module.set_bm25_manager(bm25)
    retrieval_module.set_embedding_provider(embedding)
    try:
        results_by_query = asyncio.run(_index_and_search(
            session=session,
            tenant=tenant,
            indexed_chunks=indexed_chunks,
            manifest=manifest,
            embedding=embedding,
            vector_store=vector_store,
            bm25=bm25,
            search_tool=agent_tools.search_knowledge,
            set_runtime=agent_tools.set_runtime,
        ))
        metrics = evaluate_results(manifest, results_by_query)
    finally:
        bm25.remove_tenant(tenant.slug)
        agent_tools._runtime.set(previous_runtime)
        (
            retrieval_module._vector_store,
            retrieval_module._bm25_manager,
            retrieval_module._embedding_provider,
        ) = previous_services
        session.close()
        engine.dispose()

    manifest_hashes = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in manifest_sources.items()
    }
    manifest_hashes["combined"] = hashlib.sha256(
        b"\0".join(manifest_sources.values())
    ).hexdigest()
    return {
        "schema_version": 1,
        "benchmark": "smartcs-rag-retrieval",
        "run_context": {
            "environment_label": environment_label,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "manifest_sha256": manifest_hashes,
        },
        "corpus": {
            "origin": corpus["origin"],
            "source_parser_gate": corpus["source_parser_gate"],
            "fixture_count": len(corpus_manifest["fixtures"]),
            "indexed_fixture_count": len(indexable),
            "indexed_chunk_count": len(indexed_chunks),
            "excluded_fixture_ids": excluded_fixture_ids,
        },
        "query_count": len(manifest["queries"]),
        "retriever_profile": {
            "embedding": "hash-64",
            "vector": "chroma-cosine",
            "lexical": "bm25",
            "fusion": "rrf",
            "top_k": manifest["top_k"],
        },
        **metrics,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate SmartCS RAG retrieval")
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment-label", default="local-unspecified")
    args = parser.parse_args(argv)
    output = _require_d_drive(args.output, "output")
    report = run_evaluation(args.fixture_dir, args.work_dir, args.environment_label)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if report["summary"]["gate"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
