import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_docling_requirements_pin_verified_windows_cpu_pair():
    requirements = (Path(__file__).parents[1] / "requirements-docling.txt").read_text()

    assert "docling-slim[format-pdf,models-local]>=2.113,<2.114" in requirements
    assert "opencv-python-headless>=4.6.0.66,<5.0.0.0" in requirements
    assert "torch==2.12.1" in requirements
    assert "torchvision==0.27.1" in requirements


def test_docling_runtime_versions_and_configuration_are_committed():
    evidence = (
        Path(__file__).parents[1] / "docs" / "operations" / "docling-ocr-setup.md"
    ).read_text(encoding="utf-8")

    for expected in (
        "2026-07-18 在 Windows CPU 环境验证",
        "Python 3.12.13",
        "docling-slim 2.113.0",
        "docling-core 2.87.1",
        "docling-ibm-models 3.13.3",
        "opencv-python-headless 4.13.0.92",
        "torch 2.12.1",
        "torchvision 0.27.1",
        "Tesseract 5.5.2",
        "`chi_sim` 与 `eng`",
        "CPU、4 线程",
        "`D:\\DevData\\smartcs\\tmp`",
    ):
        assert expected in evidence


def test_document_parser_defaults_keep_large_artifacts_under_d_devdata_root():
    settings = Settings(_env_file=None)

    assert settings.parser_data_root == "D:/DevData/smartcs"
    assert settings.document_storage_dir == "D:/DevData/smartcs/documents"
    assert settings.parser_temp_dir == "D:/DevData/smartcs/tmp"
    assert settings.docling_artifacts_path == "D:/DevData/smartcs/docling/artifacts"
    assert settings.hf_home == "D:/DevData/smartcs/huggingface"
    assert settings.torch_home == "D:/DevData/smartcs/torch"
    assert settings.tesseract_cmd == "D:/DevData/smartcs/tesseract-env/Library/bin/tesseract.exe"
    assert settings.tessdata_prefix == "D:/DevData/smartcs/tesseract-env/share/tessdata/"
    assert settings.docling_device == "cpu"
    assert settings.docling_num_threads == 4


def test_document_parser_allows_child_overrides_under_default_root(monkeypatch):
    monkeypatch.setenv("PARSER_TEMP_DIR", "D:/DevData/smartcs/custom/tmp")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", "D:/DevData/smartcs/custom/documents")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "D:/DevData/smartcs/custom/artifacts")
    monkeypatch.setenv("HF_HOME", "D:/DevData/smartcs/custom/huggingface")
    monkeypatch.setenv("TORCH_HOME", "D:/DevData/smartcs/custom/torch")
    monkeypatch.setenv("TESSERACT_CMD", "D:/DevData/smartcs/custom/tesseract/tesseract.exe")
    monkeypatch.setenv("TESSDATA_PREFIX", "D:/DevData/smartcs/custom/tesseract/tessdata")

    settings = Settings(_env_file=None)

    assert settings.parser_temp_dir == "D:/DevData/smartcs/custom/tmp"
    assert settings.document_storage_dir == "D:/DevData/smartcs/custom/documents"
    assert settings.docling_artifacts_path == "D:/DevData/smartcs/custom/artifacts"
    assert settings.hf_home == "D:/DevData/smartcs/custom/huggingface"
    assert settings.torch_home == "D:/DevData/smartcs/custom/torch"
    assert settings.tesseract_cmd == "D:/DevData/smartcs/custom/tesseract/tesseract.exe"
    assert settings.tessdata_prefix == "D:/DevData/smartcs/custom/tesseract/tessdata/"


@pytest.mark.parametrize(
    "path",
    [
        "C:/ParserData/artifacts",
        "D:/ParserData/artifacts",
        "D:/DevData/smartcs/docling/../../escape",
        "D:/DevData/smartcs-sibling/artifacts",
    ],
)
def test_document_parser_rejects_paths_outside_default_root(monkeypatch, path):
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", path)

    with pytest.raises(ValidationError, match="parser_data_root"):
        Settings(_env_file=None)


