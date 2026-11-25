from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.order import Order, OrderLine, OrderStatus
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import (
    OrderApprove,
    OrderCreate,
    OrderReject,
    OrderResponse,
    OrderUpdate,
)
from app.schemas.invoice import InvoiceResponse
from app.services import orders as order_service
from app.services import invoicing as invoicing_service

router = APIRouter(prefix="/orders", tags=["Orders"])

# RBAC Permissions:
# Read orders: ADMIN, OWNER, ACCOUNTANT, PRODUCTION
# Create order: SALESMAN, ADMIN
# Manage/Edit/Approve/Reject: ADMIN only
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)
ALLOW_CREATE = require_roles(UserRole.SALESMAN, UserRole.ADMIN)
ALLOW_ADMIN = require_roles(UserRole.ADMIN)


@router.post("", response_model=OrderResponse, dependencies=[Depends(ALLOW_CREATE)])
def create_order(
    payload: OrderCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submits a new sales order with client_uuid idempotency key.
    Re-posting the same client_uuid returns the existing order with HTTP 200.
    """
    order, is_duplicate = order_service.create_order(db=db, payload=payload, salesman=current_user)
    response.status_code = status.HTTP_200_OK if is_duplicate else status.HTTP_201_CREATED
    return order


@router.get("", response_model=list[OrderResponse], dependencies=[Depends(ALLOW_READ)])
def list_orders(
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    salesman_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Lists orders with optional status, salesman, customer, and date filters.
    Available to ADMIN, OWNER, ACCOUNTANT, and PRODUCTION roles.
    """
    stmt = (
        select(Order)
        .options(
            selectinload(Order.lines).selectinload(OrderLine.product).selectinload(Product.item),
            selectinload(Order.customer),
            selectinload(Order.salesman),
            selectinload(Order.status_history),
        )
        .order_by(desc(Order.order_date))
    )
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if salesman_id:
        stmt = stmt.where(Order.salesman_id == salesman_id)
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if from_date:
        stmt = stmt.where(Order.order_date >= from_date)
    if to_date:
        stmt = stmt.where(Order.order_date <= to_date)

    stmt = stmt.offset(skip).limit(limit)
    orders = db.scalars(stmt).all()
    for o in orders:
        order_service.attach_order_details(db, o)
    return orders


@router.get("/{order_id}", response_model=OrderResponse, dependencies=[Depends(ALLOW_READ)])
def get_order(order_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a single order with detailed stock availability block per line
    and estimated GST tax split.
    """
    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.lines).selectinload(OrderLine.product).selectinload(Product.item),
            selectinload(Order.customer),
            selectinload(Order.salesman),
            selectinload(Order.status_history),
        )
        .where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")

    return order_service.attach_order_details(db, order)


@router.patch("/{order_id}", response_model=OrderResponse, dependencies=[Depends(ALLOW_ADMIN)])
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Admin edit of draft order quantities or prices while in SUBMITTED status.
    Audits all changes with before/after state and marks price_source as ADMIN_EDIT.
    """
    return order_service.update_order(db=db, order_id=order_id, payload=payload, user=current_user)


@router.post("/{order_id}/approve", response_model=OrderResponse, dependencies=[Depends(ALLOW_ADMIN)])
def approve_order(
    order_id: int,
    payload: Optional[OrderApprove] = None,
    approve_with_shortage: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Approves an order atomically with item row-level locks.
    Blocks with HTTP 409 if any line has insufficient Available-to-Promise (ATP) stock,
    unless approve_with_shortage=True is explicitly confirmed.
    """
    override = approve_with_shortage or (payload.approve_with_shortage if payload else False)
    return order_service.approve_order(
        db=db, order_id=order_id, user=current_user, approve_with_shortage=override
    )


@router.post("/{order_id}/reject", response_model=OrderResponse, dependencies=[Depends(ALLOW_ADMIN)])
def reject_order(
    order_id: int,
    payload: OrderReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rejects an order (Admin only). Requires a reason of at least 3 characters.
    """
    return order_service.reject_order(db=db, order_id=order_id, reason=payload.reason, user=current_user)
