"""Concrete content-addressed local storage for payloads and SQLite snapshots."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile


class LocalArtifactKind(StrEnum):
    PAYLOAD = "payloads"
    SNAPSHOT = "snapshots"

    @property
    def suffix(self) -> str:
        return ".json" if self is LocalArtifactKind.PAYLOAD else ".sqlite"


@dataclass(frozen=True, slots=True)
class StoredLocalArtifact:
    storage_key: str
    sha256: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class VerifiedLocalArtifact:
    path: Path
    storage_key: str
    sha256: str
    byte_length: int


class LocalArtifactVerificationError(RuntimeError):
    """Stored bytes do not match their immutable receipt."""


class LocalDatalayerFileStore:
    """Own atomic writes, content addressing, containment, and read verification."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def store_bytes(
        self,
        kind: LocalArtifactKind,
        content: bytes,
    ) -> StoredLocalArtifact:
        return self._store_chunks(kind, (content,))

    def store_file(
        self,
        kind: LocalArtifactKind,
        source: Path,
    ) -> StoredLocalArtifact:
        def chunks() -> Iterable[bytes]:
            with source.open("rb") as input_file:
                while chunk := input_file.read(1024 * 1024):
                    yield chunk

        return self._store_chunks(kind, chunks())

    def open_verified(
        self,
        storage_key: str,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> VerifiedLocalArtifact:
        target = self._resolve_key(storage_key)
        actual_sha256, actual_byte_length = _hash_file(target)
        if (
            actual_sha256 != expected_sha256
            or actual_byte_length != expected_byte_length
        ):
            raise LocalArtifactVerificationError(
                "stored content does not match its hash and size receipt"
            )
        return VerifiedLocalArtifact(
            path=target,
            storage_key=storage_key,
            sha256=actual_sha256,
            byte_length=actual_byte_length,
        )

    def _store_chunks(
        self,
        kind: LocalArtifactKind,
        chunks: Iterable[bytes],
    ) -> StoredLocalArtifact:
        staging_root = self._root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=staging_root)
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        byte_length = 0
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                for chunk in chunks:
                    digest.update(chunk)
                    byte_length += len(chunk)
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())

            sha256 = digest.hexdigest()
            storage_key = _content_key(kind, sha256)
            target = self._resolve_key(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                existing_sha256, existing_size = _hash_file(target)
                if existing_sha256 != sha256 or existing_size != byte_length:
                    raise LocalArtifactVerificationError(
                        "existing content-addressed file failed verification"
                    )
            else:
                os.replace(temporary_path, target)
                target.chmod(0o444)
            return StoredLocalArtifact(
                storage_key=storage_key,
                sha256=sha256,
                byte_length=byte_length,
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        relative = PurePosixPath(storage_key)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("storage key must be a contained relative path")
        target = self._root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("storage key escapes the configured local root")
        return target


def _content_key(kind: LocalArtifactKind, sha256: str) -> str:
    return f"{kind.value}/sha256/{sha256[:2]}/{sha256}{kind.suffix}"


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_length = 0
    try:
        with path.open("rb") as content:
            while chunk := content.read(1024 * 1024):
                digest.update(chunk)
                byte_length += len(chunk)
    except OSError as error:
        raise LocalArtifactVerificationError("stored content is unavailable") from error
    return digest.hexdigest(), byte_length
