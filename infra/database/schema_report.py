"""Emit a credential-free operational schema report as JSON."""

from argparse import ArgumentParser
import json
from typing import cast

from sqlalchemy import text

from backend.database.base import APPLICATION_SCHEMAS
from backend.database.health import read_database_health
from infra.database.common import create_verified_engine


def main() -> None:
    parser = ArgumentParser()
    _ = parser.add_argument(
        "--url-environment",
        choices=("AIDAM_MIGRATION_DATABASE_URL",),
        required=True,
    )
    arguments = parser.parse_args()
    url_environment = cast(str, arguments.url_environment)
    engine = create_verified_engine(url_environment, "aidam-schema-report")
    try:
        health = read_database_health(engine, include_migration_revision=True)
        with engine.connect() as connection:
            tables = connection.execute(
                text(
                    """
                    SELECT schemaname, count(*) AS table_count
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = ANY(:schemas)
                    GROUP BY schemaname
                    ORDER BY schemaname
                    """
                ),
                {"schemas": list(APPLICATION_SCHEMAS)},
            ).mappings()
            table_counts = {
                cast(str, row["schemaname"]): cast(int, row["table_count"])
                for row in tables
            }
            sizes = connection.execute(
                text(
                    """
                    SELECT namespace.nspname AS schema_name,
                           pg_catalog.sum(pg_catalog.pg_total_relation_size(relation.oid))
                               AS bytes
                    FROM pg_catalog.pg_class AS relation
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = ANY(:schemas)
                      AND relation.relkind IN ('r', 'm')
                    GROUP BY namespace.nspname
                    ORDER BY namespace.nspname
                    """
                ),
                {"schemas": list(APPLICATION_SCHEMAS)},
            ).mappings()
            schema_sizes = {
                cast(str, row["schema_name"]): cast(int, row["bytes"])
                for row in sizes
            }
            unvalidated_constraints = cast(
                int,
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_catalog.pg_constraint AS constraint_state
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = constraint_state.connamespace
                        WHERE namespace.nspname = ANY(:schemas)
                          AND NOT constraint_state.convalidated
                        """
                    ),
                    {"schemas": list(APPLICATION_SCHEMAS)},
                ).scalar_one(),
            )

        print(
            json.dumps(
                {
                    "alembic_revision": health.alembic_revision,
                    "database": health.database,
                    "schema_sizes_bytes": schema_sizes,
                    "server_version": health.server_version,
                    "table_counts": table_counts,
                    "tls": health.tls,
                    "unvalidated_constraint_count": unvalidated_constraints,
                },
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
