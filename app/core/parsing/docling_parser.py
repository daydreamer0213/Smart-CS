"""Optional Docling adapter for PDF routes that require OCR or layout analysis."""

import importlib
import io
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.config import settings
from app.core.parsing.contracts import ParsedDocument, ParsedElement
from app.core.parsing.quality import evaluate_parse_quality, parser_failure_quality

NativeTable = tuple[int, tuple[float, float, float, float], str]
MIN_TABLE_BBOX_IOU = 0.7


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
    for item, _ in result.document.iterate_items(with_groups=False):
        label = _label_value(item)
        text, table_markdown = _item_text(item, result.document, label)
        page_start, page_end = _page_span(item)
        metadata = {"ocr": True}
        if label == "table":
            fallback_index = _matching_native_table_index(
                item, result, remaining_table_fallbacks
            )
            if fallback_index is not None:
                _, _, native_markdown = remaining_table_fallbacks.pop(fallback_index)
                if not text:
                    text = native_markdown
                    table_markdown = native_markdown
                    metadata = {"ocr": False}
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
    if _has_repeated_native_table_data(elements):
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
    bboxes = []
    pages = getattr(result, "pages", ())
    for provenance in getattr(item, "prov", ()):
        page_no = getattr(provenance, "page_no", None)
        bbox = getattr(provenance, "bbox", None)
        if (
            not isinstance(page_no, int)
            or not 1 <= page_no <= len(pages)
            or bbox is None
        ):
            continue
        try:
            bbox = bbox.to_top_left_origin(page_height=pages[page_no - 1].size.height)
            coordinates = tuple(
                float(getattr(bbox, name)) for name in ("l", "t", "r", "b")
            )
        except (AttributeError, TypeError, ValueError):
            continue
        if coordinates[0] < coordinates[2] and coordinates[1] < coordinates[3]:
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


def _has_repeated_native_table_data(elements: list[ParsedElement]) -> bool:
    non_tables = [element for element in elements if element.element_type != "table"]
    for table in elements:
        if (
            table.element_type != "table"
            or table.metadata.get("ocr") is not False
            or not table.table_markdown
        ):
            continue
        page_text = "".join(
            _normalize_table_cell(element.text)
            for element in non_tables
            if _page_spans_overlap(table, element)
        )
        if any(
            all(cell in page_text for cell in row)
            for row in _markdown_data_rows(table.table_markdown)
        ):
            return True
    return False


def _markdown_data_rows(markdown: str) -> list[list[str]]:
    rows = [_markdown_row_cells(line) for line in markdown.splitlines()]
    separator_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row and all(_is_markdown_separator(cell) for cell in row)
        ),
        None,
    )
    if separator_index is None:
        return []

    data_rows = []
    for row in rows[separator_index + 1 :]:
        cells = list(
            dict.fromkeys(
                cell
                for cell in map(_normalize_table_cell, row)
                if any(character.isalnum() for character in cell)
            )
        )
        if len(cells) >= 2:
            data_rows.append(cells)
    return data_rows


def _markdown_row_cells(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        return []
    return [cell.strip() for cell in line[1:-1].split("|")]


def _is_markdown_separator(cell: str) -> bool:
    cell = cell.strip()
    return len(cell) >= 3 and "-" in cell and set(cell) <= {"-", ":"}


def _normalize_table_cell(text: str) -> str:
    return "".join(text.replace(r"\|", "|").split()).strip("`*_")


def _page_spans_overlap(first: ParsedElement, second: ParsedElement) -> bool:
    if (
        first.page_start is None
        or first.page_end is None
        or second.page_start is None
        or second.page_end is None
    ):
        return False
    return first.page_start <= second.page_end and second.page_start <= first.page_end


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
