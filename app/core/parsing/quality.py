from collections.abc import Iterable
from math import isfinite
from typing import cast

from app.core.parsing.contracts import ParseQuality, ParseWarning, ParsedDocument

OCR_CONFIDENCE_THRESHOLD = 0.80
SAFE_PARSE_ERROR_MESSAGE = "Document parsing failed."

_ALLOWED_WARNINGS = frozenset(ParseWarning.__args__)


def evaluate_parse_quality(
    document: ParsedDocument,
    *,
    elapsed_ms: float = 0.0,
    warnings: Iterable[ParseWarning] = (),
) -> ParseQuality:
    """Assess parser output without changing the parsed document."""
    if not _is_finite_number(elapsed_ms) or elapsed_ms < 0:
        raise ValueError("elapsed_ms must be a finite non-negative number")

    normalized_warnings = _normalize_warnings(warnings)
    covered_pages = _covered_pages(document)
    metrics: dict[str, int | float] = {
        "page_count": document.page_count,
        "usable_text_pages": len(covered_pages),
        "empty_pages": document.page_count - len(covered_pages),
        "character_count": sum(len(element.text) for element in document.elements),
        "table_count": sum(
            element.element_type == "table" for element in document.elements
        ),
        "heading_count": sum(
            element.element_type in {"title", "heading"}
            for element in document.elements
        ),
        "ocr_pages": len(_ocr_pages(document)),
        "elapsed_ms": elapsed_ms,
    }

    if "ocr_confidence" in document.metadata:
        ocr_confidence = document.metadata["ocr_confidence"]
        if _is_valid_ocr_confidence(ocr_confidence):
            metrics["ocr_confidence"] = ocr_confidence
            if ocr_confidence < OCR_CONFIDENCE_THRESHOLD:
                normalized_warnings = _append_warning(
                    normalized_warnings, "low_ocr_confidence"
                )
        else:
            normalized_warnings = _append_warning(
                normalized_warnings, "invalid_ocr_confidence"
            )

    if document.page_count and len(covered_pages) != document.page_count:
        normalized_warnings = _append_warning(
            normalized_warnings, "missing_page_coverage"
        )

    if (
        "parser_exception" in normalized_warnings
        or not document.elements
        or metrics["character_count"] == 0
    ):
        status = "failed"
    elif normalized_warnings:
        status = "review_required"
    else:
        status = "passed"

    return ParseQuality(status=status, metrics=metrics, warnings=normalized_warnings)


def parser_failure_quality(_error: Exception) -> tuple[ParseQuality, str]:
    """Return a fixed failure result without exposing parser error details."""
    return (
        ParseQuality(status="failed", warnings=["parser_exception"]),
        SAFE_PARSE_ERROR_MESSAGE,
    )


def _covered_pages(document: ParsedDocument) -> set[int]:
    if not document.page_count:
        return set()
    return {
        page
        for element in document.elements
        if element.page_start is not None and element.page_end is not None
        for page in range(element.page_start, element.page_end + 1)
    }


def _ocr_pages(document: ParsedDocument) -> set[int]:
    if not document.page_count:
        return set()
    return {
        page
        for element in document.elements
        if element.metadata.get("ocr") is True
        and element.page_start is not None
        and element.page_end is not None
        for page in range(element.page_start, element.page_end + 1)
    }


def _normalize_warnings(warnings: Iterable[ParseWarning]) -> list[ParseWarning]:
    normalized: list[ParseWarning] = []
    for warning in warnings:
        if warning not in _ALLOWED_WARNINGS:
            raise ValueError("unsupported parse warning")
        normalized = _append_warning(normalized, cast(ParseWarning, warning))
    return normalized


def _append_warning(
    warnings: list[ParseWarning], warning: ParseWarning
) -> list[ParseWarning]:
    return warnings if warning in warnings else [*warnings, warning]


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _is_valid_ocr_confidence(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= value <= 1.0
