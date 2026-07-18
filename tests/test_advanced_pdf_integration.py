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
            [
                "新员工应在首日完成身份核验。",
                "入职资料应在次日完成归档。",
                "离职员工应在三天内归还设备。",
                "离职权限应在当日完成关闭。",
            ],
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
    assert document.quality.status == "passed"
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
        assert len(tables) == 1
        assert all(table.metadata == {"ocr": False} for table in tables)
        rows = ["".join(row.split()) for row in tables[0].table_markdown.splitlines()]
        header = next(row for row in rows if "工龄" in row)
        last_row = next(row for row in rows if "20年以上" in row)
        assert "年假天数" in header
        assert "15天" in last_row
        for value in ("工龄", "年假天数", "20年以上", "15天"):
            assert tables[0].table_markdown.count(value) == 1
