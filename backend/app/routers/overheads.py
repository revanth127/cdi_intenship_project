from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.costing import OverheadEntry, OverheadStatus
from app.models.user import User, UserRole
from app.schemas.costing import (
    OverheadCreate,
    OverheadResponse,
    OverheadVoid,
)
from app.services import costing as costing_service

router = APIRouter(prefix="/overheads", tags=["Overheads"])

ALLOW_WRITE = require_roles(UserRole.ADMIN, UserRole.PRODUCTION)
ALLOW_ADMIN = require_roles(UserRole.ADMIN)
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)


@router.post("", response_model=OverheadResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_overhead(
    payload: OverheadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Records an overhead expenditure (Labour, Gas, Power, Other).
    Allowed roles: ADMIN, PRODUCTION.
    """
    return costing_service.record_overhead(db=db, payload=payload, user=current_user)


@router.get("", response_model=list[OverheadResponse], dependencies=[Depends(ALLOW_READ)])
def list_overheads(
    month: Optional[str] = Query(None, description="Filter by YYYY-MM"),
    run_id: Optional[int] = Query(None, description="Filter by production run ID"),
    status_filter: Optional[OverheadStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """
    Lists overhead entries with optional month, run_id, and status filters.
    Allowed roles: ADMIN, PRODUCTION, ACCOUNTANT, OWNER. (SALESMAN no access).
    """
    stmt = select(OverheadEntry).order_by(desc(OverheadEntry.entry_date))
    if month:
        stmt = stmt.where(OverheadEntry.month == month)
    if run_id is not None:
        stmt = stmt.where(OverheadEntry.production_run_id == run_id)
    if status_filter:
        stmt = stmt.where(OverheadEntry.status == status_filter)

    return db.scalars(stmt).all()


@router.post("/{overhead_id}/void", response_model=OverheadResponse, dependencies=[Depends(ALLOW_ADMIN)])
def void_overhead(
    overhead_id: int,
    payload: OverheadVoid,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Voids an erroneous overhead entry with a mandatory reason.
    Allowed roles: ADMIN only.
    """
    return costing_service.void_overhead(
        db=db, overhead_id=overhead_id, reason=payload.reason, user=current_user
    )
