"""Optional Docling adapter for PDF routes that require OCR or layout analysis."""

import importlib
import io
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.config import settings
from app.core.parsing.contracts import ParsedDocument, ParsedElement
from app.core.parsing.quality import evaluate_parse_quality, parser_failure_quality

BBox = tuple[float, float, float, float]
NativeTable = tuple[int, BBox, str]
MIN_TABLE_BBOX_IOU = 0.7
MIN_NON_TABLE_BBOX_COVERAGE = 0.8


def parse_docling_pdf(
    filename: str, data: bytes, *, expected_page_count: int
) -> ParsedDocument:
    """Parse a PDF with Docling and convert all runtime failures into quality data."""
    try:
        result = _convert_docling_pdf(filename, data)
        return map_docling_result(
            result,
            expected_page_count=expected_page_count,
            parser_version=_docling_version(),
            table_fallbacks=_extract_native_table_markdowns(data),
        )
    except Exception as error:
        quality, _ = parser_failure_quality(error)
        return ParsedDocument(
            parser_name="docling",
            parser_version=_docling_version(),
            page_count=expected_page_count,
            elements=[],
            quality=quality,
        )


def map_docling_result(
    result,
    *,
    expected_page_count: int,
    parser_version: str,
    table_fallbacks: list[NativeTable] | None = None,
) -> ParsedDocument:
    """Map Docling's ordered items to the stable SmartCS parser contract."""
    elements: list[ParsedElement] = []
    section_path: list[str] = []
    warnings = []
    remaining_table_fallbacks = list(table_fallbacks or ())
    native_table_regions: list[tuple[int, BBox]] = []
    non_table_regions: list[tuple[int, BBox | None]] = []
    for item, _ in result.document.iterate_items(with_groups=False):
        label = _label_value(item)
        text, table_markdown = _item_text(item, result.document, label)
        page_start, page_end = _page_span(item)
        metadata = {"ocr": True}
        if label != "table":
            non_table_regions.extend(_item_page_bboxes(item, result))
        if label == "table":
            fallback_index = _matching_native_table_index(
                item, result, remaining_table_fallbacks
            )
            if fallback_index is not None:
                native_page, native_bbox, native_markdown = remaining_table_fallbacks.pop(
                    fallback_index
                )
                if not text:
                    text = native_markdown
                    table_markdown = native_markdown
                    metadata = {"ocr": False}
                    native_table_regions.append((native_page, native_bbox))
            elif not text:
                warnings.append("advanced_parser_incomplete")
        if not text:
            continue
        element_type = _element_type(label)
        if element_type == "heading":
            level = max(1, int(getattr(item, "level", 1)))
            section_path = section_path[: level - 1] + [text]
        elements.append(
            ParsedElement(
                text=text,
                element_type=element_type,
                page_start=page_start,
                page_end=page_end,
                section_path=section_path.copy() if element_type != "title" else [],
                table_markdown=table_markdown,
                metadata=metadata,
            )
        )

    if remaining_table_fallbacks:
        warnings.append("advanced_parser_incomplete")
    if _has_native_table_content_overlap(native_table_regions, non_table_regions):
        warnings.append("advanced_parser_incomplete")

    document = ParsedDocument(
        parser_name="docling",
        parser_version=parser_version,
        page_count=expected_page_count,
        elements=elements,
    )
    result_page_count = len(getattr(result, "pages", ()))
    status = _status_value(getattr(result, "status", "failure"))
    if (
        status != "success"
        or result_page_count != expected_page_count
        or result.has_timeout_errors()
    ):
        warnings.append("advanced_parser_incomplete")
    document.quality = evaluate_parse_quality(document, warnings=warnings)
    return document


