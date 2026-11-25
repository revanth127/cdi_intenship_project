import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger("audit")


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: str | int,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """
    Reusable audit logging service function.
    Records system actions with before-and-after snapshots in JSONB.
    """
    user_id = user.id if user else None
    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_values=old_values,
        new_values=new_values,
    )
    db.add(audit_entry)
    db.flush()
    logger.info(
        "AUDIT: action=%s entity=%s:%s user_id=%s",
        action,
        entity_type,
        entity_id,
        user_id,
    )
    return audit_entry
