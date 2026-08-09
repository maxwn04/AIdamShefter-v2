from uuid import UUID

from backend.api.dependencies.context import get_competition_manager_context

COMPETITION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_competition_context_uses_path_scope_and_request_correlation() -> None:
    context = get_competition_manager_context(
        competition_id=COMPETITION_ID,
        request_id=" request-123 ",
    )

    assert context.actor_kind == "api"
    assert context.actor_id == "local-api"
    assert context.competition_id == COMPETITION_ID
    assert context.global_reason is None
    assert context.correlation_id == "request-123"


def test_competition_context_generates_missing_correlation_id() -> None:
    context = get_competition_manager_context(
        competition_id=COMPETITION_ID,
        request_id=None,
    )

    assert context.correlation_id is not None
    assert context.correlation_id.strip()
