import json

from backend.api.export_openapi import render_openapi_schema


def test_openapi_export_is_deterministic_and_complete() -> None:
    first = render_openapi_schema()
    second = render_openapi_schema()

    assert first == second
    assert first.endswith("\n")

    schema = json.loads(first)
    assert schema["info"]["title"] == "AIdam API"
    assert "/health/live" in schema["paths"]
    assert "/api/v1/competitions" in schema["paths"]
    assert "/api/v1/models" in schema["paths"]
