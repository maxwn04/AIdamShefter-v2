"""Ordinary backend composition with a separate session-level controller lock."""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from backend.composition import build_generation_dependencies
from backend.config import DatalayerSettings
from backend.database.models.core import CompetitionSeason
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext, SystemProcessActor
from backend.resources.memory.revisions import CanonicalRevision, RevisionManager
from backend.resources.reporting.generations import Generation, GenerationQuery
from backend.resources.sleeper_data import DataSnapshotManager
from backend.season_simulation.contracts import Campaign
from backend.season_simulation.controller import step_request
from backend.services.datalayer import LocalDatalayerFileStore
from backend.services.generations import GenerationRequest, PreparedSnapshotResolver
from backend.services.model_usage.pricing import LiteLLMModelRegistry, _load_bundled_model_map


class DatabaseCampaignBackend:
    def __init__(self, engine: Engine, competition_id: UUID) -> None:
        self.engine = engine
        self.competition_id = competition_id
        self.factory = create_session_factory(engine)
        self.context = ManagerContext(
            actor=SystemProcessActor(process_name="season-simulation"),
            scope=CompetitionScope(competition_id=competition_id),
            correlation_id=uuid4(),
        )
        self.dependencies = build_generation_dependencies(
            self.factory, self.context,
            model_registry=LiteLLMModelRegistry(remote_loader=_load_bundled_model_map),
        )
        self.revision_manager = RevisionManager(self.factory, self.context)
        self.resolver = PreparedSnapshotResolver(
            snapshots=DataSnapshotManager(self.factory, self.context),
            files=LocalDatalayerFileStore(DatalayerSettings.from_environment().data_root),
        )

    def close(self) -> None:
        self.dependencies.close()

    @contextmanager
    def lock(self) -> Iterator[None]:
        # This dedicated AUTOCOMMIT connection has no transaction during provider
        # work. Normal managers use independent short transaction scopes.
        key = int.from_bytes(self.competition_id.bytes[:8], "big", signed=True)
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
                raise RuntimeError("another season controller owns this competition")
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})

    def generations(self) -> tuple[Generation, ...]:
        rows = []
        offset = 0
        while True:
            page = self.dependencies.generations.list(GenerationQuery(limit=200, offset=offset))
            rows.extend(self.dependencies.generations.get(item.id) for item in page.items)
            offset += len(page.items)
            if offset >= page.total:
                return tuple(rows)

    def revisions(self) -> tuple[CanonicalRevision, ...]:
        return self.revision_manager.history()

    def head(self) -> UUID:
        return self.revision_manager.current().revision_id

    def validate_inputs(self, campaign: Campaign) -> None:
        with self.factory() as session:
            season = session.get(CompetitionSeason, campaign.inputs.competition_season_id)
            if season is None or season.competition_id != campaign.inputs.competition_id or season.season_year != campaign.inputs.season_year:
                raise ValueError("campaign competition/season/year differs from database")
        if DatalayerSettings.from_environment().data_root.resolve() != campaign.inputs.data_root.resolve():
            raise ValueError("campaign data root differs from runtime")
        for index, step in enumerate(campaign.inputs.steps):
            snapshot = self.resolver.resolve(
                step_request(campaign, index, 1, campaign.root_revision_id).settings.prepared_execution,
                competition_id=campaign.inputs.competition_id,
                competition_season_id=campaign.inputs.competition_season_id,
                through_week=step.week,
            )
            primary = snapshot.included_seasons[-1]
            if primary.season_year != campaign.inputs.season_year:
                raise ValueError("prepared snapshot season year differs from campaign")

    def submit(self, request: GenerationRequest) -> None:
        self.dependencies.service.submit(request)

    async def execute(self, generation_id: UUID) -> None:
        await self.dependencies.service.execute(generation_id)

    def usage(self, generation_ids: tuple[UUID, ...]) -> tuple[int, Decimal, bool]:
        totals = [self.dependencies.usage.get(gid) for gid in generation_ids]
        return (
            sum(item.tokens.total_tokens for item in totals),
            sum((Decimal(item.estimated_cost or "0") for item in totals), Decimal(0)),
            all(item.complete for item in totals),
        )
