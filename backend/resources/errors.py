"""Persistence-boundary errors shared by resource managers."""


class ResourceError(RuntimeError):
    """A safe resource-boundary failure."""


class ResourceNotFound(ResourceError):
    """The requested resource does not exist in the manager's scope."""


class ResourceConflict(ResourceError):
    """The requested mutation conflicts with the aggregate's current state."""


class InvalidResourceCommand(ResourceError):
    """A mutation command violates an aggregate invariant."""


class ResourceReferenceUnavailable(ResourceError):
    """Valid source records reference platform data that is not yet available."""
