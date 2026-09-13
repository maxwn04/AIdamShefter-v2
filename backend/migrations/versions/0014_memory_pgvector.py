"""Use pgvector for exact semantic search, preserving existing derived rows.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extension installation requires the provisioning administrator, not the
    # application migration/runtime roles. Never change that privilege boundary.
    op.execute("""
        DO $aida$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_catalog.pg_extension AS extension
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = extension.extnamespace
                WHERE extension.extname = 'vector' AND namespace.nspname = 'public'
            ) THEN
                RAISE EXCEPTION 'Provision pgvector in public before migration 0014 using infra/database/bootstrap_extensions.sql';
            END IF;
            IF pg_catalog.to_regprocedure('public.vector_norm(public.vector)') IS NULL
               OR pg_catalog.to_regprocedure('public.cosine_distance(public.vector,public.vector)') IS NULL THEN
                RAISE EXCEPTION 'An administrator must upgrade pgvector to provide vector_norm and cosine_distance before migration 0014';
            END IF;
        END
        $aida$
    """)
    op.drop_constraint(
        op.f("ck_memory_search_embeddings_embedding_dimensions"), "memory_search_embeddings",
        schema="memory", type_="check",
    )
    # pgvector uses finite float32 values. An incompatible legacy vector makes
    # this transaction fail without deleting data; repair its derived index
    # explicitly before retrying. Compatible rows and their identity survive.
    op.execute("""
        ALTER TABLE memory.memory_search_embeddings
        ALTER COLUMN embedding TYPE public.vector USING embedding::public.vector
    """)
    op.create_check_constraint(
        "embedding_dimensions", "memory_search_embeddings",
        "public.vector_dims(embedding) = dimensions", schema="memory",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_memory_search_embeddings_embedding_dimensions"), "memory_search_embeddings",
        schema="memory", type_="check",
    )
    op.execute("""
        ALTER TABLE memory.memory_search_embeddings
        ALTER COLUMN embedding TYPE double precision[]
        USING embedding::real[]::double precision[]
    """)
    op.create_check_constraint(
        "embedding_dimensions", "memory_search_embeddings",
        "cardinality(embedding) = dimensions", schema="memory",
    )
    # The provisioned extension may be shared by other consumers; leave it in place.
