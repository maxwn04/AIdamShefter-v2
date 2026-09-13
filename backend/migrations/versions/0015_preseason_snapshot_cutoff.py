"""Allow a preseason cutoff with no completed current-season weeks.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_minimum(minimum: int) -> None:
    for table, column in (
        ("data_snapshot_seasons", "through_week"),
        ("automatic_refresh_claims", "requested_through_week"),
    ):
        op.drop_constraint(
            op.f(f"ck_{table}_through_week"), table, schema="sleeper", type_="check",
        )
        op.create_check_constraint(
            "through_week", table, f"{column} BETWEEN {minimum} AND 18", schema="sleeper",
        )


def upgrade() -> None:
    _set_minimum(0)


def downgrade() -> None:
    # Existing Week 0 rows make this fail atomically rather than deleting history.
    _set_minimum(1)
