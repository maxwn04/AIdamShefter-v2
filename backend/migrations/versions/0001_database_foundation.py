"""Create private application schemas and baseline grants.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DATA_API_ROLES = ("anon", "authenticated", "service_role")
_APPLICATION_SCHEMAS = ("core", "sleeper", "memory", "reporting")


def _alter_default_privileges(*, grant: bool, schema: str) -> None:
    action = "GRANT" if grant else "REVOKE"
    grantee_keyword = "TO" if grant else "FROM"
    op.execute(
        sa.text(
            " ".join(
                (
                    "ALTER DEFAULT PRIVILEGES FOR ROLE aidam_owner",
                    f"IN SCHEMA {schema}",
                    f"{action} SELECT, INSERT, UPDATE, DELETE ON TABLES",
                    f"{grantee_keyword} aidam_runtime",
                )
            )
        )
    )
    op.execute(
        sa.text(
            " ".join(
                (
                    "ALTER DEFAULT PRIVILEGES FOR ROLE aidam_owner",
                    f"IN SCHEMA {schema}",
                    f"{action} USAGE, SELECT ON SEQUENCES",
                    f"{grantee_keyword} aidam_runtime",
                )
            )
        )
    )


def _revoke_data_api_schema_access(schema: str) -> None:
    roles = ", ".join(f"'{role}'" for role in _DATA_API_ROLES)
    op.execute(
        sa.text(
            f"""
            DO $block$
            DECLARE role_name text;
            BEGIN
                FOREACH role_name IN ARRAY ARRAY[{roles}]
                LOOP
                    IF EXISTS (
                        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
                    ) THEN
                        EXECUTE format(
                            'REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM %I',
                            role_name
                        );
                    END IF;
                END LOOP;
            END
            $block$
            """
        )
    )


def _revoke_data_api_version_access() -> None:
    roles = ", ".join(f"'{role}'" for role in _DATA_API_ROLES)
    op.execute(
        sa.text(
            f"""
            DO $block$
            DECLARE role_name text;
            BEGIN
                FOREACH role_name IN ARRAY ARRAY[{roles}]
                LOOP
                    IF EXISTS (
                        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
                    ) THEN
                        EXECUTE format(
                            'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM %I',
                            role_name
                        );
                    END IF;
                END LOOP;
            END
            $block$
            """
        )
    )


def upgrade() -> None:
    for schema in _APPLICATION_SCHEMAS:
        op.execute(sa.schema.CreateSchema(schema))
        op.execute(sa.text(f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC"))
        op.execute(sa.text(f"GRANT USAGE ON SCHEMA {schema} TO aidam_runtime"))
        _revoke_data_api_schema_access(schema)
        _alter_default_privileges(grant=True, schema=schema)

    op.execute(sa.text("REVOKE ALL ON TABLE public.alembic_version FROM PUBLIC"))
    _revoke_data_api_version_access()


def downgrade() -> None:
    for schema in reversed(_APPLICATION_SCHEMAS):
        _alter_default_privileges(grant=False, schema=schema)
        op.execute(sa.schema.DropSchema(schema))
