"""Concrete content-addressed local storage for datalayer artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_KEY = re.compile(
    r"^(payloads|snapshots)/sha256/([0-9a-f]{2})/"
    r"([0-9a-f]{64})(\.json|\.sqlite)$"
)
_CHUNK_SIZE = 1024 * 1024


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

    def __post_init__(self) -> None:
        _validate_receipt(self.storage_key, self.sha256, self.byte_length)


@dataclass(frozen=True, slots=True)
class VerifiedLocalArtifact:
    path: Path
    storage_key: str
    sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        _validate_receipt(self.storage_key, self.sha256, self.byte_length)
        if not self.path.is_absolute():
            raise ValueError("verified local artifact path must be absolute")


class LocalArtifactVerificationError(RuntimeError):
    """Stored bytes are unavailable or do not match their immutable receipt."""


class LocalDatalayerFileStore:
    """Own content addressing, atomic publication, and verified local reads."""

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
        if not isinstance(content, bytes):
            raise TypeError("local artifact content must be bytes")
        return self._store_chunks(kind, (content,))

    def store_file(
        self,
        kind: LocalArtifactKind,
        source: Path,
    ) -> StoredLocalArtifact:
        def chunks() -> Iterable[bytes]:
            with source.open("rb") as input_file:
                while chunk := input_file.read(_CHUNK_SIZE):
                    yield chunk

        return self._store_chunks(kind, chunks())

    def open_verified(
        self,
        storage_key: str,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> VerifiedLocalArtifact:
        _validate_receipt(storage_key, expected_sha256, expected_byte_length)
        target = self._resolve_key(storage_key)
        self._verify_file(target, expected_sha256, expected_byte_length)
        return VerifiedLocalArtifact(
            path=target,
            storage_key=storage_key,
            sha256=expected_sha256,
            byte_length=expected_byte_length,
        )

    def _store_chunks(
        self,
        kind: LocalArtifactKind,
        chunks: Iterable[bytes],
    ) -> StoredLocalArtifact:
        if not isinstance(kind, LocalArtifactKind):
            raise TypeError("kind must be a LocalArtifactKind")
        staging_root = self._root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=staging_root)
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        byte_length = 0
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("local artifact chunks must be bytes")
                    digest.update(chunk)
                    byte_length += len(chunk)
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())

            sha256 = digest.hexdigest()
            self._verify_file(temporary_path, sha256, byte_length)
            storage_key = _content_key(kind, sha256)
            target = self._resolve_key(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._publish_exclusive(
                temporary_path,
                target,
                expected_sha256=sha256,
                expected_byte_length=byte_length,
            )
            return StoredLocalArtifact(
                storage_key=storage_key,
                sha256=sha256,
                byte_length=byte_length,
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    def _publish_exclusive(
        self,
        temporary_path: Path,
        target: Path,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> None:
        try:
            os.link(temporary_path, target)
        except FileExistsError:
            self._verify_file(target, expected_sha256, expected_byte_length)
            target.chmod(0o444)
            return

        try:
            temporary_path.unlink()
            target.chmod(0o444)
            self._verify_file(target, expected_sha256, expected_byte_length)
        except Exception:
            try:
                target.chmod(0o666)
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _resolve_key(self, storage_key: str) -> Path:
        if "\\" in storage_key:
            raise ValueError("storage key must use POSIX separators")
        relative = PurePosixPath(storage_key)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("storage key must be a contained relative path")
        candidate = self._root.joinpath(*relative.parts)
        current = self._root
        for part in relative.parts[:-1]:
            current /= part
            if _is_link_or_junction(current):
                raise ValueError("storage key must not traverse symbolic links")
        if _is_link_or_junction(candidate):
            raise ValueError("storage key must not resolve through a symbolic link")
        return candidate

    @staticmethod
    def _verify_file(
        path: Path,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> None:
        actual_sha256, actual_byte_length = _hash_file(path)
        if (
            actual_sha256 != expected_sha256
            or actual_byte_length != expected_byte_length
        ):
            raise LocalArtifactVerificationError(
                "stored content does not match its hash and size receipt"
            )


def _content_key(kind: LocalArtifactKind, sha256: str) -> str:
    return f"{kind.value}/sha256/{sha256[:2]}/{sha256}{kind.suffix}"


def _validate_receipt(storage_key: str, sha256: str, byte_length: int) -> None:
    if not _SHA256.fullmatch(sha256):
        raise ValueError("artifact SHA-256 must be 64 lowercase hexadecimal digits")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int):
        raise TypeError("artifact byte length must be an integer")
    if byte_length < 0:
        raise ValueError("artifact byte length must be non-negative")
    match = _STORAGE_KEY.fullmatch(storage_key)
    if match is None:
        raise ValueError("storage key is not a canonical datalayer artifact key")
    namespace, prefix, key_sha256, suffix = match.groups()
    expected_suffix = ".json" if namespace == "payloads" else ".sqlite"
    if prefix != sha256[:2] or key_sha256 != sha256 or suffix != expected_suffix:
        raise ValueError("storage key does not match the artifact receipt")


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_length = 0
    try:
        with path.open("rb") as content:
            while chunk := content.read(_CHUNK_SIZE):
                digest.update(chunk)
                byte_length += len(chunk)
    except OSError as error:
        raise LocalArtifactVerificationError("stored content is unavailable") from error
    return digest.hexdigest(), byte_length


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())
