import ast
from pathlib import Path


QUERY_ROOT = Path(__file__).parents[3] / "services" / "datalayer" / "query"
FORBIDDEN_PREFIXES = (
    "backend.database",
    "backend.resources",
    "backend.services.datalayer.refresh_service",
    "backend.services.datalayer.snapshot_service",
    "backend.services.datalayer.sleeper",
    "datalayer",
    "reporter_memory",
    "reporter_v2",
)


def test_frozen_query_runtime_has_no_forbidden_imports() -> None:
    violations = []
    for path in QUERY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []
