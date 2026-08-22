from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import stat

import pytest

from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalArtifactVerificationError,
    LocalDatalayerFileStore,
    StoredLocalArtifact,
)


def test_store_bytes_is_content_addressed_idempotent_and_read_only(
    tmp_path: Path,
) -> None:
    store = LocalDatalayerFileStore(tmp_path)
    content = b'{"week":8}'

    first = store.store_bytes(LocalArtifactKind.PAYLOAD, content)
    second = store.store_bytes(LocalArtifactKind.PAYLOAD, content)
    opened = store.open_verified(
        first.storage_key,
        expected_sha256=first.sha256,
        expected_byte_length=first.byte_length,
    )

    assert second == first
    assert first.storage_key == (
        f"payloads/sha256/{first.sha256[:2]}/{first.sha256}.json"
    )
    assert opened.path.read_bytes() == content
    assert opened.path.is_relative_to(tmp_path.resolve())
    assert opened.path.stat().st_mode & stat.S_IWRITE == 0


def test_store_file_streams_into_snapshot_namespace(tmp_path: Path) -> None:
    source = tmp_path / "build.sqlite"
    content = b"sqlite" + b"x" * (1024 * 1024 + 17)
    source.write_bytes(content)
    store = LocalDatalayerFileStore(tmp_path / "artifacts")

    receipt = store.store_file(LocalArtifactKind.SNAPSHOT, source)
    opened = store.open_verified(
        receipt.storage_key,
        expected_sha256=receipt.sha256,
        expected_byte_length=receipt.byte_length,
    )

    assert receipt.storage_key == (
        f"snapshots/sha256/{receipt.sha256[:2]}/{receipt.sha256}.sqlite"
    )
    assert opened.path.read_bytes() == content


def test_concurrent_same_content_writers_share_one_verified_target(
    tmp_path: Path,
) -> None:
    store = LocalDatalayerFileStore(tmp_path)
    content = b'{"same":true}'

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(
            executor.map(
                lambda _: store.store_bytes(LocalArtifactKind.PAYLOAD, content),
                range(24),
            )
        )

    assert all(receipt == receipts[0] for receipt in receipts)
    targets = [path for path in tmp_path.rglob("*.json") if path.is_file()]
    assert len(targets) == 1
    assert targets[0].read_bytes() == content
    assert not any(path.is_file() for path in (tmp_path / ".staging").iterdir())


def test_store_rejects_existing_content_address_collision(tmp_path: Path) -> None:
    store = LocalDatalayerFileStore(tmp_path)
    intended = b"intended content"
    sha256 = hashlib.sha256(intended).hexdigest()
    target = (
        tmp_path
        / "payloads"
        / "sha256"
        / sha256[:2]
        / f"{sha256}.json"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"different content")

    with pytest.raises(LocalArtifactVerificationError, match="does not match"):
        store.store_bytes(LocalArtifactKind.PAYLOAD, intended)

    assert target.read_bytes() == b"different content"
    assert not any(path.is_file() for path in (tmp_path / ".staging").iterdir())


def test_open_verified_rejects_tampered_missing_and_mismatched_content(
    tmp_path: Path,
) -> None:
    store = LocalDatalayerFileStore(tmp_path)
    receipt = store.store_bytes(LocalArtifactKind.PAYLOAD, b"original")
    target = tmp_path / receipt.storage_key
    target.chmod(0o666)
    target.write_bytes(b"tampered")

    with pytest.raises(LocalArtifactVerificationError, match="does not match"):
        store.open_verified(
            receipt.storage_key,
            expected_sha256=receipt.sha256,
            expected_byte_length=receipt.byte_length,
        )

    target.chmod(0o666)
    target.write_bytes(b"original")
    with pytest.raises(LocalArtifactVerificationError, match="does not match"):
        store.open_verified(
            receipt.storage_key,
            expected_sha256=receipt.sha256,
            expected_byte_length=receipt.byte_length + 1,
        )

    target.unlink()
    with pytest.raises(LocalArtifactVerificationError, match="unavailable"):
        store.open_verified(
            receipt.storage_key,
            expected_sha256=receipt.sha256,
            expected_byte_length=receipt.byte_length,
        )


@pytest.mark.parametrize(
    ("storage_key", "sha256", "byte_length"),
    [
        ("../outside.json", "0" * 64, 0),
        ("/absolute.json", "0" * 64, 0),
        ("payloads\\sha256\\00\\value.json", "0" * 64, 0),
        ("payloads/sha256/00/value.json", "0" * 64, 0),
        ("payloads/sha256/ff/" + "0" * 64 + ".json", "0" * 64, 0),
        ("snapshots/sha256/00/" + "0" * 64 + ".json", "0" * 64, 0),
        ("payloads/sha256/00/" + "0" * 64 + ".json", "A" * 64, 0),
        ("payloads/sha256/00/" + "0" * 64 + ".json", "0" * 64, -1),
    ],
)
def test_artifact_receipts_reject_noncanonical_or_inconsistent_values(
    storage_key: str,
    sha256: str,
    byte_length: int,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        StoredLocalArtifact(
            storage_key=storage_key,
            sha256=sha256,
            byte_length=byte_length,
        )


def test_open_verified_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "payloads"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")
    store = LocalDatalayerFileStore(root)
    sha256 = "0" * 64

    with pytest.raises(ValueError, match="symbolic links"):
        store.open_verified(
            f"payloads/sha256/00/{sha256}.json",
            expected_sha256=sha256,
            expected_byte_length=0,
        )


def test_staging_file_is_cleaned_when_input_stream_fails(tmp_path: Path) -> None:
    store = LocalDatalayerFileStore(tmp_path / "artifacts")

    with pytest.raises(FileNotFoundError):
        store.store_file(LocalArtifactKind.SNAPSHOT, tmp_path / "missing.sqlite")

    assert not any(
        path.is_file() for path in (store.root / ".staging").iterdir()
    )