def _convert_docling_pdf(filename: str, data: bytes):
    _validate_runtime_paths()
    converter_module = importlib.import_module("docling.document_converter")
    model_module = importlib.import_module("docling.datamodel.base_models")
    pipeline_module = importlib.import_module("docling.datamodel.pipeline_options")
    stream_module = importlib.import_module("docling_core.types.io")
    pipeline_options = pipeline_module.PdfPipelineOptions(
        artifacts_path=settings.docling_artifacts_path,
        do_ocr=True,
        do_table_structure=True,
        document_timeout=float(settings.agent_timeout_seconds),
        accelerator_options=pipeline_module.AcceleratorOptions(
            num_threads=settings.docling_num_threads,
            device=pipeline_module.AcceleratorDevice.CPU,
        ),
        ocr_options=pipeline_module.TesseractCliOcrOptions(
            lang=["chi_sim", "eng"],
            force_full_page_ocr=True,
            tesseract_cmd=settings.tesseract_cmd,
            path=settings.tessdata_prefix,
            psm=6,
        ),
    )
    converter = converter_module.DocumentConverter(
        format_options={
            model_module.InputFormat.PDF: converter_module.PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )
    return converter.convert(
        stream_module.DocumentStream(name=filename, stream=io.BytesIO(data)),
        raises_on_error=False,
    )


def _validate_runtime_paths() -> None:
    required = (
        settings.docling_artifacts_path,
        settings.tesseract_cmd,
        settings.tessdata_prefix,
        str(Path(settings.tessdata_prefix) / "chi_sim.traineddata"),
        str(Path(settings.tessdata_prefix) / "eng.traineddata"),
    )
    configured_temp = Path(settings.parser_temp_dir).resolve()
    runtime_temp = Path(tempfile.gettempdir()).resolve()
    paths_exist = all(Path(path).exists() for path in required)
    if not paths_exist or not runtime_temp.is_relative_to(configured_temp):
        raise RuntimeError("Docling runtime is unavailable")


def _extract_native_table_markdowns(data: bytes) -> list[NativeTable]:
    """Use the existing PDF backend only to recover reliable digital tables."""
    import fitz

    tables: list[NativeTable] = []
    document = fitz.open(stream=data, filetype="pdf")
    try:
        for page_no, page in enumerate(document, start=1):
            for table in page.find_tables().tables:
                markdown = table.to_markdown().strip()
                if markdown:
                    tables.append(
                        (page_no, tuple(float(value) for value in table.bbox), markdown)
                    )
    finally:
        document.close()
    return tables


def _matching_native_table_index(
    item, result, native_tables: list[NativeTable]
) -> int | None:
    best_index = None
    best_overlap = 0.0
    for page_no, item_bbox in _item_top_left_bboxes(item, result):
        for index, (native_page_no, native_bbox, _) in enumerate(native_tables):
            if native_page_no != page_no:
                continue
            overlap = _bbox_overlap_ratio(item_bbox, native_bbox)
            if overlap > best_overlap:
                best_index = index
                best_overlap = overlap
    return best_index if best_overlap >= MIN_TABLE_BBOX_IOU else None


def _item_top_left_bboxes(item, result):
    return [
        (page_no, bbox)
        for page_no, bbox in _item_page_bboxes(item, result)
        if bbox is not None
    ]


def _item_page_bboxes(item, result) -> list[tuple[int, BBox | None]]:
    bboxes: list[tuple[int, BBox | None]] = []
    pages = getattr(result, "pages", ())
    for provenance in getattr(item, "prov", ()):
        page_no = getattr(provenance, "page_no", None)
        bbox = getattr(provenance, "bbox", None)
        if not isinstance(page_no, int) or page_no < 1:
            continue
        coordinates = None
        if bbox is not None and page_no <= len(pages):
            try:
                bbox = bbox.to_top_left_origin(
                    page_height=pages[page_no - 1].size.height
                )
                candidate = tuple(
                    float(getattr(bbox, name)) for name in ("l", "t", "r", "b")
                )
                if candidate[0] < candidate[2] and candidate[1] < candidate[3]:
                    coordinates = candidate
            except (AttributeError, TypeError, ValueError):
                pass
        bboxes.append((page_no, coordinates))
    return bboxes


def _bbox_overlap_ratio(first, second) -> float:
    first_width = first[2] - first[0]
    first_height = first[3] - first[1]
    second_width = second[2] - second[0]
    second_height = second[3] - second[1]
    if min(first_width, first_height, second_width, second_height) <= 0:
        return 0.0

    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    intersection = width * height
    union = first_width * first_height + second_width * second_height - intersection
    return intersection / union


def _has_native_table_content_overlap(
    native_tables: list[tuple[int, BBox]],
    non_tables: list[tuple[int, BBox | None]],
) -> bool:
    for table_page, table_bbox in native_tables:
        for item_page, item_bbox in non_tables:
            if item_page != table_page:
                continue
            if item_bbox is None:
                return True
            if (
                _bbox_smaller_coverage(table_bbox, item_bbox)
                >= MIN_NON_TABLE_BBOX_COVERAGE
            ):
                return True
    return False


def _bbox_smaller_coverage(first: BBox, second: BBox) -> float:
    first_width = first[2] - first[0]
    first_height = first[3] - first[1]
    second_width = second[2] - second[0]
    second_height = second[3] - second[1]
    if min(first_width, first_height, second_width, second_height) <= 0:
        return 0.0

    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height / min(
        first_width * first_height, second_width * second_height
    )


def _docling_version() -> str:
    try:
        return version("docling-slim")
    except PackageNotFoundError:
        return "unavailable"


def _label_value(item) -> str:
    label = getattr(item, "label", "text")
    return str(getattr(label, "value", label))


def _status_value(status) -> str:
    return str(getattr(status, "value", status))


def _item_text(item, document, label: str) -> tuple[str, str | None]:
    if label == "table":
        text = str(item.export_to_markdown(document) or "").strip()
        return text, text or None
    return str(getattr(item, "text", "")).strip(), None


def _element_type(label: str):
    return {
        "title": "title",
        "section_header": "heading",
        "list_item": "list",
        "table": "table",
        "picture": "image",
    }.get(label, "paragraph")


def _page_span(item) -> tuple[int | None, int | None]:
    pages = [
        provenance.page_no
        for provenance in getattr(item, "prov", ())
        if isinstance(getattr(provenance, "page_no", None), int)
        and provenance.page_no >= 1
    ]
    return (min(pages), max(pages)) if pages else (None, None)
