from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.transactions import (
    TransactionManager,
    TransactionQuery,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound
from backend.tests.resources.sleeper_data.conftest import (
    ProjectedSeason,
    manager_context,
    seed_domain,
)


def _manager(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> TransactionManager:
    return TransactionManager(
        session_factory,
        manager_context(projected_season.domain),
    )


def test_transaction_reads_include_ordered_moves_and_decimal_safe_json(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    transactions = _manager(session_factory, projected_season).list_transactions(
        TransactionQuery(competition_season_id=projected_season.domain.season_id)
    )

    assert len(transactions) == 1
    transaction = transactions[0]
    assert transaction.sleeper_transaction_id == projected_season.sleeper_transaction_id
    assert transaction.competition_season_id == projected_season.domain.season_id
    assert transaction.week == projected_season.week
    assert transaction.transaction_type == "trade"
    assert transaction.status == "complete"
    assert transaction.provider_created_at_ms == 123456
    assert transaction.settings == {"waiver_bid": Decimal("3.5")}
    assert isinstance(transaction.settings["waiver_bid"], Decimal)
    assert transaction.metadata == {"note": "fixture"}
    assert transaction.source_api_request_id == projected_season.transaction_request_id
    assert len(transaction.moves) == 1
    move = transaction.moves[0]
    assert move.move_index == 0
    assert move.move_kind == "player"
    assert move.from_season_roster_id == projected_season.domain.roster_ids[0]
    assert move.to_season_roster_id == projected_season.domain.roster_ids[1]
    assert move.sleeper_player_id == projected_season.player_ids[1]
    assert move.draft_season_year is None
    assert move.draft_round is None
    assert move.original_franchise_id is None
    assert move.sleeper_pick_id is None


@pytest.mark.parametrize(
    "query_values",
    (
        {"week": 2},
        {"transaction_type": "waiver"},
        {"status": "pending"},
    ),
)
def test_transaction_query_filters_exact_current_rows(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
    query_values: dict[str, object],
) -> None:
    manager = _manager(session_factory, projected_season)
    matching = manager.list_transactions(
        TransactionQuery(
            competition_season_id=projected_season.domain.season_id,
            week=projected_season.week,
            transaction_type="trade",
            status="complete",
        )
    )
    missing = manager.list_transactions(
        TransactionQuery(
            competition_season_id=projected_season.domain.season_id,
            **query_values,
        )
    )

    assert [item.sleeper_transaction_id for item in matching] == [
        projected_season.sleeper_transaction_id
    ]
    assert missing == ()


def test_transaction_reads_reject_a_season_from_another_competition(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    other_domain = seed_domain(database_engine, label="Other")
    other_manager = TransactionManager(
        session_factory,
        manager_context(other_domain),
    )

    with pytest.raises(DatalayerResourceNotFound):
        other_manager.list_transactions(
            TransactionQuery(
                competition_season_id=projected_season.domain.season_id,
            )
        )