def test_document_parser_rejects_temp_dir_outside_default_root(monkeypatch):
    monkeypatch.setenv("PARSER_TEMP_DIR", "D:/DevData/smartcs/../tmp")

    with pytest.raises(ValidationError, match="parser_data_root"):
        Settings(_env_file=None)


def test_document_parser_rejects_storage_dir_outside_default_root(monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", "C:/SmartCS/documents")

    with pytest.raises(ValidationError, match="parser_data_root"):
        Settings(_env_file=None)


def test_document_parser_rejects_non_cpu_device(monkeypatch):
    monkeypatch.setenv("DOCLING_DEVICE", "cuda")

    with pytest.raises(ValidationError, match="cpu"):
        Settings(_env_file=None)


def test_document_parser_allows_an_explicit_portable_data_root(monkeypatch):
    monkeypatch.setenv("PARSER_DATA_ROOT", "/var/lib/smartcs")
    monkeypatch.setenv("PARSER_TEMP_DIR", "/var/lib/smartcs/tmp")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", "/var/lib/smartcs/documents")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "/var/lib/smartcs/docling/artifacts")
    monkeypatch.setenv("HF_HOME", "/var/lib/smartcs/huggingface")
    monkeypatch.setenv("TORCH_HOME", "/var/lib/smartcs/torch")
    monkeypatch.setenv("TESSERACT_CMD", "/var/lib/smartcs/tesseract/tesseract")
    monkeypatch.setenv("TESSDATA_PREFIX", "/var/lib/smartcs/tesseract/tessdata")

    settings = Settings(_env_file=None)

    assert settings.parser_data_root == "/var/lib/smartcs"
    assert settings.parser_temp_dir == "/var/lib/smartcs/tmp"
    assert settings.document_storage_dir == "/var/lib/smartcs/documents"
    assert settings.tessdata_prefix == "/var/lib/smartcs/tesseract/tessdata/"


def test_parser_runtime_is_configured_from_settings_before_docling_validation(
    monkeypatch, tmp_path,
):
    for name in ("TEMP", "TMP", "HF_HOME", "TORCH_HOME", "TESSDATA_PREFIX"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tempfile, "tempdir", None)

    from app.core.parsing import docling_parser
    from app.core.parsing.runtime import configure_parser_runtime

    root = (tmp_path / "parser-data").resolve()
    artifacts = root / "docling" / "artifacts"
    temp_dir = root / "tmp"
    hf_home = root / "huggingface"
    torch_home = root / "torch"
    tesseract_cmd = root / "tesseract" / "tesseract.exe"
    tessdata = root / "tesseract" / "tessdata"
    for directory in (artifacts, temp_dir, hf_home, torch_home, tessdata):
        directory.mkdir(parents=True, exist_ok=True)
    tesseract_cmd.touch()
    for language in ("chi_sim", "eng"):
        (tessdata / f"{language}.traineddata").write_bytes(b"fixture")

    settings = Settings(
        _env_file=None,
        parser_data_root=str(root),
        document_storage_dir=str(root / "documents"),
        parser_temp_dir=str(temp_dir),
        docling_artifacts_path=str(artifacts),
        hf_home=str(hf_home),
        torch_home=str(torch_home),
        tesseract_cmd=str(tesseract_cmd),
        tessdata_prefix=str(tessdata),
    )
    monkeypatch.setattr(docling_parser, "settings", settings)
    configure_parser_runtime(settings)

    expected = {
        "TEMP": settings.parser_temp_dir,
        "TMP": settings.parser_temp_dir,
        "HF_HOME": settings.hf_home,
        "TORCH_HOME": settings.torch_home,
        "TESSDATA_PREFIX": settings.tessdata_prefix,
    }
    assert tempfile.tempdir == settings.parser_temp_dir
    assert tempfile.gettempdir() == settings.parser_temp_dir
    assert {name: os.environ[name] for name in expected} == expected
    assert all(Path(path).resolve().is_relative_to(root) for path in expected.values())
    docling_parser._validate_runtime_paths()
