import pytest

from app.core.parsing.contracts import ParsedDocument, ParsedElement


def _document(*elements: ParsedElement) -> ParsedDocument:
    return ParsedDocument(
        parser_name="fixture",
        parser_version="1",
        page_count=3,
        elements=list(elements),
    )


def test_chunk_document_preserves_structure_lineage_and_context():
    from app.core.parsing.structured_chunker import chunk_document

    chunks = chunk_document(
        _document(
            ParsedElement(
                text="Annual Leave",
                element_type="heading",
                page_start=1,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Employees earn leave each calendar year.",
                element_type="paragraph",
                page_start=1,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Unused leave expires on 31 December.",
                element_type="paragraph",
                page_start=2,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Eligibility",
                element_type="heading",
                page_start=2,
                section_path=["Leave", "Eligibility"],
            ),
            ParsedElement(
                text="New employees receive leave after probation.",
                element_type="paragraph",
                page_start=3,
                section_path=["Leave", "Eligibility"],
            ),
        ),
        title="Employee Handbook",
    )

    assert [(chunk.content, chunk.page_start, chunk.page_end, chunk.section_path,
             chunk.element_types, chunk.source_element_indexes) for chunk in chunks] == [
        ("Annual Leave", 1, 1, ["Leave"], ["heading"], [0]),
        (
            "Employees earn leave each calendar year.\n\nUnused leave expires on 31 December.",
            1,
            2,
            ["Leave"],
            ["paragraph"],
            [1, 2],
        ),
        ("Eligibility", 2, 2, ["Leave", "Eligibility"], ["heading"], [3]),
        (
            "New employees receive leave after probation.",
            3,
            3,
            ["Leave", "Eligibility"],
            ["paragraph"],
            [4],
        ),
    ]
    assert chunks[1].contextualized_content == (
        "Employee Handbook\nLeave\n\n"
        "Employees earn leave each calendar year.\n\nUnused leave expires on 31 December."
    )
    assert chunks[1].content != chunks[1].contextualized_content
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_chunk_document_keeps_adjacent_headings_separate():
    from app.core.parsing.structured_chunker import chunk_document

    chunks = chunk_document(
        _document(
            ParsedElement(
                text="Annual Leave",
                element_type="heading",
                page_start=1,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Eligibility",
                element_type="heading",
                page_start=1,
                section_path=["Leave"],
            ),
        ),
        title="Employee Handbook",
    )

    assert [chunk.content for chunk in chunks] == ["Annual Leave", "Eligibility"]
    assert [chunk.source_element_indexes for chunk in chunks] == [[0], [1]]


def test_chunk_document_repeats_table_header_when_splitting(monkeypatch):
    from app.core.parsing import structured_chunker

    monkeypatch.setattr(structured_chunker, "MAX_TOKENS", 22)
    table = "\n".join(
        [
            "| Service | Days |",
            "| --- | --- |",
            "| 0-4 years | 5 |",
            "| 5-9 years | 10 |",
            "| 10+ years | 15 |",
        ]
    )

    chunks = structured_chunker.chunk_document(
        _document(
            ParsedElement(
                text=table,
                table_markdown=table,
                element_type="table",
                page_start=2,
                section_path=["Leave", "Entitlement"],
            )
        ),
        title="Employee Handbook",
    )

    assert len(chunks) == 3
    assert all(chunk.content.startswith("| Service | Days |\n| --- | --- |") for chunk in chunks)
    assert [chunk.source_element_indexes for chunk in chunks] == [[0], [0], [0]]
    assert [chunk.page_start for chunk in chunks] == [2, 2, 2]


def test_chunk_document_splits_a_single_oversized_table_row(monkeypatch):
    from app.core.parsing import structured_chunker

    monkeypatch.setattr(structured_chunker, "MAX_TOKENS", 24)
    header = "| Item | Detail |\n| --- | --- |"
    row = f"| Carryover | {'extended ' * 40}|"
    table = f"{header}\n{row}"

    chunks = structured_chunker.chunk_document(
        _document(
            ParsedElement(
                text=table,
                table_markdown=table,
                element_type="table",
                page_start=2,
                section_path=["Leave", "Carryover"],
            )
        ),
        title="Employee Handbook",
    )

    assert all(chunk.token_count <= structured_chunker.MAX_TOKENS for chunk in chunks)
    assert len(chunks) > 1
    assert all(chunk.content.startswith(header) for chunk in chunks)
    assert all(chunk.source_element_indexes == [0] for chunk in chunks)


def test_chunk_document_splits_oversized_elements_deterministically(monkeypatch):
    from app.core.parsing import structured_chunker

    monkeypatch.setattr(structured_chunker, "MAX_TOKENS", 8)
    document = _document(
        ParsedElement(
            text="one two three four five six seven eight nine ten eleven twelve",
            element_type="list",
            page_start=3,
            section_path=["Leave", "Notes"],
        )
    )

    first = structured_chunker.chunk_document(document, title="Employee Handbook")
    second = structured_chunker.chunk_document(document, title="Employee Handbook")

    assert [chunk.content for chunk in first] == [
        "one two three four five six seven eight",
        " nine ten eleven twelve",
    ]
    assert [chunk.content for chunk in second] == [chunk.content for chunk in first]
    assert all(chunk.token_count <= 8 for chunk in first)
    assert all(chunk.source_element_indexes == [0] for chunk in first)


@pytest.mark.parametrize("element_type", ["paragraph", "list"])
def test_chunk_document_round_trips_long_chinese_text(element_type):
    from app.core.parsing.structured_chunker import MAX_TOKENS, chunk_document

    element = ParsedElement(
        text=" 政策" * 1000 + "\n",
        element_type=element_type,
        page_start=1,
        section_path=["政策"],
    )
    chunks = chunk_document(
        _document(element),
        title="员工手册",
    )

    assert len(chunks) > 1
    assert "".join(chunk.content for chunk in chunks) == element.text
    assert all("\ufffd" not in chunk.content for chunk in chunks)
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)
    assert all(chunk.source_element_indexes == [0] for chunk in chunks)


def test_chunk_document_round_trips_an_oversized_chinese_table_row():
    from app.core.parsing.structured_chunker import MAX_TOKENS, chunk_document

    header = "| 项目 | 说明 |\n| --- | --- |"
    row = f"| 政策 | {'政策' * 1000} |"
    chunks = chunk_document(
        _document(
            ParsedElement(
                text=f"{header}\n{row}",
                table_markdown=f"{header}\n{row}",
                element_type="table",
                page_start=2,
                section_path=["政策", "明细"],
            )
        ),
        title="员工手册",
    )
    prefix = f"{header}\n"

    assert len(chunks) > 1
    assert all(chunk.content.startswith(prefix) for chunk in chunks)
    assert "".join(chunk.content.removeprefix(prefix) for chunk in chunks) == row
    assert all("\ufffd" not in chunk.content for chunk in chunks)
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)
    assert all(chunk.source_element_indexes == [0] for chunk in chunks)


def test_split_text_tokenizes_only_near_linear_total_characters(monkeypatch):
    from app.core.parsing import structured_chunker

    text = "政策" * 5000
    tokenized_lengths = []
    token_count = structured_chunker._token_count

    def counting_token_count(value):
        tokenized_lengths.append(len(value))
        return token_count(value)

    monkeypatch.setattr(structured_chunker, "_token_count", counting_token_count)
    chunks = structured_chunker._split_text(text, max_tokens=32)

    assert "".join(chunks) == text
    assert sum(tokenized_lengths) <= len(text) * 20
    assert max(tokenized_lengths) <= max(map(len, chunks)) * 4
