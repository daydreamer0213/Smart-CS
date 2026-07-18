from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_docling_requirements_pin_verified_windows_cpu_pair():
    requirements = (Path(__file__).parents[1] / "requirements-docling.txt").read_text()

    assert "torch==2.12.1" in requirements
    assert "torchvision==0.27.1" in requirements


def test_document_parser_defaults_keep_large_artifacts_under_d_devdata_root():
    settings = Settings(_env_file=None)

    assert settings.parser_data_root == "D:/DevData/smartcs"
    assert settings.parser_temp_dir == "D:/DevData/smartcs/tmp"
    assert settings.docling_artifacts_path == "D:/DevData/smartcs/docling/artifacts"
    assert settings.hf_home == "D:/DevData/smartcs/huggingface"
    assert settings.torch_home == "D:/DevData/smartcs/torch"
    assert settings.tesseract_cmd == "D:/DevData/smartcs/tesseract/tesseract.exe"
    assert settings.tessdata_prefix == "D:/DevData/smartcs/tesseract/tessdata/"
    assert settings.docling_device == "cpu"
    assert settings.docling_num_threads == 4


def test_document_parser_allows_child_overrides_under_default_root(monkeypatch):
    monkeypatch.setenv("PARSER_TEMP_DIR", "D:/DevData/smartcs/custom/tmp")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "D:/DevData/smartcs/custom/artifacts")
    monkeypatch.setenv("HF_HOME", "D:/DevData/smartcs/custom/huggingface")
    monkeypatch.setenv("TORCH_HOME", "D:/DevData/smartcs/custom/torch")
    monkeypatch.setenv("TESSERACT_CMD", "D:/DevData/smartcs/custom/tesseract/tesseract.exe")
    monkeypatch.setenv("TESSDATA_PREFIX", "D:/DevData/smartcs/custom/tesseract/tessdata")

    settings = Settings(_env_file=None)

    assert settings.parser_temp_dir == "D:/DevData/smartcs/custom/tmp"
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


def test_document_parser_rejects_non_cpu_device(monkeypatch):
    monkeypatch.setenv("DOCLING_DEVICE", "cuda")

    with pytest.raises(ValidationError, match="cpu"):
        Settings(_env_file=None)


def test_document_parser_allows_an_explicit_portable_data_root(monkeypatch):
    monkeypatch.setenv("PARSER_DATA_ROOT", "/var/lib/smartcs")
    monkeypatch.setenv("PARSER_TEMP_DIR", "/var/lib/smartcs/tmp")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "/var/lib/smartcs/docling/artifacts")
    monkeypatch.setenv("HF_HOME", "/var/lib/smartcs/huggingface")
    monkeypatch.setenv("TORCH_HOME", "/var/lib/smartcs/torch")
    monkeypatch.setenv("TESSERACT_CMD", "/var/lib/smartcs/tesseract/tesseract")
    monkeypatch.setenv("TESSDATA_PREFIX", "/var/lib/smartcs/tesseract/tessdata")

    settings = Settings(_env_file=None)

    assert settings.parser_data_root == "/var/lib/smartcs"
    assert settings.parser_temp_dir == "/var/lib/smartcs/tmp"
    assert settings.tessdata_prefix == "/var/lib/smartcs/tesseract/tessdata/"
