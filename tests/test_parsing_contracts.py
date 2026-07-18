import pytest
from pydantic import ValidationError


def _element(**page_span):
    from app.core.parsing.contracts import ParsedElement

    return ParsedElement(text="policy", element_type="paragraph", **page_span)


def _chunk(**page_span):
    from app.core.parsing.contracts import KnowledgeChunk

    return KnowledgeChunk(
        content="policy",
        contextualized_content="policy",
        token_count=1,
        **page_span,
    )


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


@pytest.mark.parametrize("factory", [_element, _chunk])
def test_page_span_defaults_end_to_start(factory):
    item = factory(page_start=3)

    assert item.page_end == 3


@pytest.mark.parametrize("factory", [_element, _chunk])
def test_page_span_rejects_end_without_start(factory):
    with pytest.raises(ValidationError, match="page_start"):
        factory(page_end=3)


@pytest.mark.parametrize("factory", [_element, _chunk])
def test_page_span_rejects_reversed_range(factory):
    with pytest.raises(ValidationError, match="page_end"):
        factory(page_start=3, page_end=2)


def test_knowledge_chunk_rejects_negative_source_element_index():
    from app.core.parsing.contracts import KnowledgeChunk

    with pytest.raises(ValidationError, match="source_element_indexes"):
        KnowledgeChunk(
            content="policy",
            contextualized_content="policy",
            source_element_indexes=[-1],
            token_count=1,
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
