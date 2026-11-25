from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.item import ItemType
from app.models.user import User, UserRole
from app.schemas.stock import (
    StockAdjustmentCreate,
    StockLedgerEntryResponse,
    StockMovementResponse,
    StockReconciliationResponse,
    StockSummaryResponse,
)
from app.services.stock import (
    get_stock_ledger,
    get_stock_summary,
    post_adjustment,
    reconcile_stock,
)

router = APIRouter(prefix="/stock", tags=["Stock Ledger"])

# Admin-only for adjustments
ALLOW_ADJUST = require_roles(UserRole.ADMIN)
# Read ledger: ADMIN, PRODUCTION, ACCOUNTANT, OWNER
ALLOW_LEDGER_READ = require_roles(
    UserRole.ADMIN, UserRole.PRODUCTION, UserRole.ACCOUNTANT, UserRole.OWNER
)
# Reconcile: ADMIN, ACCOUNTANT, OWNER
ALLOW_RECONCILE = require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.OWNER)


@router.get("/summary", response_model=list[StockSummaryResponse])
def get_summary(
    item_type: Optional[ItemType] = None,
    as_of: Optional[datetime] = None,
    from_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns item inventory summary with moving weighted average cost and
    opening + receipts - issues + adjustments = closing audit breakdown.
    - SALESMAN role may ONLY view finished-goods availability.
    - ADMIN, PRODUCTION, ACCOUNTANT, OWNER have full access.
    """
    if current_user.role == UserRole.SALESMAN:
        if item_type is not None and item_type != ItemType.FINISHED_GOOD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Salesmen may only view finished goods stock availability.",
            )
        item_type = ItemType.FINISHED_GOOD
    elif current_user.role not in (
        UserRole.ADMIN,
        UserRole.PRODUCTION,
        UserRole.ACCOUNTANT,
        UserRole.OWNER,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted for current user role.",
        )

    to_date = as_of
    return get_stock_summary(db, item_type=item_type, from_date=from_date, to_date=to_date)


@router.get("/ledger", response_model=list[StockLedgerEntryResponse], dependencies=[Depends(ALLOW_LEDGER_READ)])
def get_ledger(
    item_id: int = Query(..., description="Target Item ID"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """
    Returns the granular, immutable transaction ledger for an item with running balances.
    """
    return get_stock_ledger(db, item_id=item_id, from_date=from_date, to_date=to_date)


@router.post("/adjustments", response_model=StockMovementResponse, status_code=status.HTTP_201_CREATED)
def make_stock_adjustment(
    payload: StockAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ALLOW_ADJUST),
):
    """
    Posts an inventory adjustment with mandatory explanation reason (ADMIN only).
    Valued at prevailing weighted average cost.
    """
    return post_adjustment(
        db=db,
        item_id=payload.item_id,
        delta=payload.delta,
        reason=payload.reason,
        user=current_user,
        unit_cost_override=payload.unit_cost,
    )


@router.get("/reconcile", response_model=StockReconciliationResponse, dependencies=[Depends(ALLOW_RECONCILE)])
def reconcile_inventory(db: Session = Depends(get_db)):
    """
    Audit reconciliation endpoint:
    Verifies that every active item's ledger satisfies:
    opening + receipts - issues + adjustments == closing.
    """
    return reconcile_stock(db)
