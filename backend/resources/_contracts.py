from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


NonBlankStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


def _optional_display_name(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


DisplayName = Annotated[str | None, BeforeValidator(_optional_display_name)]


def _normalize_tags(value: Any) -> Any:
    if not isinstance(value, list):
        raise ValueError("tags must be provided as a list")

    normalized: list[Any] = []
    seen: set[str] = set()
    for tag in value:
        if not isinstance(tag, str):
            normalized.append(tag)
            continue
        tag = tag.strip().casefold()
        if tag and tag not in seen:
            normalized.append(tag)
            seen.add(tag)
    return normalized


Tags = Annotated[list[NonBlankStr], BeforeValidator(_normalize_tags)]
