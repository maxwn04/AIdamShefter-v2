"""Immutable contracts for normalized Sleeper scope heads."""

from uuid import UUID

from pydantic import Field, StrictBool

from backend.resources._contracts import ContractModel
from backend.services.datalayer.contracts import ApplyDisposition
from backend.services.datalayer.sleeper.scope import ScopeKey


class ApplyResult(ContractModel):
    """Outcome of atomically applying one observed endpoint scope."""

    request_id: UUID
    scope_key: ScopeKey
    disposition: ApplyDisposition
    head_request_id: UUID
    normalized_row_count: int = Field(strict=True, ge=0)
    changed_current_view: StrictBool
