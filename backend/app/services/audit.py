import contextvars
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger("audit")

# Context variables populated by middleware on each incoming HTTP request
current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_request_id", default=None)
current_ip_address: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_ip_address", default=None)


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: str | int,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Reusable audit logging service function.
    Records system actions with before-and-after snapshots in JSONB.
    Automatically captures request_id and ip_address from context if not explicitly provided.
    """
    user_id = user.id if user else None
    req_id = request_id or current_request_id.get()
    client_ip = ip_address or current_ip_address.get()

    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_values=old_values,
        new_values=new_values,
        request_id=req_id,
        ip_address=client_ip,
    )
    db.add(audit_entry)
    db.flush()
    logger.info(
        "AUDIT: action=%s entity=%s:%s user_id=%s req_id=%s ip=%s",
        action,
        entity_type,
        entity_id,
        user_id,
        req_id,
        client_ip,
    )
    return audit_entry
