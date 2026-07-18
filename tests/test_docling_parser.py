from types import SimpleNamespace

import pytest


class _BBox:
    def __init__(self, left, top, right, bottom):
        self.l = left
        self.t = top
        self.r = right
        self.b = bottom

    def to_top_left_origin(self, *, page_height):
        assert page_height == 842
        return self


class _Item:
    def __init__(self, label, text, pages, *, level=1, markdown=None, bboxes=None):
        self.label = label
        self.text = text
        bboxes = bboxes or [None] * len(pages)
        self.prov = [
            SimpleNamespace(page_no=page, bbox=bbox)
            for page, bbox in zip(pages, bboxes, strict=True)
        ]
        self.level = level
        self._markdown = markdown

    def export_to_markdown(self, _document):
        return self._markdown


class _Document:
    def __init__(self, items):
        self._items = items

    def iterate_items(self, with_groups=False):
        assert with_groups is False
        return ((item, 0) for item in self._items)


def _result(*, status="success", items=(), page_count=2, timeout=False):
    return SimpleNamespace(
        status=status,
        pages=[
            SimpleNamespace(size=SimpleNamespace(height=842))
            for _ in range(page_count)
        ],
        document=_Document(items),
        has_timeout_errors=lambda: timeout,
    )


def test_docling_result_maps_items_in_reading_order_with_safe_metadata():
    from app.core.parsing.docling_parser import map_docling_result

    result = _result(
        items=[
            _Item("title", "Employee handbook", [1]),
            _Item("section_header", "Leave", [1], level=1),
            _Item("text", "Ten days after ten years.", [1]),
            _Item("list_item", "Apply three days ahead.", [1]),
            _Item("table", "", [2], markdown="| Years | Days |\n| --- | --- |\n| 10 | 10 |"),
            _Item("picture", "Policy diagram", [2]),
        ]
    )

    document = map_docling_result(result, expected_page_count=2, parser_version="2.113.0")

    assert [(item.element_type, item.text) for item in document.elements] == [
        ("title", "Employee handbook"),
        ("heading", "Leave"),
        ("paragraph", "Ten days after ten years."),
        ("list", "Apply three days ahead."),
        ("table", "| Years | Days |\n| --- | --- |\n| 10 | 10 |"),
        ("image", "Policy diagram"),
    ]
    assert document.elements[2].section_path == ["Leave"]
    assert document.elements[4].table_markdown == document.elements[4].text
    assert [(item.page_start, item.page_end) for item in document.elements] == [
        (1, 1), (1, 1), (1, 1), (1, 1), (2, 2), (2, 2),
    ]
    assert all(item.metadata == {"ocr": True} for item in document.elements)
    assert document.metadata == {}


def test_docling_result_preserves_every_available_page_span_and_marks_incomplete():
    from app.core.parsing.docling_parser import map_docling_result

    result = _result(
        status="partial_success",
        items=[_Item("text", "Spans both pages.", [1, 2])],
        timeout=True,
    )

    document = map_docling_result(result, expected_page_count=3, parser_version="2.113.0")

    assert document.page_count == 3
    assert document.elements[0].page_start == 1
    assert document.elements[0].page_end == 2
    assert document.quality.status == "review_required"
    assert document.quality.warnings == [
        "advanced_parser_incomplete",
        "missing_page_coverage",
    ]


def test_docling_result_uses_controlled_native_markdown_for_an_empty_table():
    from app.core.parsing.docling_parser import map_docling_result

    result = _result(
        items=[
            _Item("section_header", "Leave table", [1]),
            _Item(
                "table",
                "",
                [1],
                markdown="",
                bboxes=[_BBox(70, 100, 430, 270)],
            ),
        ],
        page_count=1,
    )

    document = map_docling_result(
        result,
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (72, 110, 430, 270), "| Years | Days |\n| --- | --- |\n| 10 | 10 |")
        ],
    )

    table = document.elements[1]
    assert table.element_type == "table"
    assert table.table_markdown == table.text
    assert table.metadata == {"ocr": False}
    assert document.quality.status == "passed"


def test_native_filled_table_marks_a_duplicate_ocr_data_row_for_review():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("text", "20年以上 15天", [1]),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(70, 100, 430, 270)],
                ),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (
                1,
                (72, 110, 430, 270),
                "| 工龄 | 年假天数 |\n| --- | --- |\n| 20年以上 | 15天 |",
            )
        ],
    )

    normalized_text = "".join(document.plain_text.split())
    assert normalized_text.count("20年以上") == 2
    assert normalized_text.count("15天") == 2
    assert document.elements[1].metadata == {"ocr": False}
    assert document.quality.status == "review_required"
    assert document.quality.warnings == ["advanced_parser_incomplete"]


def test_native_filled_table_ignores_header_repeated_in_non_table_content():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("section_header", "工龄 年假天数", [1]),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(70, 100, 430, 270)],
                ),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (
                1,
                (72, 110, 430, 270),
                "| 工龄 | 年假天数 |\n| --- | --- |\n| 20年以上 | 15天 |",
            )
        ],
    )

    assert document.quality.status == "passed"
    assert document.quality.warnings == []


def test_non_empty_docling_table_keeps_its_markdown_after_native_match_is_consumed():
    from app.core.parsing.docling_parser import map_docling_result

    docling_markdown = "| Docling |\n| --- |\n| kept |"
    document = map_docling_result(
        _result(
            items=[
                _Item(
                    "table",
                    "",
                    [1],
                    markdown=docling_markdown,
                    bboxes=[_BBox(70, 100, 430, 270)],
                )
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (72, 110, 430, 270), "| Native |\n| --- |\n| ignored |")
        ],
    )

    assert document.elements[0].text == docling_markdown
    assert document.elements[0].table_markdown == docling_markdown
    assert document.elements[0].metadata == {"ocr": True}
    assert document.quality.status == "passed"
    assert document.quality.warnings == []


