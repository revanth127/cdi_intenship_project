from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit-log", tags=["Audit Log"])

ALLOW_AUDIT_READ = require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.OWNER)


@router.get("", response_model=list[AuditLogResponse], dependencies=[Depends(ALLOW_AUDIT_READ)])
def get_audit_log(
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. Order, Invoice, ProductionRun)"),
    entity_id: Optional[str] = Query(None, description="Filter by specific entity ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID who performed the action"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    from_date: Optional[datetime] = Query(None, alias="from", description="From timestamp"),
    to_date: Optional[datetime] = Query(None, alias="to", description="To timestamp"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Paginated audit log query endpoint (ADMIN, ACCOUNTANT, OWNER read-only).
    Returns system actions newest first.
    """
    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
    )

    if entity_type:
        stmt = stmt.where(func.lower(AuditLog.entity_type) == entity_type.lower())
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == str(entity_id))
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(func.lower(AuditLog.action) == action.lower())
    if from_date:
        stmt = stmt.where(AuditLog.created_at >= from_date)
    if to_date:
        stmt = stmt.where(AuditLog.created_at <= to_date)

    stmt = stmt.offset(skip).limit(limit)
    rows = db.scalars(stmt).all()

    return [
        AuditLogResponse(
            id=row.id,
            user_id=row.user_id,
            user_name=row.user.full_name if row.user else None,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            request_id=row.request_id,
            ip_address=row.ip_address,
            old_values=row.old_values,
            new_values=row.new_values,
            created_at=row.created_at,
        )
        for row in rows
    ]
