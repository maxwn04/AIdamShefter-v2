"""Verify hosted database identity, TLS, roles, grants, and migration state."""

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, cast

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from backend.database.base import APPLICATION_SCHEMAS
from backend.database.health import assert_database_ready, read_database_health
from infra.database.common import create_verified_engine

_DATA_API_ROLES = ("anon", "authenticated", "service_role")
UrlEnvironment = Literal[
    "AIDAM_MIGRATION_DATABASE_URL",
    "AIDAM_DATABASE_URL",
    "AIDAM_WORKER_DATABASE_URL",
]
VerificationProfile = Literal["migrator", "runtime"]


@dataclass(frozen=True, slots=True)
class VerificationArguments:
    url_environment: UrlEnvironment
    expected_database: str
    expected_role: str
    profile: VerificationProfile


def _arguments() -> VerificationArguments:
    parser = ArgumentParser()
    _ = parser.add_argument(
        "--url-environment",
        choices=(
            "AIDAM_MIGRATION_DATABASE_URL",
            "AIDAM_DATABASE_URL",
            "AIDAM_WORKER_DATABASE_URL",
        ),
        required=True,
    )
    _ = parser.add_argument("--expected-database", required=True)
    _ = parser.add_argument(
        "--expected-role",
        choices=("aidam_migrator", "aidam_api", "aidam_worker"),
        required=True,
    )
    _ = parser.add_argument(
        "--profile",
        choices=("migrator", "runtime"),
        required=True,
    )
    parsed: Namespace = parser.parse_args()
    return VerificationArguments(
        url_environment=cast(UrlEnvironment, parsed.url_environment),
        expected_database=cast(str, parsed.expected_database),
        expected_role=cast(str, parsed.expected_role),
        profile=cast(VerificationProfile, parsed.profile),
    )


def _expected_head() -> str:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "backend" / "migrations" / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected one Alembic head, found {len(heads)}")
    return heads[0]


def _verify_common(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        schema_rows = connection.execute(
            text(
                """
                SELECT nspname, pg_catalog.pg_get_userbyid(nspowner) AS owner
                FROM pg_catalog.pg_namespace
                WHERE nspname = ANY(:schemas)
                ORDER BY nspname
                """
            ),
            {"schemas": list(APPLICATION_SCHEMAS)},
        ).mappings()
        schema_owners = {
            cast(str, row["nspname"]): cast(str, row["owner"])
            for row in schema_rows
        }
        if set(schema_owners) != set(APPLICATION_SCHEMAS):
            raise RuntimeError("one or more private application schemas are missing")
        if set(schema_owners.values()) != {"aidam_owner"}:
            raise RuntimeError("private application schema ownership is incorrect")

        search_path = cast(
            str,
            connection.execute(text("SHOW search_path")).scalar_one(),
        )
        if search_path.replace(" ", "") != "pg_catalog":
            raise RuntimeError("database role search_path is not restricted")

        public_create = cast(
            bool,
            connection.execute(
                text("SELECT has_schema_privilege('public', 'public', 'CREATE')")
            ).scalar_one(),
        )
        if public_create:
            raise RuntimeError("PUBLIC retains CREATE on schema public")

        invalid_indexes = cast(
            int,
            connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM pg_catalog.pg_index AS index_state
                    JOIN pg_catalog.pg_class AS relation
                      ON relation.oid = index_state.indexrelid
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = ANY(:schemas)
                      AND NOT index_state.indisvalid
                    """
                ),
                {"schemas": list(APPLICATION_SCHEMAS)},
            ).scalar_one(),
        )
        if invalid_indexes:
            raise RuntimeError("invalid application indexes exist")

        data_api_access: dict[str, list[str]] = {}
        for role in _DATA_API_ROLES:
            role_exists = cast(
                bool,
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_catalog.pg_roles
                            WHERE rolname = :role
                        )
                        """
                    ),
                    {"role": role},
                ).scalar_one(),
            )
            if not role_exists:
                continue
            visible = [
                schema
                for schema in APPLICATION_SCHEMAS
                if cast(
                    bool,
                    connection.execute(
                        text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"),
                        {"role": role, "schema": schema},
                    ).scalar_one(),
                )
            ]
            if visible:
                raise RuntimeError(f"Data API role {role} can use private schemas")
            data_api_access[role] = visible

    return {
        "application_schemas": sorted(schema_owners),
        "data_api_schema_access": data_api_access,
        "invalid_index_count": invalid_indexes,
        "search_path": search_path,
    }


def _verify_profile(engine: Engine, profile: str, expected_role: str) -> None:
    with engine.connect() as connection:
        if profile == "migrator":
            owner_member = cast(
                bool,
                connection.execute(
                    text(
                        """
                        SELECT pg_catalog.pg_has_role(
                            :role, 'aidam_owner', 'MEMBER'
                        )
                        """
                    ),
                    {"role": expected_role},
                ).scalar_one(),
            )
            if not owner_member:
                raise RuntimeError("migrator cannot SET ROLE aidam_owner")
            return

        with connection.begin():
            for schema in APPLICATION_SCHEMAS:
                privileges = connection.execute(
                    text(
                        """
                        SELECT
                            has_schema_privilege(:schema, 'USAGE') AS can_use,
                            has_schema_privilege(:schema, 'CREATE') AS can_create
                        """
                    ),
                    {"schema": schema},
                ).mappings().one()
                if not cast(bool, privileges["can_use"]) or cast(
                    bool, privileges["can_create"]
                ):
                    raise RuntimeError("runtime schema privileges are incorrect")


def main() -> None:
    arguments = _arguments()
    engine = create_verified_engine(
        arguments.url_environment,
        f"aidam-verify-{arguments.profile}",
    )
    try:
        verifies_revision = arguments.profile == "migrator"
        health = read_database_health(
            engine,
            include_migration_revision=verifies_revision,
        )
        expected_head = _expected_head() if verifies_revision else None
        assert_database_ready(
            health,
            expected_database=arguments.expected_database,
            expected_role=arguments.expected_role,
            expected_revision=expected_head,
            require_tls=True,
        )
        report = _verify_common(engine)
        _verify_profile(engine, arguments.profile, arguments.expected_role)
        report.update(
            {
                "database": health.database,
                "migration_revision_checked": verifies_revision,
                "role": health.role,
                "server_version": health.server_version,
                "tls": health.tls,
                "verified": True,
            }
        )
        if verifies_revision:
            report["alembic_revision"] = health.alembic_revision
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
