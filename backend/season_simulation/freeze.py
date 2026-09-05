"""Check every executable input again at campaign boundaries."""

from importlib.metadata import distribution, distributions
import hashlib
import os
from pathlib import Path
import platform
import shutil

from backend.season_simulation.contracts import RuntimeFreeze


ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAMES = (
    "AIDAM_CODE_VERSION", "AIDAM_REPORTER_REVISION", "AIDAM_GENERATION_REVISION",
    "OPENAI_API_BASE", "OPENAI_BASE_URL", "AZURE_API_BASE", "AZURE_API_VERSION",
    "REPORTER_MODEL", "REPORTER_FALLBACK_MODELS", "LITELLM_LOCAL_MODEL_COST_MAP",
    "PYTHON_DOTENV_DISABLED",
)


def pricing_path() -> Path:
    return Path(distribution("litellm").locate_file("litellm/model_prices_and_context_window_backup.json"))


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def runtime_freeze(root: Path = ROOT) -> RuntimeFreeze:
    paths = [path for path in (root / "backend").rglob("*")
             if path.is_file() and path.suffix in {".py", ".md", ".json", ".yml", ".ini"}
             and "__pycache__" not in path.parts and "tests" not in path.parts]
    paths.extend(root / name for name in ("pyproject.toml", "uv.lock", ".python-version")
                 if (root / name).is_file())
    return RuntimeFreeze(
        files={path.relative_to(root).as_posix(): file_hash(path) for path in sorted(paths)},
        packages={dist.metadata["Name"].lower(): dist.version for dist in distributions()
                  if dist.metadata.get("Name")},
        python=platform.python_version(),
        configuration={name: os.environ.get(name, "") for name in CONFIG_NAMES},
        pricing_sha256=file_hash(pricing_path()),
    )


def assert_runtime(expected: RuntimeFreeze, root: Path = ROOT) -> None:
    actual = runtime_freeze(root)
    if actual != expected:
        changed = [field for field in RuntimeFreeze.model_fields if getattr(actual, field) != getattr(expected, field)]
        if "configuration" in changed:
            changed.extend(name for name in CONFIG_NAMES if actual.configuration[name] != expected.configuration[name])
        raise ValueError("campaign runtime changed (" + ", ".join(changed) + "); use its frozen checkout")


def archive_runtime(freeze: RuntimeFreeze, destination: Path, root: Path = ROOT) -> None:
    if file_hash(pricing_path()) != freeze.pricing_sha256:
        raise ValueError("bundled pricing changed while archiving")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pricing_path(), destination / "model-prices.json")
    for relative, digest in freeze.files.items():
        source = root / relative
        if file_hash(source) != digest:
            raise ValueError("runtime changed while archiving")
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
