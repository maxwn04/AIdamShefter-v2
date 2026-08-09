from decimal import Decimal

import pytest

from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    parse_json_bytes,
)


def test_parse_and_canonicalize_preserve_exact_fractional_values() -> None:
    parsed = parse_json_bytes(b'{"score":123.456700,"players":[2,1]}')

    assert isinstance(parsed, dict)
    assert parsed["score"] == Decimal("123.456700")
    assert canonical_json_bytes(parsed) == b'{"players":[2,1],"score":123.4567}'


def test_canonical_json_rejects_binary_float() -> None:
    with pytest.raises(TypeError, match="binary floats"):
        canonical_json_bytes({"score": 0.1})  # type: ignore[dict-item]


@pytest.mark.parametrize("raw", [b'{"score":NaN}', b'{"score":Infinity}'])
def test_parse_rejects_non_finite_numbers(raw: bytes) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        parse_json_bytes(raw)
