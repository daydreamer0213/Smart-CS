from types import SimpleNamespace


class _Item:
    def __init__(self, label, text, pages, *, level=1, markdown=None):
        self.label = label
        self.text = text
        self.prov = [SimpleNamespace(page_no=page) for page in pages]
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
        pages=[object() for _ in range(page_count)],
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
            _Item("table", "", [1], markdown=""),
        ],
        page_count=1,
    )

    document = map_docling_result(
        result,
        expected_page_count=1,
        parser_version="2.113.0",
        table_fallbacks=[(1, "| Years | Days |\n| --- | --- |\n| 10 | 10 |")],
    )

    table = document.elements[1]
    assert table.element_type == "table"
    assert table.table_markdown == table.text
    assert table.metadata == {"ocr": False}
    assert document.quality.status == "passed"


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


def test_native_table_fallback_does_not_reorder_docling_items():
    from app.core.parsing.docling_parser import map_docling_result

    document = map_docling_result(
        _result(
            items=[
                _Item("section_header", "Page one", [1]),
                _Item("text", "Page two", [2]),
            ],
            page_count=2,
        ),
        expected_page_count=2,
        parser_version="2.113.0",
        table_fallbacks=[(1, "| Header |\n| --- |\n| value |")],
    )

    assert [(item.element_type, item.page_start) for item in document.elements] == [
        ("heading", 1),
        ("table", 1),
        ("paragraph", 2),
    ]


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
