from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.payment import Payment, PaymentAllocation, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentReverse,
)
from app.services import receivables as receivables_service

router = APIRouter(prefix="/payments", tags=["Payments & Receipts"])

ALLOW_ADMIN = require_roles(UserRole.ADMIN)
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_ADMIN)])
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Posts a customer payment (Admin only).
    - Gapless sequential receipt number (RCT/YYYY-YY/XXXX).
    - If allocations given: validates against invoice balances (409 on over-allocation).
    - If allocations omitted: auto-allocates FIFO (oldest open invoice first).
    - Any unallocated balance is stored as customer advance.
    - Payments are immutable once posted; wrong entries must be reversed.
    """
    return receivables_service.post_payment(db=db, payload=payload, user=current_user)


@router.get("", response_model=list[PaymentResponse], dependencies=[Depends(ALLOW_READ)])
def list_payments(
    customer_id: Optional[int] = Query(None),
    status_filter: Optional[PaymentStatus] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Lists payments with customer, status, and date range filters (Admin, Owner, Accountant).
    """
    stmt = (
        select(Payment)
        .options(selectinload(Payment.allocations), selectinload(Payment.customer))
        .order_by(desc(Payment.payment_date))
    )
    if customer_id:
        stmt = stmt.where(Payment.customer_id == customer_id)
    if status_filter:
        stmt = stmt.where(Payment.status == status_filter)
    if from_date:
        stmt = stmt.where(Payment.payment_date >= from_date)
    if to_date:
        stmt = stmt.where(Payment.payment_date <= to_date)

    stmt = stmt.offset(skip).limit(limit)
    payments = db.scalars(stmt).all()
    return [receivables_service.attach_payment_details(p) for p in payments]


@router.get("/{payment_id}", response_model=PaymentResponse, dependencies=[Depends(ALLOW_READ)])
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieves full details of a payment receipt including line-level invoice allocations.
    """
    payment = db.scalar(
        select(Payment)
        .options(selectinload(Payment.allocations), selectinload(Payment.customer))
        .where(Payment.id == payment_id)
    )
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payment {payment_id} not found")

    return receivables_service.attach_payment_details(payment)


@router.post("/{payment_id}/reverse", response_model=PaymentResponse, dependencies=[Depends(ALLOW_ADMIN)])
def reverse_payment(
    payment_id: int,
    payload: PaymentReverse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reverses an erroneous payment (Admin only).
    - Preserves payment row and allocation links for audit trail.
    - Status transitions to REVERSED, removing its effect from invoice and customer outstandings.
    """
    return receivables_service.reverse_payment(
        db=db, payment_id=payment_id, reason=payload.reason, user=current_user
    )
