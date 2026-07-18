from pathlib import Path

import fitz
import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "documents"


def _pdf_bytes(draw_page):
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    draw_page(page)
    data = document.tobytes()
    document.close()
    return data


def _image_bytes():
    source = fitz.open()
    page = source.new_page(width=100, height=100)
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(0.2, 0.4, 0.8))
    image = page.get_pixmap(alpha=False).tobytes("png")
    source.close()
    return image


@pytest.mark.parametrize(
    ("filename", "route", "reason"),
    [
        ("clean_policy.pdf", "native", "clean_text"),
        ("repeated_headers.pdf", "native", "clean_text"),
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


def test_one_substantial_block_per_column_routes_advanced():
    from app.core.parsing.router import inspect_pdf

    def draw(page):
        page.insert_textbox(
            fitz.Rect(50, 150, 260, 360),
            "Left column policy text. " * 12,
            fontsize=11,
        )
        page.insert_textbox(
            fitz.Rect(340, 160, 550, 370),
            "Right column policy text. " * 12,
            fontsize=11,
        )

    decision = inspect_pdf(_pdf_bytes(draw))

    assert decision.route.value == "advanced"
    assert decision.reason.value == "multi_column_layout"


def test_full_width_heading_and_body_do_not_route_as_two_columns():
    from app.core.parsing.router import inspect_pdf

    def draw(page):
        page.insert_text((50, 70), "Employee handbook", fontsize=16)
        page.insert_textbox(
            fitz.Rect(50, 140, 550, 260),
            "Full width policy text. " * 25,
            fontsize=11,
        )

    decision = inspect_pdf(_pdf_bytes(draw))

    assert decision.route.value == "native"


def test_large_image_region_with_machine_text_routes_advanced():
    from app.core.parsing.router import inspect_pdf

    def draw(page):
        page.insert_textbox(
            fitz.Rect(50, 40, 550, 130),
            "Machine readable policy text. " * 12,
            fontsize=11,
        )
        page.insert_image(fitz.Rect(50, 180, 550, 700), stream=_image_bytes())

    decision = inspect_pdf(_pdf_bytes(draw))

    assert decision.route.value == "advanced"
    assert decision.reason.value == "large_image_region"


def test_small_logo_on_clean_text_page_stays_native():
    from app.core.parsing.router import inspect_pdf

    def draw(page):
        page.insert_image(fitz.Rect(20, 20, 50, 50), stream=_image_bytes())
        page.insert_textbox(
            fitz.Rect(50, 100, 550, 300),
            "Clean machine readable policy text. " * 25,
            fontsize=11,
        )

    decision = inspect_pdf(_pdf_bytes(draw))

    assert decision.route.value == "native"


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
