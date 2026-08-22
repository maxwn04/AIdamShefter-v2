from decimal import Decimal

import pytest

from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    canonical_json_sha256,
    parse_json_bytes,
)


def test_parse_and_canonicalize_preserve_exact_fractional_values() -> None:
    parsed = parse_json_bytes(
        b'{"score":123.456700,"negative_zero":-0.00,"players":[2,1]}'
    )

    assert isinstance(parsed, dict)
    assert parsed["score"] == Decimal("123.456700")
    assert canonical_json_bytes(parsed) == (
        b'{"negative_zero":0,"players":[2,1],"score":123.4567}'
    )


def test_canonical_json_has_stable_unicode_key_order_and_hash() -> None:
    value = {
        "z": Decimal("1E+3"),
        "message": "caf\u00e9",
        "nested": {"truth": True, "nothing": None},
    }

    assert canonical_json_bytes(value) == (
        b'{"message":"caf\xc3\xa9","nested":{"nothing":null,"truth":true},"z":1000}'
    )
    assert canonical_json_sha256(value) == (
        "981209b0fd19f37d3e69abf9cb69984576a3c285a7d7088812320fcad3ec3376"
    )


def test_parse_preserves_large_integers() -> None:
    parsed = parse_json_bytes(b'{"value":123456789012345678901234567890}')

    assert parsed == {"value": 123456789012345678901234567890}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"score": 0.1}, "binary floats"),
        ({1: "value"}, "keys must be strings"),
        ({"value": Decimal("NaN")}, "must be finite"),
        ({"value": (1, 2)}, "unsupported JSON value"),
    ],
)
def test_canonical_json_rejects_values_outside_the_contract(
    value: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        canonical_json_bytes(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw",
    [b'{"score":NaN}', b'{"score":Infinity}', b'{"score":-Infinity}'],
)
def test_parse_rejects_non_finite_numbers(raw: bytes) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        parse_json_bytes(raw)