def test_docling_result_blocks_an_empty_table_without_a_fallback():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("section_header", "Leave table", [1]),
                _Item("table", "", [1], markdown=""),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
    )

    assert document.quality.status == "review_required"
    assert document.quality.warnings == ["advanced_parser_incomplete"]


def test_native_table_fallback_preserves_same_page_before_table_after_order():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("text", "Before table", [1]),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(70, 200, 430, 300)],
                ),
                _Item("text", "After table", [1]),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (72, 205, 430, 295), "| Header |\n| --- |\n| value |")
        ],
    )

    assert [(item.element_type, item.text) for item in document.elements] == [
        ("paragraph", "Before table"),
        ("table", "| Header |\n| --- |\n| value |"),
        ("paragraph", "After table"),
    ]


def test_native_table_fallback_matches_multiple_same_page_tables_once_by_bbox():
    from app.core.parsing.docling_parser import map_docling_result

    top_markdown = "| Top |\n| --- |\n| first |"
    bottom_markdown = "| Bottom |\n| --- |\n| second |"
    document = map_docling_result(
        _result(
            items=[
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(50, 100, 250, 180)],
                ),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(50, 300, 250, 380)],
                ),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (52, 302, 248, 378), bottom_markdown),
            (1, (52, 102, 248, 178), top_markdown),
        ],
    )

    assert [item.text for item in document.elements] == [
        top_markdown,
        bottom_markdown,
    ]
    assert document.plain_text.count("first") == 1
    assert document.plain_text.count("second") == 1
    assert document.quality.status == "passed"


def test_unmatched_native_table_is_not_appended_or_allowed_to_pass():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(items=[_Item("text", "Body text", [1])], page_count=1),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (50, 200, 250, 280), "| Missing |\n| --- |\n| table |")
        ],
    )

    assert [item.text for item in document.elements] == ["Body text"]
    assert document.quality.status == "review_required"
    assert document.quality.warnings == ["advanced_parser_incomplete"]


def test_incidental_bbox_overlap_does_not_replace_a_docling_table():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("text", "Body text", [1]),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(50, 100, 250, 180)],
                ),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (240, 170, 400, 300), "| Wrong |\n| --- |\n| table |")
        ],
    )

    assert [item.text for item in document.elements] == ["Body text"]
    assert document.quality.status == "review_required"
    assert document.quality.warnings == ["advanced_parser_incomplete"]


def test_contained_small_bbox_does_not_match_a_large_docling_table():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("text", "Body text", [1]),
                _Item(
                    "table",
                    "",
                    [1],
                    markdown="",
                    bboxes=[_BBox(0, 0, 100, 100)],
                ),
            ],
            page_count=1,
        ),
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[
            (1, (10, 10, 20, 20), "| Wrong |\n| --- |\n| contained |")
        ],
    )

    assert [item.text for item in document.elements] == ["Body text"]
    assert document.quality.status == "review_required"
    assert document.quality.warnings == ["advanced_parser_incomplete"]


def test_bbox_overlap_ratio_is_iou_for_a_contained_box():
    from app.core.parsing.docling_parser import _bbox_overlap_ratio

    assert _bbox_overlap_ratio((0, 0, 100, 100), (10, 10, 20, 20)) == pytest.approx(
        0.01
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((0, 0, 0, 10), (0, 0, 10, 10)),
        ((10, 0, 0, 10), (0, 0, 10, 10)),
        ((0, 0, 10, 10), (5, 5, 5, 5)),
    ],
)
def test_bbox_overlap_ratio_returns_zero_for_non_positive_area(first, second):
    from app.core.parsing.docling_parser import _bbox_overlap_ratio

    assert _bbox_overlap_ratio(first, second) == 0


def test_runtime_validation_rejects_tempfile_directory_outside_parser_temp(
    monkeypatch, tmp_path
):
    from app.core.parsing import docling_parser

    parser_root = tmp_path / "parser"
    parser_temp = parser_root / "tmp"
    artifacts = parser_root / "artifacts"
    tessdata = parser_root / "tessdata"
    tesseract = parser_root / "tesseract.exe"
    parser_temp.mkdir(parents=True)
    artifacts.mkdir()
    tessdata.mkdir()
    tesseract.touch()
    (tessdata / "chi_sim.traineddata").touch()
    (tessdata / "eng.traineddata").touch()
    monkeypatch.setattr(
        docling_parser.settings, "parser_temp_dir", str(parser_temp)
    )
    monkeypatch.setattr(
        docling_parser.settings, "docling_artifacts_path", str(artifacts)
    )
    monkeypatch.setattr(docling_parser.settings, "tesseract_cmd", str(tesseract))
    monkeypatch.setattr(docling_parser.settings, "tessdata_prefix", str(tessdata))
    monkeypatch.setattr(docling_parser.tempfile, "gettempdir", lambda: str(tmp_path))

    with pytest.raises(RuntimeError, match="Docling runtime is unavailable"):
        docling_parser._validate_runtime_paths()


def test_docling_adapter_returns_controlled_failure_when_optional_runtime_is_unavailable(monkeypatch):
    from app.core.parsing import docling_parser

    monkeypatch.setattr(
        docling_parser,
        "_convert_docling_pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(r"C:\\Users\\Ada\\secret-token")
        ),
    )

    document = docling_parser.parse_docling_pdf("scanned.pdf", b"pdf", expected_page_count=1)

    assert document.page_count == 1
    assert document.elements == []
    assert document.quality.status == "failed"
    assert document.quality.warnings == ["parser_exception"]
    assert document.metadata == {}
