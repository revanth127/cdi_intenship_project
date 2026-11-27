from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.order import Order, OrderLine, OrderStatus
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import (
    CustomerSalesSummaryResponse,
    OrderResponse,
    SalesmanCustomerResponse,
    SalesmanProductResponse,
)
from app.services import orders as order_service

router = APIRouter(prefix="/me", tags=["Salesman Mobile"])

ALLOW_SALESMAN = require_roles(UserRole.SALESMAN)


@router.get("/customers", response_model=list[SalesmanCustomerResponse], dependencies=[Depends(ALLOW_SALESMAN)])
def get_my_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns active customers assigned to the currently authenticated salesman.
    """
    return order_service.get_salesman_customers(db=db, salesman_id=current_user.id)


@router.get("/products", response_model=list[SalesmanProductResponse], dependencies=[Depends(ALLOW_SALESMAN)])
def get_products_for_customer(
    customer_id: int = Query(..., description="Target customer to resolve effective pricing for"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all active finished goods products with effective pricing resolved
    for the specified customer (Customer override first, then standard Price list).
    """
    return order_service.get_salesman_products_with_prices(db=db, customer_id=customer_id)


@router.get("/orders", response_model=list[OrderResponse], dependencies=[Depends(ALLOW_SALESMAN)])
def get_my_orders(
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Paginated list of orders placed by the current salesman.
    """
    stmt = (
        select(Order)
        .options(
            selectinload(Order.lines).selectinload(OrderLine.product).selectinload(Product.item),
            selectinload(Order.customer),
            selectinload(Order.salesman),
            selectinload(Order.status_history),
        )
        .where(Order.salesman_id == current_user.id)
        .order_by(desc(Order.order_date))
    )
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if from_date:
        stmt = stmt.where(Order.order_date >= from_date)
    if to_date:
        stmt = stmt.where(Order.order_date <= to_date)

    stmt = stmt.offset(skip).limit(limit)
    orders = db.scalars(stmt).all()
    for o in orders:
        order_service.attach_order_details(db, o)
    return orders


@router.get("/orders/{order_id}", response_model=OrderResponse, dependencies=[Depends(ALLOW_SALESMAN)])
def get_my_order_detail(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves full details of an order placed by the current salesman.
    Returns 404 (not 403) if the order belongs to another salesman to prevent leaking order existence.
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
    # Salesman isolation: return 404 to avoid leaking existence
    if not order or (current_user.role == UserRole.SALESMAN and order.salesman_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order_service.attach_order_details(db, order)


@router.get(
    "/sales/customer-wise",
    response_model=list[CustomerSalesSummaryResponse],
    dependencies=[Depends(ALLOW_SALESMAN)],
)
def get_my_customer_sales(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregates salesman orders customer-wise (order count and total value in paise).
    Excludes REJECTED and CANCELLED orders.
    """
    return order_service.get_salesman_sales_summary(
        db=db, salesman_id=current_user.id, from_date=from_date, to_date=to_date
    )
