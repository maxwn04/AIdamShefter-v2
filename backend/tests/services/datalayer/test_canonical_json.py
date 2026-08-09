from decimal import Decimal

import pytest

from backend.json import (
    canonical_json_bytes,
    canonical_json_text,
    parse_json_bytes,
    parse_json_text,
)


def test_parse_and_canonicalize_preserve_exact_fractional_values() -> None:
    parsed = parse_json_bytes(b'{"score":123.456700,"players":[2,1]}')

    assert isinstance(parsed, dict)
    assert parsed["score"] == Decimal("123.456700")
    assert canonical_json_bytes(parsed) == b'{"players":[2,1],"score":123.4567}'


def test_canonical_json_rejects_binary_float() -> None:
    with pytest.raises(TypeError, match="binary floats"):
        canonical_json_bytes({"score": 0.1})  # type: ignore[dict-item]


def test_text_boundary_round_trips_exact_fractional_values() -> None:
    encoded = canonical_json_text({"score": Decimal("1.2300")})

    assert encoded == '{"score":1.23}'
    assert parse_json_text(encoded) == {"score": Decimal("1.23")}


@pytest.mark.parametrize("raw", [b'{"score":NaN}', b'{"score":Infinity}'])
def test_parse_rejects_non_finite_numbers(raw: bytes) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        parse_json_bytes(raw)
