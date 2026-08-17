from __future__ import annotations

from uuid import UUID

from backend.resources.memory.common.kinds import MemoryKind


class MemoryApplicationError(Exception):
    """Base class for stable memory application failures."""


class GenerationMemoryContextClosedError(MemoryApplicationError):
    def __init__(self, generation_id: UUID) -> None:
        self.generation_id = generation_id
        super().__init__(
            f"generation memory context {generation_id} has already been finalized"
        )


class DuplicateContextNoteError(MemoryApplicationError):
    def __init__(self, scope: str, note_key: str) -> None:
        self.scope = scope
        self.note_key = note_key
        super().__init__(f"context note {scope}:{note_key} already exists")


class CanonicalStateHashMismatchError(MemoryApplicationError):
    def __init__(self, expected_hash: str, actual_hash: str) -> None:
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            "canonical state hash mismatch: "
            f"expected {expected_hash}, got {actual_hash}"
        )


class MemoryIdentityConflictError(MemoryApplicationError):
    def __init__(self, identity_id: UUID) -> None:
        self.identity_id = identity_id
        super().__init__(f"memory identity {identity_id} is already in use")


class EntityReferenceNotFoundError(MemoryApplicationError):
    def __init__(self, entity_kind: str, entity_id: UUID | str) -> None:
        self.entity_kind = entity_kind
        self.entity_id = entity_id
        super().__init__(f"{entity_kind} entity {entity_id} was not found")


class CrossCompetitionEntityReferenceError(MemoryApplicationError):
    def __init__(
        self,
        entity_kind: str,
        entity_id: UUID | str,
        expected_competition_id: UUID,
    ) -> None:
        self.entity_kind = entity_kind
        self.entity_id = entity_id
        self.expected_competition_id = expected_competition_id
        super().__init__(
            f"{entity_kind} entity {entity_id} does not belong to competition "
            f"{expected_competition_id}"
        )


class RevisionNotFoundError(MemoryApplicationError):
    def __init__(
        self,
        competition_id: UUID,
        revision_id: UUID | None = None,
    ) -> None:
        self.competition_id: UUID = competition_id
        self.revision_id: UUID | None = revision_id
        if revision_id is None:
            message = f"current revision was not found for competition {competition_id}"
        else:
            message = (
                f"revision {revision_id} was not found in competition {competition_id}"
            )
        super().__init__(message)


class SearchProjectionHydrationError(MemoryApplicationError):
    def __init__(
        self,
        version_id: UUID,
        projected_kind: MemoryKind,
        reason: str,
    ) -> None:
        self.version_id = version_id
        self.projected_kind = projected_kind
        self.reason = reason
        super().__init__(
            f"search candidate {version_id} projected as {projected_kind.value} "
            f"could not be hydrated canonically: {reason}"
        )


class TargetNotFoundError(MemoryApplicationError):
    def __init__(
        self,
        reference_id: UUID,
        expected_kinds: tuple[MemoryKind, ...],
    ) -> None:
        self.reference_id = reference_id
        self.expected_kinds = expected_kinds
        expected = ", ".join(kind.value for kind in expected_kinds)
        super().__init__(f"target {reference_id} was not found; expected {expected}")


class WrongTargetKindError(MemoryApplicationError):
    def __init__(
        self,
        reference_id: UUID,
        expected_kinds: tuple[MemoryKind, ...],
        actual_kind: MemoryKind,
    ) -> None:
        self.reference_id = reference_id
        self.expected_kinds = expected_kinds
        self.actual_kind = actual_kind
        expected = ", ".join(kind.value for kind in expected_kinds)
        super().__init__(
            f"target {reference_id} has kind {actual_kind.value}; expected {expected}"
        )


class CrossCompetitionReferenceError(MemoryApplicationError):
    def __init__(
        self,
        reference_id: UUID,
        expected_competition_id: UUID,
        actual_competition_id: UUID,
    ) -> None:
        self.reference_id = reference_id
        self.expected_competition_id = expected_competition_id
        self.actual_competition_id = actual_competition_id
        super().__init__(
            f"target {reference_id} belongs to competition {actual_competition_id}, "
            f"not {expected_competition_id}"
        )


class StaleItemVersionError(MemoryApplicationError):
    def __init__(
        self,
        item_id: UUID,
        expected_revision_number: int,
        actual_revision_number: int,
    ) -> None:
        self.item_id = item_id
        self.expected_revision_number = expected_revision_number
        self.actual_revision_number = actual_revision_number
        super().__init__(
            f"item {item_id} is at revision {actual_revision_number}, "
            f"not {expected_revision_number}"
        )


class StaleCanonicalRevisionError(MemoryApplicationError):
    def __init__(
        self,
        competition_id: UUID,
        expected_revision_id: UUID,
        actual_revision_id: UUID,
    ) -> None:
        self.competition_id = competition_id
        self.expected_revision_id = expected_revision_id
        self.actual_revision_id = actual_revision_id
        super().__init__(
            f"competition {competition_id} is at canonical revision "
            f"{actual_revision_id}, not {expected_revision_id}"
        )
