from datetime import datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)


def _insert_identity_graph(engine: Engine) -> dict[str, UUID]:
    ids = {
        "competition": uuid4(),
        "season": uuid4(),
        "franchise": uuid4(),
        "roster": uuid4(),
    }
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": ids["competition"], "display_name": "The League"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": ids["season"],
                "competition_id": ids["competition"],
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            sa.insert(Franchise),
            {
                "id": ids["franchise"],
                "competition_id": ids["competition"],
                "display_name": "Fourth and Long",
            },
        )
        connection.execute(
            sa.insert(SeasonRoster),
            {
                "id": ids["roster"],
                "competition_id": ids["competition"],
                "competition_season_id": ids["season"],
                "franchise_id": ids["franchise"],
                "sleeper_roster_id": "1",
            },
        )
    return ids


def _assert_integrity_error(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(statement)


def test_core_constraints_and_indexes_are_named(
    database_engine: Engine,
) -> None:
    expected_constraints = {
        "pk_competitions",
        "pk_competition_seasons",
        "fk_competition_seasons_competition_id_competitions",
        "uq_competition_seasons_competition_id_season_year",
        "uq_competition_seasons_competition_id_sequence_number",
        "uq_competition_seasons_id_competition_id",
        "uq_competition_seasons_sleeper_league_id",
        "pk_franchises",
        "fk_franchises_competition_id_competitions",
        "uq_franchises_id_competition_id",
        "pk_season_rosters",
        "fk_season_rosters_competition_id_competitions",
        "fk_season_rosters_season_competition_scope",
        "fk_season_rosters_franchise_competition_scope",
        "uq_season_rosters_competition_season_id_sleeper_roster_id",
        "uq_season_rosters_competition_season_id_franchise_id",
        "uq_season_rosters_id_competition_season_id",
        "uq_season_rosters_id_competition_id",
    }
    expected_indexes = {
        "ix_franchises_competition_id_archived_at",
        "ix_season_rosters_competition_id",
        "ix_season_rosters_season_competition_scope",
        "ix_season_rosters_franchise_competition_scope",
    }

    with database_engine.connect() as connection:
        constraints = set(
            connection.execute(
                sa.text(
                    """
                    SELECT constraint_name
                    FROM information_schema.table_constraints
                    WHERE constraint_schema = 'core'
                    """
                )
            ).scalars()
        )
        indexes = set(
            connection.execute(
                sa.text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'core'
                    """
                )
            ).scalars()
        )
        foreign_key_delete_actions = dict(
            connection.execute(
                sa.text(
                    """
                    SELECT constraint_name, delete_rule
                    FROM information_schema.referential_constraints
                    WHERE constraint_schema = 'core'
                    """
                )
            ).all()
        )

    assert expected_constraints <= constraints
    assert expected_indexes <= indexes
    assert foreign_key_delete_actions
    assert set(foreign_key_delete_actions.values()) == {"RESTRICT"}


def test_core_uses_application_uuids_and_server_timestamps(
    database_engine: Engine,
) -> None:
    competition_id = uuid4()
    with database_engine.begin() as connection:
        row = connection.execute(
            sa.text(
                """
                INSERT INTO core.competitions (id, display_name)
                VALUES (:id, 'Timestamp League')
                RETURNING created_at, updated_at
                """
            ),
            {"id": competition_id},
        ).one()

    assert isinstance(row.created_at, datetime)
    assert row.created_at.tzinfo is not None
    assert row.updated_at.tzinfo is not None

    _assert_integrity_error(
        database_engine,
        sa.text("INSERT INTO core.competitions (display_name) VALUES ('Missing UUID')"),
    )


def test_competition_season_unique_coordinates_and_sleeper_id(
    database_engine: Engine,
) -> None:
    first_competition = uuid4()
    second_competition = uuid4()
    sleeper_league_id = f"league-{uuid4()}"
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": first_competition, "display_name": "First"},
                {"id": second_competition, "display_name": "Second"},
            ],
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": uuid4(),
                "competition_id": first_competition,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": sleeper_league_id,
            },
        )

    invalid_seasons = [
        {
            "id": uuid4(),
            "competition_id": first_competition,
            "season_year": 2026,
            "sequence_number": 2,
            "sleeper_league_id": f"league-{uuid4()}",
        },
        {
            "id": uuid4(),
            "competition_id": first_competition,
            "season_year": 2027,
            "sequence_number": 1,
            "sleeper_league_id": f"league-{uuid4()}",
        },
        {
            "id": uuid4(),
            "competition_id": second_competition,
            "season_year": 2026,
            "sequence_number": 1,
            "sleeper_league_id": sleeper_league_id,
        },
    ]
    for values in invalid_seasons:
        _assert_integrity_error(
            database_engine,
            sa.insert(CompetitionSeason).values(**values),
        )


def test_season_and_franchise_uniqueness_is_competition_scoped(
    database_engine: Engine,
) -> None:
    competition_id = uuid4()
    season_one_id = uuid4()
    season_two_id = uuid4()
    franchise_id = uuid4()
    second_franchise_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Dynasty"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            [
                {
                    "id": season_one_id,
                    "competition_id": competition_id,
                    "season_year": 2025,
                    "sequence_number": 1,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
                {
                    "id": season_two_id,
                    "competition_id": competition_id,
                    "season_year": 2026,
                    "sequence_number": 2,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
            ],
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": franchise_id,
                    "competition_id": competition_id,
                    "display_name": "Same Team",
                },
                {
                    "id": second_franchise_id,
                    "competition_id": competition_id,
                    "display_name": "Other Team",
                },
            ],
        )
        connection.execute(
            sa.insert(SeasonRoster),
            [
                {
                    "id": uuid4(),
                    "competition_id": competition_id,
                    "competition_season_id": season_one_id,
                    "franchise_id": franchise_id,
                    "sleeper_roster_id": "1",
                },
                {
                    "id": uuid4(),
                    "competition_id": competition_id,
                    "competition_season_id": season_two_id,
                    "franchise_id": franchise_id,
                    "sleeper_roster_id": "1",
                },
            ],
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(SeasonRoster).values(
            id=uuid4(),
            competition_id=competition_id,
            competition_season_id=season_one_id,
            franchise_id=second_franchise_id,
            sleeper_roster_id="1",
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(SeasonRoster).values(
            id=uuid4(),
            competition_id=competition_id,
            competition_season_id=season_one_id,
            franchise_id=franchise_id,
            sleeper_roster_id="2",
        ),
    )


def test_season_roster_rejects_cross_competition_references(
    database_engine: Engine,
) -> None:
    first_competition = uuid4()
    second_competition = uuid4()
    first_season = uuid4()
    second_season = uuid4()
    first_franchise = uuid4()
    second_franchise = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": first_competition, "display_name": "First"},
                {"id": second_competition, "display_name": "Second"},
            ],
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            [
                {
                    "id": first_season,
                    "competition_id": first_competition,
                    "season_year": 2026,
                    "sequence_number": 1,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
                {
                    "id": second_season,
                    "competition_id": second_competition,
                    "season_year": 2026,
                    "sequence_number": 1,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
            ],
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": first_franchise,
                    "competition_id": first_competition,
                    "display_name": "First Team",
                },
                {
                    "id": second_franchise,
                    "competition_id": second_competition,
                    "display_name": "Second Team",
                },
            ],
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(SeasonRoster).values(
            id=uuid4(),
            competition_id=first_competition,
            competition_season_id=second_season,
            franchise_id=first_franchise,
            sleeper_roster_id="1",
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(SeasonRoster).values(
            id=uuid4(),
            competition_id=first_competition,
            competition_season_id=first_season,
            franchise_id=second_franchise,
            sleeper_roster_id="1",
        ),
    )


@pytest.mark.parametrize("parent", ["competition", "season", "franchise"])
def test_core_durable_parents_use_restrict_deletes(
    database_engine: Engine,
    parent: str,
) -> None:
    ids = _insert_identity_graph(database_engine)
    statements = {
        "competition": sa.delete(Competition).where(Competition.id == ids["competition"]),
        "season": sa.delete(CompetitionSeason).where(CompetitionSeason.id == ids["season"]),
        "franchise": sa.delete(Franchise).where(Franchise.id == ids["franchise"]),
    }

    _assert_integrity_error(database_engine, statements[parent])
