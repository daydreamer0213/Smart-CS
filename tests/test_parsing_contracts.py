import pytest
from pydantic import ValidationError


def test_parsed_document_preserves_source_structure():
    from app.core.parsing.contracts import ParsedDocument, ParsedElement

    document = ParsedDocument(
        parser_name="fixture",
        parser_version="1",
        page_count=2,
        elements=[
            ParsedElement(
                text="Annual leave policy",
                element_type="heading",
                page_start=1,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Ten years of service grants ten days.",
                element_type="paragraph",
                page_start=2,
                section_path=["Leave", "Entitlement"],
            ),
        ],
    )

    assert document.plain_text == (
        "Annual leave policy\n\nTen years of service grants ten days."
    )
    assert document.elements[0].page_end == 1
    assert document.elements[1].section_path == ["Leave", "Entitlement"]


def test_parsed_element_rejects_invalid_page_span():
    from app.core.parsing.contracts import ParsedElement

    with pytest.raises(ValidationError, match="page_end"):
        ParsedElement(
            text="policy",
            element_type="paragraph",
            page_start=3,
            page_end=2,
        )


def test_parsed_document_rejects_element_outside_page_count():
    from app.core.parsing.contracts import ParsedDocument, ParsedElement

    with pytest.raises(ValidationError, match="page_count"):
        ParsedDocument(
            parser_name="fixture",
            parser_version="1",
            page_count=1,
            elements=[
                ParsedElement(
                    text="page two",
                    element_type="paragraph",
                    page_start=2,
                )
            ],
        )


def test_knowledge_chunk_keeps_display_and_embedding_content_separate():
    from app.core.parsing.contracts import KnowledgeChunk

    chunk = KnowledgeChunk(
        content="Ten years grants ten days.",
        contextualized_content="Leave > Entitlement\nTen years grants ten days.",
        page_start=2,
        page_end=2,
        section_path=["Leave", "Entitlement"],
        element_types=["table"],
        source_element_indexes=[3],
        token_count=12,
    )

    assert chunk.content != chunk.contextualized_content
    assert chunk.source_element_indexes == [3]
