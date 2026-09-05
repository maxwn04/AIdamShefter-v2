"""Strictly identified, disposable local PostgreSQL targets for season runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
from uuid import uuid4

from sqlalchemy.engine import make_url


LABEL = "aidam.season-simulation.target"
NAME = re.compile(r"^aidam-season-[a-z0-9][a-z0-9-]{0,55}$")


@dataclass(frozen=True)
class DockerTarget:
    name: str
    identity: str
    container_id: str
    port: int
    database: str
    env_file: str
    output_root: str


def _docker(*args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["docker", *args], input=input, capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


def assert_free_port(port: int) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("port must be in 1024..65535")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def read_target(path: Path) -> DockerTarget:
    return DockerTarget(**json.loads(path.read_text(encoding="utf-8")))


def verify_target(target: DockerTarget) -> None:
    """Refuse another, replaced, non-local, or stopped container."""
    if not NAME.fullmatch(target.name) or target.database != "aidam":
        raise ValueError("not a season simulation target")
    observed = json.loads(_docker("inspect", target.name))[0]
    bindings = observed["HostConfig"]["PortBindings"].get("5432/tcp", [])
    if (
        observed["Id"] != target.container_id
        or observed["Config"].get("Labels", {}).get(LABEL) != target.identity
        or not observed["State"]["Running"]
        or bindings != [{"HostIp": "127.0.0.1", "HostPort": str(target.port)}]
    ):
        raise ValueError("Docker target identity/state/port differs from its receipt")


def target_environment(target: DockerTarget) -> dict[str, str]:
    """Read private local credentials without logging them."""
    environment = dict(
        line.split("=", 1)
        for line in Path(target.env_file).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    for key in ("AIDAM_TEST_DATABASE_URL", "AIDAM_MIGRATION_DATABASE_URL", "AIDAM_DATABASE_URL", "AIDAM_WORKER_DATABASE_URL"):
        url = make_url(environment[key])
        if (url.drivername, url.host, url.port, url.database) != ("postgresql+psycopg", "127.0.0.1", target.port, target.database):
            raise ValueError("target database environment does not match isolated Docker receipt")
    if Path(environment["AIDAM_DATALAYER_ROOT"]).resolve() != (Path(target.output_root) / "data").resolve():
        raise ValueError("target data root differs from isolated output directory")
    return environment


def create_target(*, name: str, output_root: Path, port: int = 55441) -> DockerTarget:
    if not NAME.fullmatch(name):
        raise ValueError("name must start aidam-season- and contain lowercase letters/digits/hyphens")
    root = output_root.resolve()
    if ".context" not in root.parts:
        raise ValueError("simulation outputs must live under ignored .context")
    if root.exists():
        raise FileExistsError("refusing an existing target output directory")
    existing = _docker("ps", "-a", "--format", "{{.Names}}").decode().splitlines()
    if name in existing:
        raise FileExistsError("refusing an existing Docker container")
    assert_free_port(port)
    root.mkdir(parents=True)
    identity = str(uuid4())
    password = secrets.token_hex(24)
    env_file = root / "target.env"
    env_file.write_text(
        f"POSTGRES_PASSWORD={password}\nPOSTGRES_DB=aidam\nPOSTGRES_USER=postgres\n",
        encoding="utf-8",
    )
    container_id = _docker(
        "run", "--detach", "--name", name, "--label", f"{LABEL}={identity}",
        "--publish", f"127.0.0.1:{port}:5432", "--env-file", str(env_file),
        "--tmpfs", "/var/lib/postgresql/data", "postgres:17",
    ).decode().strip()
    url = f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/aidam"
    env_file.write_text(
        env_file.read_text(encoding="utf-8")
        + f"AIDAM_TEST_DATABASE_URL={url}\nAIDAM_MIGRATION_DATABASE_URL={url}\n"
        + f"AIDAM_DATABASE_URL=postgresql+psycopg://aidam_api:{password}@127.0.0.1:{port}/aidam\n"
        + f"AIDAM_WORKER_DATABASE_URL=postgresql+psycopg://aidam_worker:{password}@127.0.0.1:{port}/aidam\n"
        + "AIDAM_DATABASE_REQUIRE_TLS=false\nAIDAM_MIGRATION_REQUIRE_TLS=false\n"
        + f"AIDAM_DATALAYER_ROOT={root / 'data'}\n",
        encoding="utf-8",
    )
    target = DockerTarget(name, identity, container_id, port, "aidam", str(env_file), str(root))
    (root / "target.json").write_text(json.dumps(asdict(target), indent=2) + "\n", encoding="utf-8")
    for _ in range(60):
        result = subprocess.run(
            ["docker", "exec", name, "pg_isready", "-U", "postgres", "-d", "aidam"],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("new isolated PostgreSQL target did not become ready")
    verify_target(target)
    sql = f"""
CREATE ROLE aidam_owner NOLOGIN;
CREATE ROLE aidam_runtime NOLOGIN;
CREATE ROLE aidam_migrator LOGIN PASSWORD '{password}' NOINHERIT;
CREATE ROLE aidam_api LOGIN PASSWORD '{password}';
CREATE ROLE aidam_worker LOGIN PASSWORD '{password}';
GRANT aidam_owner TO aidam_migrator;
GRANT aidam_runtime TO aidam_api, aidam_worker;
GRANT CONNECT, CREATE ON DATABASE aidam TO aidam_owner;
GRANT CONNECT ON DATABASE aidam TO aidam_migrator, aidam_api, aidam_worker;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO aidam_owner;
"""
    _docker("exec", "-i", name, "psql", "-U", "postgres", "-d", "aidam", "-v", "ON_ERROR_STOP=1", input=sql.encode())
    return target


def dump_database(target: DockerTarget, destination: Path) -> Path:
    """Atomic restorable dump; callers must separately retain external data assets."""
    verify_target(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with temporary.open("wb") as stream:
        result = subprocess.run(
            ["docker", "exec", target.name, "pg_dump", "-U", "postgres", "-d", target.database, "--format=custom"],
            stdout=stream, stderr=subprocess.PIPE, check=False,
        )
    if result.returncode:
        raise RuntimeError("database export failed: " + result.stderr.decode(errors="replace"))
    temporary.replace(destination)
    return destination


def restore_database(target: DockerTarget, source: Path) -> None:
    """Restore only to an identified new target with no application schemas."""
    verify_target(target)
    populated = _docker(
        "exec", target.name, "psql", "-U", "postgres", "-d", target.database,
        "-At", "-c",
        "SELECT count(*) FROM pg_namespace WHERE nspname IN ('core','sleeper','memory','reporting')",
    ).decode().strip()
    if populated != "0":
        raise ValueError("restore requires an empty fresh target; never resets schemas")
    with source.open("rb") as stream:
        result = subprocess.run(
            ["docker", "exec", "-i", target.name, "pg_restore", "-U", "postgres", "-d", target.database, "--exit-on-error"],
            stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    if result.returncode:
        raise RuntimeError("database restore failed: " + result.stderr.decode(errors="replace"))
