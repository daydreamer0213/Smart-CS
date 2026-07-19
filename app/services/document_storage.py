"""Content-addressed storage for original document files."""

import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from app.config import settings


_SAFE_TENANT = re.compile(r"^[A-Za-z0-9_-]+$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".txt", ".md"})


def _storage_root() -> Path:
    return Path(settings.document_storage_dir).resolve()


def _resolve_key(storage_key: str) -> Path:
    key = PurePosixPath(storage_key)
    if (
        not storage_key
        or "\\" in storage_key
        or key.is_absolute()
        or any(part in {"", ".", ".."} for part in key.parts)
    ):
        raise ValueError("Invalid storage key")
    root = _storage_root()
    target = (root / Path(*key.parts)).resolve()
    try:
        contained = os.path.commonpath((str(root), str(target))) == str(root)
    except ValueError:
        contained = False
    if not contained:
        raise ValueError("Invalid storage key")
    return target


def store_original(
    tenant_id: str,
    file_hash: str,
    suffix: str,
    data: bytes,
) -> str:
    suffix = suffix.lower()
    if not _SAFE_TENANT.fullmatch(tenant_id) or not _SHA256.fullmatch(file_hash):
        raise ValueError("Invalid document storage identity")
    if suffix not in _SUFFIXES:
        raise ValueError("Unsupported document suffix")

    storage_key = f"{tenant_id}/{file_hash}{suffix}"
    target = _resolve_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise RuntimeError("Stored document content does not match its hash")
        return storage_key

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{file_hash}.", delete=False
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return storage_key


def read_original(storage_key: str) -> bytes:
    return _resolve_key(storage_key).read_bytes()


def delete_original(storage_key: str) -> None:
    path = _resolve_key(storage_key)
    try:
        path.unlink()
    except FileNotFoundError:
        return
