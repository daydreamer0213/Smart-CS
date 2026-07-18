"""Deterministic parser routing without an optional advanced-parser dependency."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core.parsing.contracts import ParsedDocument
from app.core.parsing.native_parser import parse_native_file


class PdfRoute(str, Enum):
    NATIVE = "native"
    ADVANCED = "advanced"
    REJECTED = "rejected"


class PdfRouteReason(str, Enum):
    CLEAN_TEXT = "clean_text"
    INVALID_PDF = "invalid_pdf"
    ENCRYPTED = "encrypted"
    ZERO_PAGES = "zero_pages"
    SPARSE_TEXT_PAGE = "sparse_text_page"
    TABLE_LAYOUT = "table_layout"
    MULTI_COLUMN_LAYOUT = "multi_column_layout"
    LARGE_IMAGE_REGION = "large_image_region"


@dataclass(frozen=True)
class PdfRouteDecision:
    route: PdfRoute
    reason: PdfRouteReason
    page_count: int


class AdvancedParserRequired(RuntimeError):
    def __init__(self, decision: PdfRouteDecision):
        self.decision = decision
        super().__init__(f"advanced parser required: {decision.reason.value}")


class PdfRejectedError(ValueError):
    def __init__(self, decision: PdfRouteDecision):
        self.decision = decision
        super().__init__(f"PDF rejected: {decision.reason.value}")


def _has_two_columns(page) -> bool:
    width = page.rect.width
    blocks = [
        block
        for block in page.get_text("blocks")
        if len("".join(block[4].split())) >= 12
    ]
    for left in blocks:
        for right in blocks:
            if left is right:
                continue
            horizontally_separated = (
                left[2] <= width * 0.5
                and right[0] >= width * 0.5
                and right[0] - left[2] >= width * 0.05
            )
            vertically_overlapping = max(left[1], right[1]) < min(left[3], right[3])
            if horizontally_separated and vertically_overlapping:
                return True
    return False


def _has_large_image_region(page) -> bool:
    page_area = page.rect.get_area()
    image_area = sum(
        rectangle.get_area()
        for image in page.get_images(full=True)
        for rectangle in page.get_image_rects(image[0])
    )
    return page_area > 0 and image_area / page_area >= 0.15


def inspect_pdf(data: bytes) -> PdfRouteDecision:
    import fitz

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return PdfRouteDecision(PdfRoute.REJECTED, PdfRouteReason.INVALID_PDF, 0)
    try:
        page_count = document.page_count
        if document.needs_pass:
            return PdfRouteDecision(PdfRoute.REJECTED, PdfRouteReason.ENCRYPTED, page_count)
        if page_count == 0:
            return PdfRouteDecision(PdfRoute.REJECTED, PdfRouteReason.ZERO_PAGES, page_count)
        for page in document:
            if len("".join(page.get_text().split())) < 20:
                return PdfRouteDecision(PdfRoute.ADVANCED, PdfRouteReason.SPARSE_TEXT_PAGE, page_count)
            if page.find_tables().tables:
                return PdfRouteDecision(PdfRoute.ADVANCED, PdfRouteReason.TABLE_LAYOUT, page_count)
            if _has_two_columns(page):
                return PdfRouteDecision(PdfRoute.ADVANCED, PdfRouteReason.MULTI_COLUMN_LAYOUT, page_count)
            if _has_large_image_region(page):
                return PdfRouteDecision(PdfRoute.ADVANCED, PdfRouteReason.LARGE_IMAGE_REGION, page_count)
        return PdfRouteDecision(PdfRoute.NATIVE, PdfRouteReason.CLEAN_TEXT, page_count)
    except Exception:
        return PdfRouteDecision(PdfRoute.REJECTED, PdfRouteReason.INVALID_PDF, 0)
    finally:
        document.close()


def parse_structured_file(filename: str, data: bytes) -> ParsedDocument:
    if Path(filename).suffix.lower() != ".pdf":
        return parse_native_file(filename, data)
    decision = inspect_pdf(data)
    if decision.route is PdfRoute.ADVANCED:
        raise AdvancedParserRequired(decision)
    if decision.route is PdfRoute.REJECTED:
        raise PdfRejectedError(decision)
    document = parse_native_file(filename, data)
    document.metadata = {"route": decision.route.value, "route_reason": decision.reason.value}
    return document
