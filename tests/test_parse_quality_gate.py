import math

import pytest


def _document(*, page_count=2, elements=None, metadata=None):
    from app.core.parsing.contracts import ParsedDocument, ParsedElement

    return ParsedDocument(
        parser_name="fixture",
        parser_version="1",
        page_count=page_count,
        elements=elements
        if elements is not None
        else [
            ParsedElement(text="One", element_type="heading", page_start=1),
            ParsedElement(text="Two", element_type="paragraph", page_start=2),
        ],
        metadata=metadata or {},
    )


def test_quality_gate_reports_structural_metrics_for_paged_document():
    from app.core.parsing.contracts import ParsedElement
    from app.core.parsing.quality import evaluate_parse_quality

    document = _document(
        elements=[
            ParsedElement(text="Title", element_type="heading", page_start=1),
            ParsedElement(
                text="| A | B |", element_type="table", page_start=1, page_end=2,
                metadata={"ocr": True},
            ),
        ]
    )

    quality = evaluate_parse_quality(document, elapsed_ms=12.5)

    assert quality.status == "passed"
    assert quality.metrics == {
        "page_count": 2,
        "usable_text_pages": 2,
        "empty_pages": 0,
        "character_count": 14,
        "table_count": 1,
        "heading_count": 1,
        "ocr_pages": 2,
        "elapsed_ms": 12.5,
    }


def test_quality_gate_marks_missing_paged_coverage_for_review():
    from app.core.parsing.contracts import ParsedElement
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(
        _document(
            page_count=3,
            elements=[ParsedElement(text="One", element_type="paragraph", page_start=1)]
        )
    )

    assert quality.status == "review_required"
    assert quality.warnings == ["missing_page_coverage"]
    assert quality.metrics["empty_pages"] == 2


def test_quality_gate_does_not_treat_non_paged_documents_as_missing_pages():
    from app.core.parsing.contracts import ParsedElement
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(
        _document(
            page_count=0,
            elements=[ParsedElement(text="Policy", element_type="paragraph")],
        )
    )

    assert quality.status == "passed"
    assert quality.metrics["empty_pages"] == 0
    assert quality.metrics["usable_text_pages"] == 0


@pytest.mark.parametrize("warnings", [["encrypted_input"], ["indexing_blocked"]])
def test_quality_gate_requires_review_for_blocking_controlled_warning(warnings):
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(_document(), warnings=warnings)

    assert quality.status == "review_required"
    assert quality.warnings == warnings


def test_quality_gate_rejects_uncontrolled_warning_strings():
    from app.core.parsing.quality import evaluate_parse_quality

    with pytest.raises(ValueError, match="unsupported parse warning"):
        evaluate_parse_quality(_document(), warnings=[r"C:\\Users\\Ada\\secret-token"])


def test_quality_gate_low_ocr_confidence_requires_review_without_fabricating_metric():
    from app.core.parsing.quality import OCR_CONFIDENCE_THRESHOLD, evaluate_parse_quality

    quality = evaluate_parse_quality(
        _document(metadata={"ocr_confidence": OCR_CONFIDENCE_THRESHOLD - 0.01})
    )
    no_ocr_metric = evaluate_parse_quality(_document())

    assert quality.status == "review_required"
    assert quality.warnings == ["low_ocr_confidence"]
    assert quality.metrics["ocr_confidence"] == OCR_CONFIDENCE_THRESHOLD - 0.01
    assert "ocr_confidence" not in no_ocr_metric.metrics


def test_quality_gate_failed_status_takes_precedence_over_blocking_warnings():
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(
        _document(page_count=0, elements=[]), warnings=["encrypted_input"]
    )

    assert quality.status == "failed"


def test_quality_gate_parser_exception_warning_takes_failed_precedence():
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(_document(), warnings=["parser_exception"])

    assert quality.status == "failed"


@pytest.mark.parametrize("elapsed_ms", [-0.01, math.nan, math.inf, -math.inf])
def test_quality_gate_rejects_invalid_elapsed_time_without_echoing_value(elapsed_ms):
    from app.core.parsing.quality import evaluate_parse_quality

    with pytest.raises(ValueError) as error:
        evaluate_parse_quality(_document(), elapsed_ms=elapsed_ms)

    assert str(error.value) == "elapsed_ms must be a finite non-negative number"


@pytest.mark.parametrize(
    "ocr_confidence",
    [-0.01, 1.01, math.nan, math.inf, -math.inf, True, "0.8"],
)
def test_quality_gate_requires_review_for_invalid_ocr_confidence(ocr_confidence):
    from app.core.parsing.quality import evaluate_parse_quality

    quality = evaluate_parse_quality(
        _document(metadata={"ocr_confidence": ocr_confidence})
    )

    assert quality.status == "review_required"
    assert quality.warnings == ["invalid_ocr_confidence"]
    assert "ocr_confidence" not in quality.metrics


def test_parser_failure_quality_hides_exception_details():
    from app.core.parsing.quality import SAFE_PARSE_ERROR_MESSAGE, parser_failure_quality

    quality, public_message = parser_failure_quality(
        RuntimeError(r"C:\\Users\\Ada\\secret-token")
    )

    assert quality.status == "failed"
    assert quality.warnings == ["parser_exception"]
    assert public_message == SAFE_PARSE_ERROR_MESSAGE
    assert "Ada" not in public_message
    assert "secret-token" not in public_message
