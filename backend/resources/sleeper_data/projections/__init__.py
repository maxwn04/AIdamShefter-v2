"""Transaction-scoped normalized-current-state projection writers."""

from backend.resources.sleeper_data.projections.dispatch import write_endpoint_records

__all__ = ["write_endpoint_records"]
