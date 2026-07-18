from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "documents"


@pytest.mark.parametrize(
    ("filename", "route", "reason"),
    [
        ("clean_policy.pdf", "native", "clean_text"),
        ("scanned_policy.pdf", "advanced", "sparse_text_page"),
        ("mixed_policy.pdf", "advanced", "sparse_text_page"),
        ("leave_table.pdf", "advanced", "table_layout"),
        ("two_column_policy.pdf", "advanced", "multi_column_layout"),
        ("encrypted_policy.pdf", "rejected", "encrypted"),
    ],
)
def test_pdf_route_decisions_are_controlled_fixture_signals(filename, route, reason):
    from app.core.parsing.router import inspect_pdf

    decision = inspect_pdf((FIXTURES / filename).read_bytes())

    assert decision.route.value == route
    assert decision.reason.value == reason
    assert isinstance(decision.page_count, int)


def test_structured_clean_pdf_preserves_each_page_and_route_metadata():
    from app.core.parsing.router import parse_structured_file

    document = parse_structured_file(
        "clean_policy.pdf", (FIXTURES / "clean_policy.pdf").read_bytes()
    )

    assert document.page_count == 2
    assert [(element.page_start, element.page_end) for element in document.elements] == [
        (1, 1), (2, 2),
    ]
    assert document.metadata == {"route": "native", "route_reason": "clean_text"}


@pytest.mark.parametrize("filename", ["scanned_policy.pdf", "mixed_policy.pdf", "leave_table.pdf", "two_column_policy.pdf"])
def test_structured_advanced_pdf_requires_adapter_without_plain_text_fallback(filename):
    from app.core.parsing.router import AdvancedParserRequired, parse_structured_file

    with pytest.raises(AdvancedParserRequired, match="advanced parser required") as error:
        parse_structured_file(filename, (FIXTURES / filename).read_bytes())

    assert error.value.decision.reason.value in {
        "sparse_text_page", "table_layout", "multi_column_layout",
    }


def test_structured_encrypted_pdf_is_rejected_without_raw_parser_error():
    from app.core.parsing.router import PdfRejectedError, parse_structured_file

    with pytest.raises(PdfRejectedError, match="PDF rejected: encrypted"):
        parse_structured_file(
            "encrypted_policy.pdf", (FIXTURES / "encrypted_policy.pdf").read_bytes()
        )


def test_zero_page_pdf_is_rejected_with_a_controlled_reason():
    from app.core.parsing.router import PdfRejectedError, parse_structured_file

    empty_pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )

    with pytest.raises(PdfRejectedError, match="PDF rejected: zero_pages"):
        parse_structured_file("empty.pdf", empty_pdf)


def test_invalid_pdf_is_rejected_without_pymupdf_error_text():
    from app.core.parsing.router import PdfRejectedError, parse_structured_file

    with pytest.raises(PdfRejectedError, match="PDF rejected: invalid_pdf"):
        parse_structured_file("broken.pdf", b"not a PDF")
