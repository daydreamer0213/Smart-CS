import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


def test_document_fixture_manifest_covers_enterprise_shapes():
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["fixtures"]

    assert manifest["schema_version"] == 1
    assert {entry["category"] for entry in entries} == {
        "clean_text",
        "repeated_header_footer",
        "table",
        "scanned",
        "mixed_text_scan",
        "two_column",
        "encrypted",
        "headed_docx",
        "multi_sheet_xlsx",
    }
    assert all((FIXTURE_DIR / entry["filename"]).is_file() for entry in entries)
    assert all(entry["required_facts"] for entry in entries if entry["category"] != "encrypted")
