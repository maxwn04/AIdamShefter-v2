"""Dependency-boundary tests for the copied reporter service."""

from __future__ import annotations

import ast
from pathlib import Path


REPORTER_ROOT = Path(__file__).parents[4] / "backend" / "services" / "reporter"


def test_reporter_does_not_import_legacy_or_persistence_layers() -> None:
    forbidden_prefixes = (
        "backend.database",
        "backend.resources",
        "datalayer",
        "reporter_v2",
        "sqlalchemy",
    )
    imports = {
        imported
        for path in REPORTER_ROOT.rglob("*.py")
        for imported in _imports(path)
    }

    assert not {
        imported
        for imported in imports
        if any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for prefix in forbidden_prefixes
        )
    }


def test_reporter_has_no_reverse_dependency_from_datalayer() -> None:
    root = Path(__file__).parents[4]
    datalayer_paths = [
        *(root / "datalayer").rglob("*.py"),
        *(root / "backend" / "services" / "datalayer").rglob("*.py"),
    ]
    reverse_imports = {
        imported
        for path in datalayer_paths
        for imported in _imports(path)
        if imported == "backend.services.reporter"
        or imported.startswith("backend.services.reporter.")
    }

    assert reverse_imports == set()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names
