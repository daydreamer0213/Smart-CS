from pathlib import Path

import pytest

from app.config import settings


def test_store_original_returns_relative_content_addressed_key(tmp_path, monkeypatch):
    from app.services.document_storage import read_original, store_original

    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))

    key = store_original("tenant-1", "a" * 64, ".pdf", b"content")

    assert key == f"tenant-1/{'a' * 64}.pdf"
    assert not Path(key).is_absolute()
    assert read_original(key) == b"content"


def test_store_original_is_idempotent_for_same_content(tmp_path, monkeypatch):
    from app.services.document_storage import store_original

    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))
    key = store_original("tenant-1", "b" * 64, ".txt", b"same")

    assert store_original("tenant-1", "b" * 64, ".txt", b"same") == key
    assert (tmp_path / Path(key)).read_bytes() == b"same"


@pytest.mark.parametrize("storage_key", ["../secret", "/absolute/file", "tenant/../../secret"])
def test_read_original_rejects_paths_outside_storage_root(
    tmp_path, monkeypatch, storage_key,
):
    from app.services.document_storage import read_original

    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))

    with pytest.raises(ValueError, match="Invalid storage key"):
        read_original(storage_key)
