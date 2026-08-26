from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config


def _config(*, output_buffer: StringIO) -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(
        str(root / "backend" / "migrations" / "alembic.ini"),
        output_buffer=output_buffer,
    )
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://unused:unused@localhost/unused",
    )
    return config


def test_multi_season_preparation_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(_config(output_buffer=upgrade_sql), "0010", sql=True)
    upgrade = upgrade_sql.getvalue()

    assert "ADD COLUMN input_revision TEXT" in upgrade
    assert "CREATE TABLE sleeper.data_snapshot_seasons" in upgrade
    assert "INSERT INTO sleeper.data_snapshot_seasons" in upgrade
    assert "CREATE TABLE sleeper.automatic_refresh_claims" in upgrade
    assert "uq_data_snapshot_seasons_primary" in upgrade
    assert "uq_automatic_refresh_claims_active_key" in upgrade
    assert "WHERE role = 'primary'" in upgrade
    assert "WHERE status = 'running'" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(output_buffer=downgrade_sql),
        "0010:0009",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()

    assert "DROP TABLE sleeper.automatic_refresh_claims" in downgrade
    assert "DROP TABLE sleeper.data_snapshot_seasons" in downgrade
    assert "DROP COLUMN input_revision" in downgrade
