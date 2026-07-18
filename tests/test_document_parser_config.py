import pytest
from pydantic import ValidationError

from app.config import Settings


def test_document_parser_defaults_keep_large_artifacts_on_d_drive():
    settings = Settings(_env_file=None)

    assert settings.docling_artifacts_path == "D:/DevData/smartcs/docling/artifacts"
    assert settings.hf_home == "D:/DevData/smartcs/huggingface"
    assert settings.torch_home == "D:/DevData/smartcs/torch"
    assert settings.tesseract_cmd == "D:/DevData/smartcs/tesseract/tesseract.exe"
    assert settings.tessdata_prefix == "D:/DevData/smartcs/tesseract/tessdata/"
    assert settings.docling_device == "cpu"
    assert settings.docling_num_threads == 4

    for path in (
        settings.docling_artifacts_path,
        settings.hf_home,
        settings.torch_home,
        settings.tesseract_cmd,
        settings.tessdata_prefix,
    ):
        assert path.replace("\\", "/").lower().startswith("d:/")


def test_document_parser_settings_allow_d_drive_environment_overrides(monkeypatch):
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "D:/ParserData/artifacts")
    monkeypatch.setenv("HF_HOME", "D:/ParserData/huggingface")
    monkeypatch.setenv("TORCH_HOME", "D:/ParserData/torch")
    monkeypatch.setenv("TESSERACT_CMD", "D:/ParserData/tesseract/tesseract.exe")
    monkeypatch.setenv("TESSDATA_PREFIX", "D:/ParserData/tesseract/tessdata/")
    monkeypatch.setenv("DOCLING_DEVICE", "cpu")
    monkeypatch.setenv("DOCLING_NUM_THREADS", "2")

    settings = Settings(_env_file=None)

    assert settings.docling_artifacts_path == "D:/ParserData/artifacts"
    assert settings.hf_home == "D:/ParserData/huggingface"
    assert settings.torch_home == "D:/ParserData/torch"
    assert settings.tesseract_cmd == "D:/ParserData/tesseract/tesseract.exe"
    assert settings.tessdata_prefix == "D:/ParserData/tesseract/tessdata/"
    assert settings.docling_device == "cpu"
    assert settings.docling_num_threads == 2


def test_document_parser_rejects_paths_outside_d_drive(monkeypatch):
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "C:/temp/docling")

    with pytest.raises(ValidationError, match="D:"):
        Settings(_env_file=None)
