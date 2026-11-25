from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.user import User, UserRole
from app.schemas.production import (
    ProductionRunCancel,
    ProductionRunCreate,
    ProductionRunResponse,
    ProductionRunUpdate,
    VarianceAlertResponse,
)
from app.services import production as prod_service

router = APIRouter(prefix="/production", tags=["Production"])

# RBAC Roles:
# Read: ADMIN, OWNER, ACCOUNTANT, PRODUCTION
# Create / Edit / Post: PRODUCTION, ADMIN
# Cancel: ADMIN only
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)
ALLOW_WRITE = require_roles(UserRole.ADMIN, UserRole.PRODUCTION)
ALLOW_ADMIN = require_roles(UserRole.ADMIN)


@router.post(
    "",
    response_model=ProductionRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ALLOW_WRITE)],
)
def create_production_run(
    payload: ProductionRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a new DRAFT production run scaled from the active product BOM.
    """
    return prod_service.create_run(db=db, payload=payload, user=current_user)


@router.get(
    "/variance-alerts",
    response_model=list[VarianceAlertResponse],
    dependencies=[Depends(ALLOW_READ)],
)
def get_variance_alerts(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """
    Returns production runs where material consumption or finished goods yield
    exceeded variance tolerance thresholds.
    """
    return prod_service.get_variance_alerts(db=db, from_date=from_date, to_date=to_date)


@router.get("", response_model=list[ProductionRunResponse], dependencies=[Depends(ALLOW_READ)])
def list_production_runs(
    product_id: Optional[int] = None,
    status_filter: Optional[ProductionRunStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lists production runs with optional product and status filtering."""
    stmt = (
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
            selectinload(ProductionRun.product),
        )
        .order_by(desc(ProductionRun.created_at))
    )
    if product_id:
        stmt = stmt.where(ProductionRun.product_id == product_id)
    if status_filter:
        stmt = stmt.where(ProductionRun.status == status_filter)
    stmt = stmt.offset(skip).limit(limit)
    runs = db.scalars(stmt).all()
    for r in runs:
        prod_service.attach_variance_report(db, r)
    return runs


@router.get("/{run_id}", response_model=ProductionRunResponse, dependencies=[Depends(ALLOW_READ)])
def get_production_run(run_id: int, db: Session = Depends(get_db)):
    """Retrieves full details of a single production run."""
    run = db.scalar(
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
            selectinload(ProductionRun.product),
        )
        .where(ProductionRun.id == run_id)
    )
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production run not found")
    return prod_service.attach_variance_report(db, run)


@router.patch("/{run_id}", response_model=ProductionRunResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_production_run(
    run_id: int,
    payload: ProductionRunUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edits actual quantities, damaged items, and finished output for a DRAFT run.
    Audits every edit.
    """
    return prod_service.update_run(db=db, run_id=run_id, payload=payload, user=current_user)


@router.post("/{run_id}/post", response_model=ProductionRunResponse, dependencies=[Depends(ALLOW_WRITE)])
def post_production_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Posts a production run atomically:
    1. Pre-validates inventory (409 if any shortage).
    2. Writes PRODUCTION_ISSUE for materials and packaging.
    3. Writes PRODUCTION_OUTPUT for finished goods.
    4. Marks run POSTED.
    """
    return prod_service.post_run(db=db, run_id=run_id, user=current_user)


@router.post("/{run_id}/cancel", response_model=ProductionRunResponse, dependencies=[Depends(ALLOW_ADMIN)])
def cancel_production_run(
    run_id: int,
    payload: ProductionRunCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancels a production run (ADMIN only). Reverses all stock movements if previously POSTED.
    """
    return prod_service.cancel_run(db=db, run_id=run_id, reason=payload.reason, user=current_user)
