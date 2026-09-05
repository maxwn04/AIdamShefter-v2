"""Errors exposed by the frozen query runtime."""


class FrozenSnapshotInvalid(RuntimeError):
    """A purported ready artifact does not match its sealed snapshot identity."""


__all__ = ["FrozenSnapshotInvalid"]
