"""Complete ORM metadata registry imported by Alembic.

Namespace model imports are added here as their stack layers land. Keeping this
module as the sole Alembic entry point prevents migrations from depending on
resource managers or services.
"""

from backend.database.base import Base
from backend.database.models import core as core_models
from backend.database.models import sleeper as sleeper_models
from backend.database.models import memory as memory_models

metadata = Base.metadata

__all__ = ["core_models", "memory_models", "metadata", "sleeper_models"]
