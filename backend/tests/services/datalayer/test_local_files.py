from pathlib import Path

import pytest

from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalArtifactVerificationError,
    LocalDatalayerFileStore,
)


def test_store_bytes_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = LocalDatalayerFileStore(tmp_path)

    first = store.store_bytes(LocalArtifactKind.PAYLOAD, b'{"week":8}')
    second = store.store_bytes(LocalArtifactKind.PAYLOAD, b'{"week":8}')
    opened = store.open_verified(
        first.storage_key,
        expected_sha256=first.sha256,
        expected_byte_length=first.byte_length,
    )

    assert second == first
    assert opened.path.read_bytes() == b'{"week":8}'
    assert opened.path.is_relative_to(tmp_path.resolve())


def test_store_file_uses_snapshot_namespace(tmp_path: Path) -> None:
    source = tmp_path / "build.sqlite"
    source.write_bytes(b"sqlite bytes")
    store = LocalDatalayerFileStore(tmp_path / "artifacts")

    receipt = store.store_file(LocalArtifactKind.SNAPSHOT, source)

    assert receipt.storage_key.startswith("snapshots/sha256/")
    assert receipt.storage_key.endswith(".sqlite")


def test_open_verified_rejects_tampered_content(tmp_path: Path) -> None:
    store = LocalDatalayerFileStore(tmp_path)
    receipt = store.store_bytes(LocalArtifactKind.PAYLOAD, b"original")
    target = tmp_path / receipt.storage_key
    target.chmod(0o644)
    target.write_bytes(b"tampered")

    with pytest.raises(LocalArtifactVerificationError):
        store.open_verified(
            receipt.storage_key,
            expected_sha256=receipt.sha256,
            expected_byte_length=receipt.byte_length,
        )


def test_open_verified_rejects_escape_key(tmp_path: Path) -> None:
    store = LocalDatalayerFileStore(tmp_path)

    with pytest.raises(ValueError):
        store.open_verified(
            "../outside.sqlite",
            expected_sha256="0" * 64,
            expected_byte_length=0,
        )
