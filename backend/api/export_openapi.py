"""Deterministically export the product API's OpenAPI document."""

import json
import sys
from typing import Any

from backend.api.app import create_app


def build_openapi_schema() -> dict[str, Any]:
    """Build the schema without starting the API runtime or opening a database."""

    return create_app().openapi()


def render_openapi_schema() -> str:
    """Render stable JSON suitable for downstream code generation."""

    return json.dumps(
        build_openapi_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def main() -> None:
    """Write the current schema to standard output."""

    sys.stdout.write(render_openapi_schema())


if __name__ == "__main__":
    main()
