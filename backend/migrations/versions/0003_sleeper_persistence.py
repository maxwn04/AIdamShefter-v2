"""Create request-oriented Sleeper persistence and frozen snapshot metadata.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_sleeper_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_sealed_data_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshots cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status IN ('ready', 'expired') THEN
                IF NEW.status NOT IN ('ready', 'expired')
                   OR ROW(
                       NEW.competition_id, NEW.primary_competition_season_id, NEW.mode,
                       NEW.domain_cutoff_week, NEW.domain_cutoff_at,
                       NEW.knowledge_cutoff_at, NEW.materializer_version,
                       NEW.sqlite_schema_version, NEW.code_version,
                       NEW.completeness_warnings, NEW.selected_request_set_sha256,
                       NEW.sqlite_artifact_sha256, NEW.sqlite_artifact_byte_length,
                       NEW.sqlite_artifact_storage_key, NEW.created_at, NEW.completed_at
                   ) IS DISTINCT FROM ROW(
                       OLD.competition_id, OLD.primary_competition_season_id, OLD.mode,
                       OLD.domain_cutoff_week, OLD.domain_cutoff_at,
                       OLD.knowledge_cutoff_at, OLD.materializer_version,
                       OLD.sqlite_schema_version, OLD.code_version,
                       OLD.completeness_warnings, OLD.selected_request_set_sha256,
                       OLD.sqlite_artifact_sha256, OLD.sqlite_artifact_byte_length,
                       OLD.sqlite_artifact_storage_key, OLD.created_at, OLD.completed_at
                   ) THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshot meaning is immutable';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshots_protect_sealed
        BEFORE UPDATE OR DELETE ON sleeper.data_snapshots
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_sealed_data_snapshot()
        """
    )
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_snapshot_request_membership()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        DECLARE
            snapshot_status text;
            snapshot_season_id uuid;
            request_season_id uuid;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO snapshot_status
                FROM sleeper.data_snapshots
                WHERE id = OLD.data_snapshot_id;
                IF snapshot_status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            SELECT status, primary_competition_season_id
            INTO snapshot_status, snapshot_season_id
            FROM sleeper.data_snapshots
            WHERE id = NEW.data_snapshot_id
            FOR UPDATE;
            IF snapshot_status IN ('ready', 'expired') THEN
                RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
            END IF;

            SELECT competition_season_id INTO request_season_id
            FROM sleeper.api_requests
            WHERE id = NEW.api_request_id;
            IF request_season_id IS NOT NULL
               AND request_season_id <> snapshot_season_id THEN
                RAISE EXCEPTION 'snapshot request belongs to another competition season';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshot_requests_protect_membership
        BEFORE INSERT OR UPDATE OR DELETE ON sleeper.data_snapshot_requests
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_snapshot_request_membership()
        """
    )


def _drop_sleeper_triggers() -> None:
    op.execute(
        "DROP FUNCTION sleeper.protect_snapshot_request_membership() CASCADE"
    )
    op.execute("DROP FUNCTION sleeper.protect_sealed_data_snapshot() CASCADE")

def upgrade() -> None:
    op.create_table('refresh_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=True),
    sa.Column('competition_season_id', sa.UUID(), nullable=True),
    sa.Column('requested_through_week', sa.SmallInteger(), nullable=True),
    sa.Column('endpoint_scope', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('trigger_source', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('code_version', sa.Text(), nullable=False),
    sa.Column('normalizer_version', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_summary', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('request_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('succeeded_request_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('failed_request_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['competition_id'], ['core.competitions.id'], name=op.f('fk_refresh_runs_competition_id_competitions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['competition_season_id', 'competition_id'], ['core.competition_seasons.id', 'core.competition_seasons.competition_id'], name='fk_refresh_runs_season_competition', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_runs')),
    sa.UniqueConstraint('id', 'competition_season_id', name='uq_refresh_runs_id_competition_season'),
    schema='sleeper'
    )
    op.create_index('ix_refresh_runs_competition_started', 'refresh_runs', ['competition_id', sa.literal_column('started_at DESC')], unique=False, schema='sleeper')
    op.create_table('api_payloads',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('sha256_hash', sa.Text(), nullable=False),
    sa.Column('byte_length', sa.BigInteger(), nullable=False),
    sa.Column('media_type', sa.Text(), nullable=False),
    sa.Column('storage_kind', sa.Text(), nullable=False),
    sa.Column('inline_payload', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('object_storage_key', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(storage_kind = 'inline_json' AND inline_payload IS NOT NULL AND object_storage_key IS NULL) OR (storage_kind = 'object' AND inline_payload IS NULL AND object_storage_key IS NOT NULL)", name=op.f('ck_api_payloads_exactly_one_location')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_payloads')),
    sa.UniqueConstraint('id', 'sha256_hash', name='uq_api_payloads_id_hash'),
    sa.UniqueConstraint('sha256_hash', name='uq_api_payloads_sha256_hash'),
    schema='sleeper'
    )
    op.create_table('api_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('refresh_run_id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=True),
    sa.Column('endpoint_kind', sa.Text(), nullable=False),
    sa.Column('scope_key', sa.Text(), nullable=False),
    sa.Column('request_path', sa.Text(), nullable=False),
    sa.Column('request_parameters', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('week', sa.SmallInteger(), nullable=True),
    sa.Column('bracket_kind', sa.Text(), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latency_ms', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('error', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('is_complete', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('completeness_reason', sa.Text(), nullable=True),
    sa.Column('payload_id', sa.UUID(), nullable=True),
    sa.Column('response_sha256', sa.Text(), nullable=True),
    sa.Column('normalization_status', sa.Text(), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('normalizer_version', sa.Text(), nullable=True),
    sa.Column('normalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['competition_season_id'], ['core.competition_seasons.id'], name=op.f('fk_api_requests_competition_season_id_competition_seasons'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payload_id', 'response_sha256'], ['sleeper.api_payloads.id', 'sleeper.api_payloads.sha256_hash'], name='fk_api_requests_verified_payload', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['refresh_run_id', 'competition_season_id'], ['sleeper.refresh_runs.id', 'sleeper.refresh_runs.competition_season_id'], name='fk_api_requests_refresh_run_scope', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_requests')),
    sa.UniqueConstraint('id', 'competition_season_id', name='uq_api_requests_id_competition_season'),
    sa.UniqueConstraint('id', 'scope_key', 'response_sha256', name='uq_api_requests_id_scope_hash'),
    sa.UniqueConstraint('id', 'scope_key', name='uq_api_requests_id_scope'),
    schema='sleeper'
    )
    op.create_index('ix_api_requests_eligible_scope_completed', 'api_requests', ['scope_key', sa.literal_column('completed_at DESC')], unique=False, schema='sleeper', postgresql_where=sa.text("status = 'succeeded' AND is_complete"))
    op.create_index('ix_api_requests_refresh_run', 'api_requests', ['refresh_run_id'], unique=False, schema='sleeper')
    op.create_index('ix_api_requests_season_endpoint_week', 'api_requests', ['competition_season_id', 'endpoint_kind', 'week'], unique=False, schema='sleeper')
    op.create_table('normalized_scopes',
    sa.Column('scope_key', sa.Text(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.Column('response_sha256', sa.Text(), nullable=False),
    sa.Column('normalized_row_count', sa.Integer(), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_api_request_id', 'scope_key', 'response_sha256'], ['sleeper.api_requests.id', 'sleeper.api_requests.scope_key', 'sleeper.api_requests.response_sha256'], name='fk_normalized_scopes_request_scope_hash', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('scope_key', name=op.f('pk_normalized_scopes')),
    sa.UniqueConstraint('source_api_request_id', name='uq_normalized_scopes_source_request'),
    schema='sleeper'
    )
    op.create_table('leagues',
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=True),
    sa.Column('season', sa.Text(), nullable=False),
    sa.Column('previous_sleeper_league_id', sa.Text(), nullable=True),
    sa.Column('sleeper_draft_id', sa.Text(), nullable=True),
    sa.Column('sport', sa.Text(), server_default=sa.text("'nfl'"), nullable=False),
    sa.Column('scoring_settings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('roster_positions', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('provider_settings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('playoff_start_week', sa.SmallInteger(), nullable=True),
    sa.Column('playoff_team_count', sa.SmallInteger(), nullable=True),
    sa.Column('league_average_match', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['competition_season_id'], ['core.competition_seasons.id'], name=op.f('fk_leagues_competition_season_id_competition_seasons'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_leagues_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('competition_season_id', name=op.f('pk_leagues')),
    schema='sleeper'
    )
    op.create_index('ix_leagues_source_request', 'leagues', ['source_api_request_id'], unique=False, schema='sleeper')
    op.create_table('users',
    sa.Column('sleeper_user_id', sa.Text(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('username', sa.Text(), nullable=True),
    sa.Column('avatar', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_users_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('sleeper_user_id', name=op.f('pk_users')),
    schema='sleeper'
    )
    op.create_index('ix_users_display_name_lower', 'users', [sa.literal_column('lower(display_name)')], unique=False, schema='sleeper')
    op.create_table('league_users',
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_user_id', sa.Text(), nullable=False),
    sa.Column('team_name', sa.Text(), nullable=True),
    sa.Column('nickname', sa.Text(), nullable=True),
    sa.Column('is_commissioner', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['competition_season_id'], ['core.competition_seasons.id'], name=op.f('fk_league_users_competition_season_id_competition_seasons'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sleeper_user_id'], ['sleeper.users.sleeper_user_id'], name=op.f('fk_league_users_sleeper_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_league_users_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('competition_season_id', 'sleeper_user_id', name=op.f('pk_league_users')),
    schema='sleeper'
    )
    op.create_index('ix_league_users_user', 'league_users', ['sleeper_user_id'], unique=False, schema='sleeper')
    op.create_table('players',
    sa.Column('sleeper_player_id', sa.Text(), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=True),
    sa.Column('position', sa.Text(), nullable=True),
    sa.Column('nfl_team', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('status', sa.Text(), nullable=True),
    sa.Column('injury_status', sa.Text(), nullable=True),
    sa.Column('age', sa.SmallInteger(), nullable=True),
    sa.Column('years_experience', sa.SmallInteger(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_players_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('sleeper_player_id', name=op.f('pk_players')),
    schema='sleeper'
    )
    op.create_index('ix_players_full_name_lower', 'players', [sa.literal_column('lower(full_name)')], unique=False, schema='sleeper')
    op.create_index('ix_players_team_position', 'players', ['nfl_team', 'position'], unique=False, schema='sleeper')
    op.create_table('rosters',
    sa.Column('season_roster_id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('record_string', sa.Text(), nullable=True),
    sa.Column('wins', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('losses', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('ties', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('points_for', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('points_against', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_rosters_season_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_rosters_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('season_roster_id', name=op.f('pk_rosters')),
    schema='sleeper'
    )
    op.create_index('ix_rosters_competition_season', 'rosters', ['competition_season_id'], unique=False, schema='sleeper')
    op.create_table('roster_managers',
    sa.Column('season_roster_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_user_id', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('source_order', sa.SmallInteger(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['season_roster_id'], ['sleeper.rosters.season_roster_id'], name=op.f('fk_roster_managers_season_roster_id_rosters'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sleeper_user_id'], ['sleeper.users.sleeper_user_id'], name=op.f('fk_roster_managers_sleeper_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_roster_managers_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('season_roster_id', 'sleeper_user_id', name=op.f('pk_roster_managers')),
    schema='sleeper'
    )
    op.create_index('ix_roster_managers_user', 'roster_managers', ['sleeper_user_id'], unique=False, schema='sleeper')
    op.create_index('uq_roster_managers_one_owner', 'roster_managers', ['season_roster_id'], unique=True, schema='sleeper', postgresql_where=sa.text("role = 'owner'"))
    op.create_table('roster_players',
    sa.Column('season_roster_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_player_id', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['season_roster_id'], ['sleeper.rosters.season_roster_id'], name=op.f('fk_roster_players_season_roster_id_rosters'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sleeper_player_id'], ['sleeper.players.sleeper_player_id'], name=op.f('fk_roster_players_sleeper_player_id_players'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_roster_players_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('season_roster_id', 'sleeper_player_id', name=op.f('pk_roster_players')),
    schema='sleeper'
    )
    op.create_index('ix_roster_players_player', 'roster_players', ['sleeper_player_id'], unique=False, schema='sleeper')
    op.create_table('matchups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('week', sa.SmallInteger(), nullable=False),
    sa.Column('season_roster_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_matchup_id', sa.Integer(), nullable=True),
    sa.Column('points', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_matchups_season_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_matchups_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_matchups')),
    sa.UniqueConstraint('competition_season_id', 'week', 'season_roster_id', name='uq_matchups_season_week_roster'),
    schema='sleeper'
    )
    op.create_index('ix_matchups_season_week_matchup', 'matchups', ['competition_season_id', 'week', 'sleeper_matchup_id'], unique=False, schema='sleeper')
    op.create_table('player_performances',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('week', sa.SmallInteger(), nullable=False),
    sa.Column('season_roster_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_matchup_id', sa.Integer(), nullable=True),
    sa.Column('sleeper_player_id', sa.Text(), nullable=False),
    sa.Column('points', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_player_performances_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sleeper_player_id'], ['sleeper.players.sleeper_player_id'], name=op.f('fk_player_performances_sleeper_player_id_players'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_player_performances_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_player_performances')),
    sa.UniqueConstraint('competition_season_id', 'week', 'season_roster_id', 'sleeper_player_id', name='uq_player_performances_natural'),
    schema='sleeper'
    )
    op.create_index('ix_player_performances_player_season_week', 'player_performances', ['sleeper_player_id', 'competition_season_id', 'week'], unique=False, schema='sleeper')
    op.create_index('ix_player_performances_roster_week', 'player_performances', ['season_roster_id', 'week'], unique=False, schema='sleeper')
    op.create_table('transactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_transaction_id', sa.Text(), nullable=False),
    sa.Column('week', sa.SmallInteger(), nullable=False),
    sa.Column('transaction_type', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=True),
    sa.Column('provider_created_at_ms', sa.BigInteger(), nullable=True),
    sa.Column('settings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['competition_season_id'], ['core.competition_seasons.id'], name=op.f('fk_transactions_competition_season_id_competition_seasons'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_transactions_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions')),
    sa.UniqueConstraint('competition_season_id', 'sleeper_transaction_id', name='uq_transactions_season_sleeper_id'),
    sa.UniqueConstraint('id', 'competition_season_id', name='uq_transactions_id_season'),
    schema='sleeper'
    )
    op.create_index('ix_transactions_season_week_type_status', 'transactions', ['competition_season_id', 'week', 'transaction_type', 'status'], unique=False, schema='sleeper')
    op.create_index('ix_transactions_sleeper_id', 'transactions', ['sleeper_transaction_id'], unique=False, schema='sleeper')
    op.create_table('draft_picks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('draft_season_year', sa.Integer(), nullable=False),
    sa.Column('round', sa.SmallInteger(), nullable=False),
    sa.Column('original_franchise_id', sa.UUID(), nullable=False),
    sa.Column('current_franchise_id', sa.UUID(), nullable=False),
    sa.Column('sleeper_pick_id', sa.Text(), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_api_request_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['competition_id'], ['core.competitions.id'], name=op.f('fk_draft_picks_competition_id_competitions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['current_franchise_id', 'competition_id'], ['core.franchises.id', 'core.franchises.competition_id'], name='fk_draft_picks_current_franchise_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['original_franchise_id', 'competition_id'], ['core.franchises.id', 'core.franchises.competition_id'], name='fk_draft_picks_original_franchise_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_draft_picks_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_draft_picks')),
    sa.UniqueConstraint('competition_id', 'draft_season_year', 'round', 'original_franchise_id', name='uq_draft_picks_natural'),
    sa.UniqueConstraint('id', 'competition_id', name='uq_draft_picks_id_competition'),
    schema='sleeper'
    )
    op.create_index('ix_draft_picks_current_owner', 'draft_picks', ['competition_id', 'draft_season_year', 'current_franchise_id'], unique=False, schema='sleeper')
    op.create_table('transaction_moves',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('transaction_id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('move_index', sa.Integer(), nullable=False),
    sa.Column('move_kind', sa.Text(), nullable=False),
    sa.Column('from_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('to_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('sleeper_player_id', sa.Text(), nullable=True),
    sa.Column('draft_pick_id', sa.UUID(), nullable=True),
    sa.Column('budget_amount', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['draft_pick_id'], ['sleeper.draft_picks.id'], name=op.f('fk_transaction_moves_draft_pick_id_draft_picks'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['from_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_transaction_moves_from_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sleeper_player_id'], ['sleeper.players.sleeper_player_id'], name=op.f('fk_transaction_moves_sleeper_player_id_players'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_transaction_moves_to_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['transaction_id', 'competition_season_id'], ['sleeper.transactions.id', 'sleeper.transactions.competition_season_id'], name='fk_transaction_moves_transaction_scope', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transaction_moves')),
    sa.UniqueConstraint('transaction_id', 'move_index', name='uq_transaction_moves_index'),
    schema='sleeper'
    )
    op.create_index('ix_transaction_moves_from_roster', 'transaction_moves', ['from_season_roster_id'], unique=False, schema='sleeper')
    op.create_index('ix_transaction_moves_pick', 'transaction_moves', ['draft_pick_id'], unique=False, schema='sleeper')
    op.create_index('ix_transaction_moves_player', 'transaction_moves', ['sleeper_player_id'], unique=False, schema='sleeper')
    op.create_index('ix_transaction_moves_to_roster', 'transaction_moves', ['to_season_roster_id'], unique=False, schema='sleeper')
    op.create_table('playoff_matchups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_season_id', sa.UUID(), nullable=False),
    sa.Column('bracket_kind', sa.Text(), nullable=False),
    sa.Column('node_key', sa.Text(), nullable=False),
    sa.Column('round', sa.SmallInteger(), nullable=False),
    sa.Column('t1_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('t2_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('t1_from_node_key', sa.Text(), nullable=True),
    sa.Column('t1_from_outcome', sa.Text(), nullable=True),
    sa.Column('t2_from_node_key', sa.Text(), nullable=True),
    sa.Column('t2_from_outcome', sa.Text(), nullable=True),
    sa.Column('winner_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('loser_season_roster_id', sa.UUID(), nullable=True),
    sa.Column('placement', sa.SmallInteger(), nullable=True),
    sa.Column('source_api_request_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['competition_season_id'], ['core.competition_seasons.id'], name=op.f('fk_playoff_matchups_competition_season_id_competition_seasons'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['loser_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_playoff_matchups_loser_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_api_request_id'], ['sleeper.api_requests.id'], name=op.f('fk_playoff_matchups_source_api_request_id_api_requests'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['t1_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_playoff_matchups_t1_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['t2_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_playoff_matchups_t2_roster_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['winner_season_roster_id', 'competition_season_id'], ['core.season_rosters.id', 'core.season_rosters.competition_season_id'], name='fk_playoff_matchups_winner_scope', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_playoff_matchups')),
    sa.UniqueConstraint('competition_season_id', 'bracket_kind', 'node_key', name='uq_playoff_matchups_natural'),
    schema='sleeper'
    )
    op.create_index('ix_playoff_matchups_bracket_round', 'playoff_matchups', ['competition_season_id', 'bracket_kind', 'round'], unique=False, schema='sleeper')
    op.create_index('ix_playoff_matchups_winner', 'playoff_matchups', ['winner_season_roster_id'], unique=False, schema='sleeper')
    op.create_table('data_snapshots',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('primary_competition_season_id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('domain_cutoff_week', sa.SmallInteger(), nullable=True),
    sa.Column('domain_cutoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('knowledge_cutoff_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('materializer_version', sa.Text(), nullable=False),
    sa.Column('sqlite_schema_version', sa.Text(), nullable=False),
    sa.Column('code_version', sa.Text(), nullable=False),
    sa.Column('completeness_warnings', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('selected_request_set_sha256', sa.Text(), nullable=True),
    sa.Column('sqlite_artifact_sha256', sa.Text(), nullable=True),
    sa.Column('sqlite_artifact_byte_length', sa.BigInteger(), nullable=True),
    sa.Column('sqlite_artifact_storage_key', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['competition_id'], ['core.competitions.id'], name=op.f('fk_data_snapshots_competition_id_competitions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['primary_competition_season_id', 'competition_id'], ['core.competition_seasons.id', 'core.competition_seasons.competition_id'], name='fk_data_snapshots_primary_season_scope', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_snapshots')),
    sa.UniqueConstraint('id', 'competition_id', name='uq_data_snapshots_id_competition'),
    sa.UniqueConstraint('id', 'primary_competition_season_id', name='uq_data_snapshots_id_primary_season'),
    schema='sleeper'
    )
    op.create_index('ix_data_snapshots_competition_status', 'data_snapshots', ['competition_id', 'status'], unique=False, schema='sleeper')
    op.create_index('ix_data_snapshots_season_mode_cutoff_created', 'data_snapshots', ['primary_competition_season_id', 'mode', 'knowledge_cutoff_at', 'created_at'], unique=False, schema='sleeper')
    op.create_table('data_snapshot_requests',
    sa.Column('data_snapshot_id', sa.UUID(), nullable=False),
    sa.Column('api_request_id', sa.UUID(), nullable=False),
    sa.Column('scope_key', sa.Text(), nullable=False),
    sa.Column('selection_role', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['api_request_id', 'scope_key'], ['sleeper.api_requests.id', 'sleeper.api_requests.scope_key'], name='fk_data_snapshot_requests_request_scope', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['data_snapshot_id'], ['sleeper.data_snapshots.id'], name=op.f('fk_data_snapshot_requests_data_snapshot_id_data_snapshots'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('data_snapshot_id', 'api_request_id', name=op.f('pk_data_snapshot_requests')),
    sa.UniqueConstraint('data_snapshot_id', 'scope_key', name='uq_data_snapshot_requests_snapshot_scope'),
    schema='sleeper'
    )
    op.create_index('ix_data_snapshot_requests_api_request', 'data_snapshot_requests', ['api_request_id'], unique=False, schema='sleeper')
    _create_sleeper_triggers()



def downgrade() -> None:
    _drop_sleeper_triggers()
    op.drop_index('ix_data_snapshot_requests_api_request', table_name='data_snapshot_requests', schema='sleeper')
    op.drop_table('data_snapshot_requests', schema='sleeper')
    op.drop_index('ix_data_snapshots_season_mode_cutoff_created', table_name='data_snapshots', schema='sleeper')
    op.drop_index('ix_data_snapshots_competition_status', table_name='data_snapshots', schema='sleeper')
    op.drop_table('data_snapshots', schema='sleeper')
    op.drop_index('ix_playoff_matchups_winner', table_name='playoff_matchups', schema='sleeper')
    op.drop_index('ix_playoff_matchups_bracket_round', table_name='playoff_matchups', schema='sleeper')
    op.drop_table('playoff_matchups', schema='sleeper')
    op.drop_index('ix_transaction_moves_to_roster', table_name='transaction_moves', schema='sleeper')
    op.drop_index('ix_transaction_moves_player', table_name='transaction_moves', schema='sleeper')
    op.drop_index('ix_transaction_moves_pick', table_name='transaction_moves', schema='sleeper')
    op.drop_index('ix_transaction_moves_from_roster', table_name='transaction_moves', schema='sleeper')
    op.drop_table('transaction_moves', schema='sleeper')
    op.drop_index('ix_draft_picks_current_owner', table_name='draft_picks', schema='sleeper')
    op.drop_table('draft_picks', schema='sleeper')
    op.drop_index('ix_transactions_sleeper_id', table_name='transactions', schema='sleeper')
    op.drop_index('ix_transactions_season_week_type_status', table_name='transactions', schema='sleeper')
    op.drop_table('transactions', schema='sleeper')
    op.drop_index('ix_player_performances_roster_week', table_name='player_performances', schema='sleeper')
    op.drop_index('ix_player_performances_player_season_week', table_name='player_performances', schema='sleeper')
    op.drop_table('player_performances', schema='sleeper')
    op.drop_index('ix_matchups_season_week_matchup', table_name='matchups', schema='sleeper')
    op.drop_table('matchups', schema='sleeper')
    op.drop_index('ix_roster_players_player', table_name='roster_players', schema='sleeper')
    op.drop_table('roster_players', schema='sleeper')
    op.drop_index('uq_roster_managers_one_owner', table_name='roster_managers', schema='sleeper', postgresql_where=sa.text("role = 'owner'"))
    op.drop_index('ix_roster_managers_user', table_name='roster_managers', schema='sleeper')
    op.drop_table('roster_managers', schema='sleeper')
    op.drop_index('ix_rosters_competition_season', table_name='rosters', schema='sleeper')
    op.drop_table('rosters', schema='sleeper')
    op.drop_index('ix_players_team_position', table_name='players', schema='sleeper')
    op.drop_index('ix_players_full_name_lower', table_name='players', schema='sleeper')
    op.drop_table('players', schema='sleeper')
    op.drop_index('ix_league_users_user', table_name='league_users', schema='sleeper')
    op.drop_table('league_users', schema='sleeper')
    op.drop_index('ix_users_display_name_lower', table_name='users', schema='sleeper')
    op.drop_table('users', schema='sleeper')
    op.drop_index('ix_leagues_source_request', table_name='leagues', schema='sleeper')
    op.drop_table('leagues', schema='sleeper')
    op.drop_table('normalized_scopes', schema='sleeper')
    op.drop_index('ix_api_requests_season_endpoint_week', table_name='api_requests', schema='sleeper')
    op.drop_index('ix_api_requests_refresh_run', table_name='api_requests', schema='sleeper')
    op.drop_index('ix_api_requests_eligible_scope_completed', table_name='api_requests', schema='sleeper', postgresql_where=sa.text("status = 'succeeded' AND is_complete"))
    op.drop_table('api_requests', schema='sleeper')
    op.drop_table('api_payloads', schema='sleeper')
    op.drop_index('ix_refresh_runs_competition_started', table_name='refresh_runs', schema='sleeper')
    op.drop_table('refresh_runs', schema='sleeper')
