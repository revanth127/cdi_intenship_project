from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.purchase import Purchase, PurchaseStatus
from app.models.user import User, UserRole
from app.schemas.purchase import PurchaseCreate, PurchaseResponse
from app.services.purchase import cancel_purchase, create_and_post_purchase

router = APIRouter(prefix="/purchases", tags=["Purchases"])

ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.PRODUCTION, UserRole.ACCOUNTANT, UserRole.OWNER)
ALLOW_CREATE = require_roles(UserRole.ADMIN, UserRole.PRODUCTION)
ALLOW_CANCEL = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[PurchaseResponse], dependencies=[Depends(ALLOW_READ)])
def list_purchases(
    supplier_id: Optional[int] = None,
    status_filter: Optional[PurchaseStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Purchase).options(selectinload(Purchase.lines)).offset(skip).limit(limit)
    if supplier_id:
        stmt = stmt.where(Purchase.supplier_id == supplier_id)
    if status_filter:
        stmt = stmt.where(Purchase.status == status_filter)
    return db.scalars(stmt).all()


@router.post("", response_model=PurchaseResponse, status_code=status.HTTP_201_CREATED)
def record_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ALLOW_CREATE),
):
    """
    Creates and posts a purchase receipt. Immediately writes immutable rows
    into the stock ledger in the same database transaction.
    """
    return create_and_post_purchase(db, payload, current_user)


@router.get("/{purchase_id}", response_model=PurchaseResponse, dependencies=[Depends(ALLOW_READ)])
def get_purchase(purchase_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(Purchase)
        .options(selectinload(Purchase.lines))
        .where(Purchase.id == purchase_id)
    )
    purchase = db.scalar(stmt)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase {purchase_id} not found",
        )
    return purchase


@router.post("/{purchase_id}/cancel", response_model=PurchaseResponse)
def cancel_purchase_endpoint(
    purchase_id: int,
    reason: str = Query("Cancelled by administrator"),
    db: Session = Depends(get_db),
    current_user: User = Depends(ALLOW_CANCEL),
):
    """
    Cancels a purchase receipt by writing REVERSAL rows in the stock ledger.
    No rows are deleted.
    """
    return cancel_purchase(db, purchase_id, current_user, reason)
