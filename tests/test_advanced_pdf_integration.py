import os
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "documents"


@pytest.mark.skipif(
    os.environ.get("RUN_DOCLING_INTEGRATION") != "1",
    reason="set RUN_DOCLING_INTEGRATION=1 to run local Docling fixtures",
)
@pytest.mark.parametrize(
    ("filename", "page_count", "expected_fragments"),
    [
        ("scanned_policy.pdf", 1, ["育儿假每年五天。"]),
        (
            "mixed_policy.pdf",
            2,
            ["驻外员工住宿由公司统一安排。", "驻外补贴标准为每月3000元。"],
        ),
        ("leave_table.pdf", 1, ["工龄", "年假天数", "20年以上", "15天"]),
        (
            "two_column_policy.pdf",
            1,
            ["新员工应在首日完成身份核验。", "离职员工应在三天内归还设备。"],
        ),
    ],
)
def test_advanced_pdf_fixtures_use_docling_with_controlled_quality(
    filename, page_count, expected_fragments
):
    from app.core.parsing.router import parse_structured_file

    document = parse_structured_file(filename, (FIXTURES / filename).read_bytes())

    assert document.parser_name == "docling"
    assert document.page_count == page_count
    assert document.quality.status in {"passed", "review_required"}
    assert "parser_exception" not in document.quality.warnings
    assert document.elements
    assert all(
        set(element.metadata) == {"ocr"}
        and isinstance(element.metadata["ocr"], bool)
        for element in document.elements
    )
    assert document.quality.metrics["ocr_pages"] == page_count

    normalized_text = "".join(document.plain_text.split())
    offsets = [normalized_text.index(fragment) for fragment in expected_fragments]
    if filename != "leave_table.pdf":
        assert offsets == sorted(offsets)

    if filename == "leave_table.pdf":
        tables = [element for element in document.elements if element.table_markdown]
        assert tables
        assert all(table.metadata == {"ocr": False} for table in tables)
