"""Complete ORM metadata registry imported by Alembic.

Namespace model imports are added here as their stack layers land. Keeping this
module as the sole Alembic entry point prevents migrations from depending on
resource managers or services.
"""

from backend.database.base import Base
from backend.database.models import core as core_models

metadata = Base.metadata

__all__ = ["core_models", "metadata"]
