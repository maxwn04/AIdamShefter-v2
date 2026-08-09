"""Create generation-centered reporting history.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GENERATION_TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")
_AI_CALL_TERMINAL_STATUSES = (
    "succeeded",
    "retryable_error",
    "fatal_error",
    "cancelled",
    "unknown_outcome",
)
_TOOL_CALL_TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")
_WORKSPACE_CLOSED_STATUSES = ("discarded", "promoted")


def _sql_statuses(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _create_reporting_history_triggers() -> None:
    op.execute(
        f"""
        CREATE FUNCTION reporting.protect_terminal_generation()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            IF OLD.status IN ({_sql_statuses(_GENERATION_TERMINAL_STATUSES)}) THEN
                RAISE EXCEPTION 'terminal generations are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER generations_protect_terminal
        BEFORE UPDATE OR DELETE ON reporting.generations
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_terminal_generation()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION reporting.protect_evaluation_workspace()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ({_sql_statuses(_WORKSPACE_CLOSED_STATUSES)}) THEN
                    RAISE EXCEPTION 'closed evaluation workspaces are immutable';
                END IF;
                RETURN OLD;
            END IF;
            IF ROW(NEW.competition_id, NEW.base_memory_revision_id, NEW.created_at)
               IS DISTINCT FROM
               ROW(OLD.competition_id, OLD.base_memory_revision_id, OLD.created_at) THEN
                RAISE EXCEPTION 'evaluation workspace identity and base are immutable';
            END IF;
            IF OLD.status IN ({_sql_statuses(_WORKSPACE_CLOSED_STATUSES)}) THEN
                RAISE EXCEPTION 'closed evaluation workspaces are immutable';
            END IF;
            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER evaluation_workspaces_protect_history
        BEFORE UPDATE OR DELETE ON reporting.evaluation_workspaces
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_evaluation_workspace()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION reporting.protect_workspace_generation_membership()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        DECLARE
            workspace_status text;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.evaluation_workspace_id IS NOT NULL THEN
                SELECT status INTO workspace_status
                FROM reporting.evaluation_workspaces
                WHERE id = OLD.evaluation_workspace_id;
                IF workspace_status IN ({_sql_statuses(_WORKSPACE_CLOSED_STATUSES)}) THEN
                    RAISE EXCEPTION 'closed workspace generation membership is immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            IF NEW.evaluation_workspace_id IS NOT NULL THEN
                SELECT status INTO workspace_status
                FROM reporting.evaluation_workspaces
                WHERE id = NEW.evaluation_workspace_id
                FOR UPDATE;
                IF workspace_status IN ({_sql_statuses(_WORKSPACE_CLOSED_STATUSES)}) THEN
                    RAISE EXCEPTION 'closed workspace generation membership is immutable';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER generations_protect_workspace_membership
        BEFORE INSERT OR UPDATE OR DELETE ON reporting.generations
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_workspace_generation_membership()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION reporting.protect_terminal_ai_call()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            IF OLD.status IN ({_sql_statuses(_AI_CALL_TERMINAL_STATUSES)}) THEN
                RAISE EXCEPTION 'terminal AI call records are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ai_calls_protect_terminal
        BEFORE UPDATE OR DELETE ON reporting.ai_calls
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_terminal_ai_call()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION reporting.protect_terminal_tool_call()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            IF OLD.status IN ({_sql_statuses(_TOOL_CALL_TERMINAL_STATUSES)}) THEN
                RAISE EXCEPTION 'terminal tool call records are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER tool_calls_protect_terminal
        BEFORE UPDATE OR DELETE ON reporting.tool_calls
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_terminal_tool_call()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reporting.protect_artifact_version()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            RAISE EXCEPTION 'artifact versions are append-only';
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifact_versions_append_only
        BEFORE UPDATE OR DELETE ON reporting.artifact_versions
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_artifact_version()
        """
    )


def _drop_reporting_history_triggers() -> None:
    op.execute("DROP FUNCTION reporting.protect_artifact_version() CASCADE")
    op.execute("DROP FUNCTION reporting.protect_terminal_tool_call() CASCADE")
    op.execute("DROP FUNCTION reporting.protect_terminal_ai_call() CASCADE")
    op.execute(
        "DROP FUNCTION reporting.protect_workspace_generation_membership() CASCADE"
    )
    op.execute("DROP FUNCTION reporting.protect_evaluation_workspace() CASCADE")
    op.execute("DROP FUNCTION reporting.protect_terminal_generation() CASCADE")


def upgrade() -> None:
    op.create_table('evaluation_workspaces',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('base_memory_revision_id', sa.UUID(), nullable=False),
    sa.Column('current_memory_artifact_version_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('promoted_memory_revision_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['base_memory_revision_id', 'competition_id'], ['memory.memory_revisions.id', 'memory.memory_revisions.competition_id'], name='fk_evaluation_workspaces_base_same_competition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['competition_id'], ['core.competitions.id'], name=op.f('fk_evaluation_workspaces_competition_id_competitions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['promoted_memory_revision_id', 'competition_id'], ['memory.memory_revisions.id', 'memory.memory_revisions.competition_id'], name='fk_evaluation_workspaces_promoted_same_competition', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_workspaces')),
    sa.UniqueConstraint('id', 'competition_id', name='uq_evaluation_workspaces_id_competition'),
    schema='reporting'
    )
    op.create_index('ix_evaluation_workspaces_base_revision', 'evaluation_workspaces', ['base_memory_revision_id'], unique=False, schema='reporting')
    op.create_index('ix_evaluation_workspaces_competition_status', 'evaluation_workspaces', ['competition_id', 'status'], unique=False, schema='reporting')
    op.create_index('uq_evaluation_workspaces_one_active', 'evaluation_workspaces', ['competition_id'], unique=True, schema='reporting', postgresql_where=sa.text("status = 'active'"))
    op.create_table('generations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('data_snapshot_id', sa.UUID(), nullable=True),
    sa.Column('input_memory_revision_id', sa.UUID(), nullable=True),
    sa.Column('input_memory_artifact_version_id', sa.UUID(), nullable=True),
    sa.Column('evaluation_workspace_id', sa.UUID(), nullable=True),
    sa.Column('workspace_sequence_number', sa.BigInteger(), nullable=True),
    sa.Column('rerun_of_generation_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('request_text', sa.Text(), nullable=False),
    sa.Column('week_start', sa.SmallInteger(), nullable=True),
    sa.Column('week_end', sa.SmallInteger(), nullable=True),
    sa.Column('domain_cutoff_week', sa.SmallInteger(), nullable=True),
    sa.Column('domain_cutoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('knowledge_cutoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requested_primary_model', sa.Text(), nullable=False),
    sa.Column('settings_jsonb', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('input_manifest_jsonb', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('manifest_schema_version', sa.SmallInteger(), nullable=True),
    sa.Column('manifest_hash', sa.Text(), nullable=True),
    sa.Column('current_turn', sa.BigInteger(), nullable=False),
    sa.Column('current_stage', sa.Text(), nullable=True),
    sa.Column('progress_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_category', sa.Text(), nullable=True),
    sa.Column('failure_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('(evaluation_workspace_id IS NULL AND workspace_sequence_number IS NULL) OR (evaluation_workspace_id IS NOT NULL AND workspace_sequence_number IS NOT NULL)', name=op.f('ck_generations_workspace_shape')),
    sa.CheckConstraint('num_nonnulls(input_memory_revision_id, input_memory_artifact_version_id) <= 1', name=op.f('ck_generations_unambiguous_memory_input')),
    sa.ForeignKeyConstraint(['competition_id'], ['core.competitions.id'], name=op.f('fk_generations_competition_id_competitions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['competition_season_id', 'competition_id'], ['core.competition_seasons.id', 'core.competition_seasons.competition_id'], name='fk_generations_season_same_competition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['data_snapshot_id', 'competition_id'], ['sleeper.data_snapshots.id', 'sleeper.data_snapshots.competition_id'], name='fk_generations_snapshot_same_competition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['evaluation_workspace_id', 'competition_id'], ['reporting.evaluation_workspaces.id', 'reporting.evaluation_workspaces.competition_id'], name='fk_generations_workspace_same_competition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['input_memory_revision_id', 'competition_id'], ['memory.memory_revisions.id', 'memory.memory_revisions.competition_id'], name='fk_generations_memory_revision_same_competition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rerun_of_generation_id', 'competition_id'], ['reporting.generations.id', 'reporting.generations.competition_id'], name='fk_generations_rerun_same_competition', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_generations')),
    sa.UniqueConstraint('evaluation_workspace_id', 'workspace_sequence_number', name='uq_generations_workspace_sequence'),
    sa.UniqueConstraint('id', 'competition_id', name='uq_generations_id_competition'),
    schema='reporting'
    )
    op.create_index('ix_generations_competition_created', 'generations', ['competition_id', sa.literal_column('created_at DESC')], unique=False, schema='reporting')
    op.create_index('ix_generations_competition_season', 'generations', ['competition_season_id'], unique=False, schema='reporting')
    op.create_index('ix_generations_data_snapshot', 'generations', ['data_snapshot_id'], unique=False, schema='reporting')
    op.create_index('ix_generations_memory_revision', 'generations', ['input_memory_revision_id'], unique=False, schema='reporting')
    op.create_index('ix_generations_requested_model', 'generations', ['requested_primary_model'], unique=False, schema='reporting')
    op.create_index('ix_generations_status_progress', 'generations', ['status', 'progress_updated_at'], unique=False, schema='reporting')
    op.create_index('ix_generations_workspace_sequence', 'generations', ['evaluation_workspace_id', 'workspace_sequence_number'], unique=False, schema='reporting')
    op.create_table('ai_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('generation_id', sa.UUID(), nullable=False),
    sa.Column('turn_number', sa.BigInteger(), nullable=False),
    sa.Column('attempt_number', sa.SmallInteger(), nullable=False),
    sa.Column('requested_provider', sa.Text(), nullable=True),
    sa.Column('requested_model', sa.Text(), nullable=False),
    sa.Column('actual_provider', sa.Text(), nullable=True),
    sa.Column('actual_model', sa.Text(), nullable=True),
    sa.Column('input_messages', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('tool_definitions', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('request_parameters', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('provider_response', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_jsonb', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('finish_reason', sa.Text(), nullable=True),
    sa.Column('provider_request_id', sa.Text(), nullable=True),
    sa.Column('provider_response_id', sa.Text(), nullable=True),
    sa.Column('input_tokens', sa.BigInteger(), nullable=True),
    sa.Column('cached_input_tokens', sa.BigInteger(), nullable=True),
    sa.Column('output_tokens', sa.BigInteger(), nullable=True),
    sa.Column('reasoning_tokens', sa.BigInteger(), nullable=True),
    sa.Column('total_tokens', sa.BigInteger(), nullable=True),
    sa.Column('raw_provider_usage', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('latency_ms', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['reporting.generations.id'], name=op.f('fk_ai_calls_generation_id_generations'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_calls')),
    sa.UniqueConstraint('generation_id', 'turn_number', 'attempt_number', name='uq_ai_calls_generation_turn_attempt'),
    sa.UniqueConstraint('id', 'generation_id', name='uq_ai_calls_id_generation'),
    schema='reporting'
    )
    op.create_index('ix_ai_calls_actual_model_completed', 'ai_calls', ['actual_model', 'completed_at'], unique=False, schema='reporting')
    op.create_index('ix_ai_calls_generation_turn_attempt', 'ai_calls', ['generation_id', 'turn_number', 'attempt_number'], unique=False, schema='reporting')
    op.create_index('uq_ai_calls_one_success_per_turn', 'ai_calls', ['generation_id', 'turn_number'], unique=True, schema='reporting', postgresql_where=sa.text("status = 'succeeded'"))
    op.create_table('tool_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('generation_id', sa.UUID(), nullable=False),
    sa.Column('ai_call_id', sa.UUID(), nullable=False),
    sa.Column('tool_ordinal', sa.SmallInteger(), nullable=False),
    sa.Column('provider_tool_call_id', sa.Text(), nullable=True),
    sa.Column('tool_name', sa.Text(), nullable=False),
    sa.Column('implementation_version', sa.Text(), nullable=False),
    sa.Column('arguments_jsonb', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('full_result_text', sa.Text(), nullable=True),
    sa.Column('structured_result_jsonb', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('error_text', sa.Text(), nullable=True),
    sa.Column('error_jsonb', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['ai_call_id', 'generation_id'], ['reporting.ai_calls.id', 'reporting.ai_calls.generation_id'], name='fk_tool_calls_ai_call_same_generation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['generation_id'], ['reporting.generations.id'], name=op.f('fk_tool_calls_generation_id_generations'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tool_calls')),
    sa.UniqueConstraint('ai_call_id', 'tool_ordinal', name='uq_tool_calls_ai_call_ordinal'),
    sa.UniqueConstraint('id', 'generation_id', name='uq_tool_calls_id_generation'),
    schema='reporting'
    )
    op.create_index('ix_tool_calls_generation_ai_ordinal', 'tool_calls', ['generation_id', 'ai_call_id', 'tool_ordinal'], unique=False, schema='reporting')
    op.create_index('ix_tool_calls_name_started', 'tool_calls', ['tool_name', 'started_at'], unique=False, schema='reporting')
    op.create_table('artifacts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('generation_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('format', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['reporting.generations.id'], name=op.f('fk_artifacts_generation_id_generations'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifacts')),
    sa.UniqueConstraint('generation_id', 'kind', 'name', name='uq_artifacts_generation_kind_name'),
    sa.UniqueConstraint('id', 'generation_id', name='uq_artifacts_id_generation'),
    schema='reporting'
    )
    op.create_index('ix_artifacts_generation_kind', 'artifacts', ['generation_id', 'kind'], unique=False, schema='reporting')
    op.create_table('artifact_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('artifact_id', sa.UUID(), nullable=False),
    sa.Column('generation_id', sa.UUID(), nullable=False),
    sa.Column('revision_number', sa.SmallInteger(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('source_ai_call_id', sa.UUID(), nullable=True),
    sa.Column('source_tool_call_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['artifact_id', 'generation_id'], ['reporting.artifacts.id', 'reporting.artifacts.generation_id'], name='fk_artifact_versions_artifact_same_generation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_ai_call_id', 'generation_id'], ['reporting.ai_calls.id', 'reporting.ai_calls.generation_id'], name='fk_artifact_versions_ai_call_same_generation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_tool_call_id', 'generation_id'], ['reporting.tool_calls.id', 'reporting.tool_calls.generation_id'], name='fk_artifact_versions_tool_call_same_generation', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifact_versions')),
    sa.UniqueConstraint('artifact_id', 'revision_number', name='uq_artifact_versions_artifact_revision'),
    sa.UniqueConstraint('id', 'generation_id', name='uq_artifact_versions_id_generation'),
    schema='reporting'
    )
    op.create_index('ix_artifact_versions_artifact_revision_desc', 'artifact_versions', ['artifact_id', sa.literal_column('revision_number DESC')], unique=False, schema='reporting')
    op.create_index('ix_artifact_versions_final', 'artifact_versions', ['artifact_id'], unique=False, schema='reporting', postgresql_where=sa.text("status = 'final'"))
    op.create_index('uq_artifact_versions_one_final', 'artifact_versions', ['artifact_id'], unique=True, schema='reporting', postgresql_where=sa.text("status = 'final'"))
    _create_reporting_history_triggers()


def downgrade() -> None:
    _drop_reporting_history_triggers()
    op.drop_index('uq_artifact_versions_one_final', table_name='artifact_versions', schema='reporting', postgresql_where=sa.text("status = 'final'"))
    op.drop_index('ix_artifact_versions_final', table_name='artifact_versions', schema='reporting', postgresql_where=sa.text("status = 'final'"))
    op.drop_index('ix_artifact_versions_artifact_revision_desc', table_name='artifact_versions', schema='reporting')
    op.drop_table('artifact_versions', schema='reporting')
    op.drop_index('ix_artifacts_generation_kind', table_name='artifacts', schema='reporting')
    op.drop_table('artifacts', schema='reporting')
    op.drop_index('ix_tool_calls_name_started', table_name='tool_calls', schema='reporting')
    op.drop_index('ix_tool_calls_generation_ai_ordinal', table_name='tool_calls', schema='reporting')
    op.drop_table('tool_calls', schema='reporting')
    op.drop_index('uq_ai_calls_one_success_per_turn', table_name='ai_calls', schema='reporting', postgresql_where=sa.text("status = 'succeeded'"))
    op.drop_index('ix_ai_calls_generation_turn_attempt', table_name='ai_calls', schema='reporting')
    op.drop_index('ix_ai_calls_actual_model_completed', table_name='ai_calls', schema='reporting')
    op.drop_table('ai_calls', schema='reporting')
    op.drop_index('ix_generations_workspace_sequence', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_status_progress', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_requested_model', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_memory_revision', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_data_snapshot', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_competition_season', table_name='generations', schema='reporting')
    op.drop_index('ix_generations_competition_created', table_name='generations', schema='reporting')
    op.drop_table('generations', schema='reporting')
    op.drop_index('uq_evaluation_workspaces_one_active', table_name='evaluation_workspaces', schema='reporting', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('ix_evaluation_workspaces_competition_status', table_name='evaluation_workspaces', schema='reporting')
    op.drop_index('ix_evaluation_workspaces_base_revision', table_name='evaluation_workspaces', schema='reporting')
    op.drop_table('evaluation_workspaces', schema='reporting')
