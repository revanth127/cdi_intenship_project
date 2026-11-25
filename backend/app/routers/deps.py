from app.core.deps import get_current_user, require_roles
from app.models.user import UserRole

# Re-export core dependencies
require_admin = require_roles(UserRole.ADMIN)

__all__ = ["get_current_user", "require_roles", "require_admin"]
