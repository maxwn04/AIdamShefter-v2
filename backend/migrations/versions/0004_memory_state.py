"""Create linear canonical reporter memory.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_history_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION memory.reject_sealed_history_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            RAISE EXCEPTION 'sealed canonical memory history is immutable';
        END;
        $aida$
        """
    )
    immutable_tables = (
        "memory_revisions",
        "memory_items",
        "storyline_versions",
        "fact_versions",
        "event_versions",
        "trigger_versions",
        "context_notes",
        "context_note_versions",
    )
    for table_name in immutable_tables:
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_reject_mutation
            BEFORE UPDATE OR DELETE ON memory.{table_name}
            FOR EACH ROW EXECUTE FUNCTION memory.reject_sealed_history_mutation()
            """
        )

    op.execute(
        """
        CREATE FUNCTION memory.protect_memory_version()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'canonical memory versions cannot be deleted';
            END IF;
            IF (to_jsonb(NEW) - 'retired_revision_id') IS DISTINCT FROM
               (to_jsonb(OLD) - 'retired_revision_id') THEN
                RAISE EXCEPTION 'canonical memory version content is immutable';
            END IF;
            IF OLD.retired_revision_id IS NOT NULL
               AND NEW.retired_revision_id IS DISTINCT FROM OLD.retired_revision_id THEN
                RAISE EXCEPTION 'a retired memory version cannot be changed';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_protect_history
        BEFORE UPDATE OR DELETE ON memory.memory_versions
        FOR EACH ROW EXECUTE FUNCTION memory.protect_memory_version()
        """
    )

    op.execute(
        """
        CREATE FUNCTION memory.protect_current_revision()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'the canonical current revision pointer cannot be deleted';
            END IF;
            IF NEW.competition_id IS DISTINCT FROM OLD.competition_id THEN
                RAISE EXCEPTION 'the canonical current revision scope is immutable';
            END IF;
            IF NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id THEN
                IF NEW.lock_version <> OLD.lock_version + 1 THEN
                    RAISE EXCEPTION 'advancing canonical memory must increment lock_version once';
                END IF;
            ELSIF NEW.lock_version IS DISTINCT FROM OLD.lock_version THEN
                RAISE EXCEPTION 'lock_version may change only with the current revision';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER current_revisions_protect_concurrency
        BEFORE UPDATE OR DELETE ON memory.current_revisions
        FOR EACH ROW EXECUTE FUNCTION memory.protect_current_revision()
        """
    )


def upgrade() -> None:
    op.create_table(
        "memory_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column(
            "previous_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Reporting provenance and promotion FKs are added in revision 0006.
        sa.Column(
            "producing_generation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("week", sa.SmallInteger(), nullable=True),
        sa.Column("knowledge_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_content_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_memory_revisions_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_revisions_previous_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_memory_revisions_season_same_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_revisions"),
        sa.UniqueConstraint(
            "competition_id",
            "sequence_number",
            name="uq_memory_revisions_competition_sequence",
        ),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_memory_revisions_id_competition",
        ),
        sa.UniqueConstraint(
            "producing_generation_id",
            name="uq_memory_revisions_producing_generation",
        ),
        schema="memory",
    )
    op.create_index(
        "ix_memory_revisions_competition_sequence_desc",
        "memory_revisions",
        ["competition_id", sa.text("sequence_number DESC")],
        schema="memory",
    )
    op.create_index(
        "ix_memory_revisions_previous_competition",
        "memory_revisions",
        ["previous_revision_id", "competition_id"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_revisions_season_competition",
        "memory_revisions",
        ["competition_season_id", "competition_id"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_revisions_producing_generation",
        "memory_revisions",
        ["producing_generation_id"],
        schema="memory",
    )

    op.create_table(
        "current_revisions",
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "current_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("lock_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_current_revisions_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_current_revisions_revision_same_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("competition_id", name="pk_current_revisions"),
        schema="memory",
    )
    op.create_index(
        "ix_current_revisions_revision_competition",
        "current_revisions",
        ["current_revision_id", "competition_id"],
        schema="memory",
    )

    op.create_table(
        "memory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("agent_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_memory_items_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_items"),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_memory_items_id_competition",
        ),
        schema="memory",
    )
    op.create_index(
        "ix_memory_items_competition_kind",
        "memory_items",
        ["competition_id", "kind"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_items_competition_agent_key",
        "memory_items",
        ["competition_id", "agent_key"],
        schema="memory",
    )

    op.create_table(
        "memory_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.SmallInteger(), nullable=False),
        sa.Column(
            "content_schema_version",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "introduced_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "retired_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("week", sa.SmallInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        # Reporting generation/tool-call scope FKs are added in revision 0006.
        sa.Column(
            "creating_generation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "creating_tool_call_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "competition_id"],
            ["memory.memory_items.id", "memory.memory_items.competition_id"],
            name="fk_memory_versions_item_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["introduced_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_introduced_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retired_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_retired_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_memory_versions_season_same_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_versions"),
        sa.UniqueConstraint(
            "item_id",
            "revision_number",
            name="uq_memory_versions_item_revision",
        ),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_memory_versions_id_competition",
        ),
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_item_revision",
        "memory_versions",
        ["item_id", "revision_number"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_introduced_revision",
        "memory_versions",
        ["introduced_revision_id"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_retired_revision",
        "memory_versions",
        ["retired_revision_id"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_creating_generation",
        "memory_versions",
        ["creating_generation_id"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_competition_season_week",
        "memory_versions",
        ["competition_id", "competition_season_id", "week"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_versions_season_competition",
        "memory_versions",
        ["competition_season_id", "competition_id"],
        schema="memory",
    )

    op.create_table(
        "storyline_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("arc_type", sa.Text(), nullable=True),
        sa.Column("salience", sa.SmallInteger(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "subjects",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "related_storylines",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("callback_condition", sa.Text(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["memory.memory_versions.id"],
            name="fk_storyline_versions_version_id_memory_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_storyline_versions"),
        schema="memory",
    )
    op.create_table(
        "fact_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("structured_numbers", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column(
            "subjects",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "originating_event_version_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        # The reporting tool-call FK is added in revision 0006.
        sa.Column(
            "primary_tool_call_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "primary_api_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("additional_source_hints", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["memory.memory_versions.id"],
            name="fk_fact_versions_version_id_memory_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_api_request_id"],
            ["sleeper.api_requests.id"],
            name="fk_fact_versions_primary_api_request_id_api_requests",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_fact_versions"),
        schema="memory",
    )
    op.create_index(
        "ix_fact_versions_primary_tool_call",
        "fact_versions",
        ["primary_tool_call_id"],
        schema="memory",
    )
    op.create_index(
        "ix_fact_versions_primary_api_request",
        "fact_versions",
        ["primary_api_request_id"],
        schema="memory",
    )
    op.create_table(
        "event_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("salience", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("additional_source_hints", postgresql.JSONB(), nullable=True),
        # The reporting tool-call FK is added in revision 0006.
        sa.Column(
            "primary_tool_call_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "primary_api_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["memory.memory_versions.id"],
            name="fk_event_versions_version_id_memory_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_api_request_id"],
            ["sleeper.api_requests.id"],
            name="fk_event_versions_primary_api_request_id_api_requests",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_event_versions"),
        schema="memory",
    )
    op.create_index(
        "ix_event_versions_primary_tool_call",
        "event_versions",
        ["primary_tool_call_id"],
        schema="memory",
    )
    op.create_index(
        "ix_event_versions_primary_api_request",
        "event_versions",
        ["primary_api_request_id"],
        schema="memory",
    )
    op.create_table(
        "trigger_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("fire_policy", sa.Text(), nullable=False),
        sa.Column(
            "target_competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "target_storyline_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "origin_event_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("target_week", sa.SmallInteger(), nullable=True),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_trigger_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_trigger_versions_target_same_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_trigger_versions"),
        schema="memory",
    )
    op.create_index(
        "ix_trigger_versions_target_season_competition",
        "trigger_versions",
        ["target_competition_season_id", "competition_id"],
        schema="memory",
    )

    op.create_table(
        "context_notes",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("franchise_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note_key", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(scope = 'competition' AND competition_season_id IS NULL AND "
            "franchise_id IS NULL) OR "
            "(scope = 'competition_season' AND competition_season_id IS NOT NULL "
            "AND franchise_id IS NULL) OR "
            "(scope = 'franchise' AND competition_season_id IS NULL AND "
            "franchise_id IS NOT NULL)",
            name=op.f("ck_context_notes_scope_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "competition_id"],
            ["memory.memory_items.id", "memory.memory_items.competition_id"],
            name="fk_context_notes_item_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_context_notes_season_same_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_context_notes_franchise_same_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("item_id", name="pk_context_notes"),
        sa.UniqueConstraint(
            "item_id",
            "competition_id",
            name="uq_context_notes_item_competition",
        ),
        schema="memory",
    )
    op.create_index(
        "uq_context_notes_competition_key",
        "context_notes",
        ["competition_id", "note_key"],
        unique=True,
        postgresql_where=sa.text("scope = 'competition'"),
        schema="memory",
    )
    op.create_index(
        "uq_context_notes_season_key",
        "context_notes",
        ["competition_season_id", "note_key"],
        unique=True,
        postgresql_where=sa.text("scope = 'competition_season'"),
        schema="memory",
    )
    op.create_index(
        "uq_context_notes_franchise_key",
        "context_notes",
        ["franchise_id", "note_key"],
        unique=True,
        postgresql_where=sa.text("scope = 'franchise'"),
        schema="memory",
    )

    op.create_table(
        "context_note_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("narrative_text", sa.Text(), nullable=False),
        sa.Column("outlook", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["memory.memory_versions.id"],
            name="fk_context_note_versions_version_id_memory_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_context_note_versions"),
        schema="memory",
    )
    op.create_table(
        "memory_search_documents",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("salience", sa.SmallInteger(), nullable=True),
        sa.Column(
            "competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("week", sa.SmallInteger(), nullable=True),
        sa.Column(
            "entity_keys",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "evidence_version_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "related_item_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("document_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', document_text)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("builder_version", sa.SmallInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["memory.memory_versions.id"],
            name="fk_memory_search_documents_version_id_memory_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "version_id",
            name="pk_memory_search_documents",
        ),
        schema="memory",
    )
    op.create_index(
        "ix_memory_search_documents_competition_kind_status",
        "memory_search_documents",
        ["competition_id", "kind", "status"],
        schema="memory",
    )
    op.create_index(
        "ix_memory_search_documents_item",
        "memory_search_documents",
        ["item_id"],
        schema="memory",
    )
    for index_name, column in (
        ("ix_memory_search_documents_entity_keys", "entity_keys"),
        ("ix_memory_search_documents_evidence_versions", "evidence_version_ids"),
        ("ix_memory_search_documents_related_items", "related_item_ids"),
        ("ix_memory_search_documents_tags", "tags"),
        ("ix_memory_search_documents_search_vector", "search_vector"),
    ):
        op.create_index(
            index_name,
            "memory_search_documents",
            [column],
            postgresql_using="gin",
            schema="memory",
        )

    _create_history_guards()


def downgrade() -> None:
    op.drop_table("memory_search_documents", schema="memory")
    op.drop_table("context_note_versions", schema="memory")
    op.drop_table("context_notes", schema="memory")
    op.drop_table("trigger_versions", schema="memory")
    op.drop_table("event_versions", schema="memory")
    op.drop_table("fact_versions", schema="memory")
    op.drop_table("storyline_versions", schema="memory")
    op.drop_table("memory_versions", schema="memory")
    op.drop_table("memory_items", schema="memory")
    op.drop_table("current_revisions", schema="memory")
    op.drop_table("memory_revisions", schema="memory")
    op.execute("DROP FUNCTION memory.protect_current_revision()")
    op.execute("DROP FUNCTION memory.protect_memory_version()")
    op.execute("DROP FUNCTION memory.reject_sealed_history_mutation()")
