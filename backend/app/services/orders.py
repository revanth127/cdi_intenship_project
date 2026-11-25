from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.company import CompanySettings
from app.models.customer import Customer
from app.models.item import Item
from app.models.order import (
    NumberingSequence,
    Order,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
    PriceSource,
)
from app.models.pricing import CustomerPriceOverride, PriceList, PriceListItem
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import (
    CustomerSalesSummaryResponse,
    OrderCreate,
    OrderLineUpdate,
    OrderUpdate,
    SalesmanCustomerResponse,
    SalesmanProductResponse,
    StockAvailabilityLine,
    TaxSummaryResponse,
)
from app.services.audit import log_audit
from app.services.stock import get_balance
from app.utils.gst import compute_order_tax_summary

logger = logging.getLogger("orders_service")


def get_financial_year(date: Optional[datetime] = None, fy_start_month: int = 4) -> tuple[int, str]:
    """
    Computes financial year based on transaction date and starting month (default April = 4).
    Returns (start_year, "YYYY-YY") e.g. (2026, "2026-27").
    """
    dt = date or datetime.now(timezone.utc)
    if dt.month >= fy_start_month:
        start_year = dt.year
        end_year = dt.year + 1
    else:
        start_year = dt.year - 1
        end_year = dt.year
    fy_str = f"{start_year}-{str(end_year)[-2:]}"
    return start_year, fy_str


def get_next_order_number(db: Session, order_date: Optional[datetime] = None) -> str:
    """
    Generates a gapless, race-free order number per financial year (e.g. ORD-2026-0001).
    Uses row-level locking (SELECT ... FOR UPDATE) on numbering_sequences.
    """
    company = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    fy_start_month = company.financial_year_start_month if company else 4
    start_year, fy_str = get_financial_year(order_date, fy_start_month)

    # Row lock on the sequence row
    seq_row = db.scalar(
        select(NumberingSequence)
        .where(
            NumberingSequence.sequence_name == "ORDER",
            NumberingSequence.financial_year == fy_str,
        )
        .with_for_update()
    )

    if not seq_row:
        seq_row = NumberingSequence(
            sequence_name="ORDER",
            financial_year=fy_str,
            last_number=1,
        )
        db.add(seq_row)
        db.flush()
        next_val = 1
    else:
        seq_row.last_number += 1
        next_val = seq_row.last_number
        db.flush()

    return f"ORD-{start_year}-{next_val:04d}"


def get_effective_product_price(
    db: Session, customer_id: int, product_id: int, as_of: Optional[datetime] = None
) -> tuple[int, PriceSource]:
    """
    Looks up the effective price in paise for a customer and product:
    1. Customer-specific price override (if active on date) -> CUSTOMER_OVERRIDE
    2. Active Price list item (standard/default list) -> PRICE_LIST
    """
    target_date = as_of or datetime.now(timezone.utc)

    # 1. Customer Price Override
    override = db.scalar(
        select(CustomerPriceOverride)
        .where(
            CustomerPriceOverride.customer_id == customer_id,
            CustomerPriceOverride.product_id == product_id,
            CustomerPriceOverride.effective_from <= target_date,
            (
                CustomerPriceOverride.effective_to.is_(None)
                | (CustomerPriceOverride.effective_to >= target_date)
            ),
        )
        .order_by(desc(CustomerPriceOverride.effective_from))
        .limit(1)
    )
    if override:
        return override.price_paise, PriceSource.CUSTOMER_OVERRIDE

    # 2. Price List Item
    pli = db.scalar(
        select(PriceListItem)
        .join(PriceList, PriceList.id == PriceListItem.price_list_id)
        .where(
            PriceListItem.product_id == product_id,
            PriceList.is_active.is_(True),
            PriceListItem.effective_from <= target_date,
            (
                PriceListItem.effective_to.is_(None)
                | (PriceListItem.effective_to >= target_date)
            ),
        )
        .order_by(desc(PriceList.is_default), desc(PriceListItem.effective_from))
        .limit(1)
    )
    if pli:
        return pli.price_paise, PriceSource.PRICE_LIST

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"No active price list or override found for Product {product_id}",
    )


def available_to_promise(
    db: Session, product_id: int, exclude_order_id: Optional[int] = None
) -> dict[str, int]:
    """
    Computes Available-to-Promise (ATP) inventory for a finished product:
      ATP = finished_goods_ledger_balance - quantity_committed_to_orders_in_APPROVED_or_INVOICED
    """
    product = db.scalar(select(Product).options(selectinload(Product.item)).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {product_id} not found")

    on_hand = get_balance(db, product.item_id)

    # Quantity committed to orders in APPROVED or INVOICED status not yet dispatched
    stmt = (
        select(func.coalesce(func.sum(OrderLine.quantity_packets), 0))
        .join(Order, Order.id == OrderLine.order_id)
        .where(
            OrderLine.product_id == product_id,
            Order.status.in_([OrderStatus.APPROVED, OrderStatus.INVOICED]),
        )
    )
    if exclude_order_id:
        stmt = stmt.where(Order.id != exclude_order_id)

    committed = int(db.scalar(stmt) or 0)
    available = on_hand - committed

    return {
        "on_hand": on_hand,
        "committed_elsewhere": committed,
        "available": available,
    }


def check_order_stock_availability(db: Session, order: Order) -> list[StockAvailabilityLine]:
    """
    Computes per-line stock availability report for an order:
    Returns requested, on_hand, committed_elsewhere, available, shortage, ok.
    """
    results = []
    for line in order.lines:
        atp = available_to_promise(db, line.product_id, exclude_order_id=order.id)
        product_name = line.product.item.name if (line.product and line.product.item) else f"Product {line.product_id}"
        requested = line.quantity_packets
        available = atp["available"]
        shortage = max(0, requested - available)
        ok = shortage == 0

        line_avail = StockAvailabilityLine(
            product_id=line.product_id,
            product_name=product_name,
            requested=requested,
            on_hand=atp["on_hand"],
            committed_elsewhere=atp["committed_elsewhere"],
            available=available,
            shortage=shortage,
            ok=ok,
        )
        # Also attach to line object for line-level serialization
        line.stock_availability = line_avail
        line.product_name = product_name
        results.append(line_avail)

    return results


def attach_order_details(db: Session, order: Order) -> Order:
    """
    Enriches Order instance with:
    1. Estimated taxable value and GST split (using utils/gst.py)
    2. Per-line and order-level stock availability block
    3. Customer and Salesman human-readable names
    """
    company = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    company_state = company.state_code if company else "33"
    customer_state = order.customer.state_code if order.customer else "33"

    # Compute GST summary
    tax_lines = []
    for line in order.lines:
        rate_bp = line.product.item.gst_rate_bp if (line.product and line.product.item) else 0
        tax_lines.append({
            "line_total_paise": line.line_total_paise,
            "gst_rate_bp": rate_bp,
        })
    tax_dict = compute_order_tax_summary(tax_lines, company_state, customer_state)
    order.estimated_tax = TaxSummaryResponse(**tax_dict)

    # Compute stock availability
    order.stock_availability = check_order_stock_availability(db, order)

    # Names
    order.customer_name = order.customer.name if order.customer else None
    order.salesman_name = order.salesman.full_name if order.salesman else None

    return order


def create_order(db: Session, payload: OrderCreate, salesman: User) -> tuple[Order, bool]:
    """
    Creates an order placed by a salesman.
    - Idempotency: Re-posting the same client_uuid returns the existing order (is_duplicate = True).
    - Salesman can only place orders for assigned customers.
    - Server looks up all prices; client prices are completely ignored.
    """
    # 1. Idempotency Check via client_uuid
    existing = db.scalar(
        select(Order)
        .options(
            selectinload(Order.lines).selectinload(OrderLine.product).selectinload(Product.item),
            selectinload(Order.customer),
            selectinload(Order.salesman),
            selectinload(Order.status_history),
        )
        .where(Order.client_uuid == payload.client_uuid)
    )
    if existing:
        if salesman.role == UserRole.SALESMAN and existing.salesman_id != salesman.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        return attach_order_details(db, existing), True

    # 2. Customer Validation & Assignment Check
    customer = db.scalar(select(Customer).where(Customer.id == payload.customer_id))
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {payload.customer_id} not found")
    if not customer.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot order for inactive customer")

    if salesman.role == UserRole.SALESMAN and customer.assigned_salesman_id != salesman.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Salesman {salesman.id} is not assigned to Customer {customer.id} ({customer.name})",
        )

    # 3. Gapless order number generation
    order_no = get_next_order_number(db)
    now = datetime.now(timezone.utc)

    order = Order(
        order_no=order_no,
        client_uuid=payload.client_uuid,
        customer_id=customer.id,
        salesman_id=salesman.id,
        order_date=now,
        status=OrderStatus.SUBMITTED,
        notes=payload.notes,
        total_amount_paise=0,
    )

    total_amount_paise = 0
    for line_in in payload.lines:
        product = db.scalar(
            select(Product).options(selectinload(Product.item)).where(Product.id == line_in.product_id)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {line_in.product_id} not found",
            )
        unit_price_paise, source = get_effective_product_price(db, customer.id, product.id, as_of=now)
        line_total = line_in.quantity_packets * unit_price_paise
        total_amount_paise += line_total

        order_line = OrderLine(
            product_id=product.id,
            quantity_packets=line_in.quantity_packets,
            unit_price_paise=unit_price_paise,
            line_total_paise=line_total,
            price_source=source,
        )
        order.lines.append(order_line)

    order.total_amount_paise = total_amount_paise

    # Initial status history record
    history = OrderStatusHistory(
        from_status=None,
        to_status=OrderStatus.SUBMITTED,
        user_id=salesman.id,
        timestamp=now,
        notes="Order submitted by salesman",
    )
    order.status_history.append(history)

    db.add(order)
    db.commit()
    db.refresh(order)

    # Audit log
    log_audit(
        db=db,
        user=salesman,
        action="ORDER_CREATED",
        entity_type="Order",
        entity_id=order.id,
        new_values={
            "order_no": order.order_no,
            "client_uuid": order.client_uuid,
            "customer_id": order.customer_id,
            "total_amount_paise": order.total_amount_paise,
            "status": order.status.value,
        },
    )

    return attach_order_details(db, order), False


def update_order(db: Session, order_id: int, payload: OrderUpdate, user: User) -> Order:
    """
    Edits quantities or prices of an order while in SUBMITTED status (Admin only).
    Logs all edits to audit_log with old and new values.
    Marks price_source as ADMIN_EDIT when price is modified.
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

    if order.status != OrderStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit order {order.order_no} with status {order.status.value}. Only SUBMITTED orders can be edited.",
        )

    old_values = {
        "notes": order.notes,
        "total_amount_paise": order.total_amount_paise,
        "lines": [
            {
                "product_id": l.product_id,
                "quantity_packets": l.quantity_packets,
                "unit_price_paise": l.unit_price_paise,
                "price_source": l.price_source.value,
            }
            for l in order.lines
        ],
    }

    if payload.notes is not None:
        order.notes = payload.notes

    if payload.lines is not None:
        line_map = {l.product_id: l for l in order.lines}
        new_lines = []
        total_paise = 0

        for line_in in payload.lines:
            if line_in.product_id in line_map:
                line = line_map[line_in.product_id]
                line.quantity_packets = line_in.quantity_packets
                if line_in.unit_price_paise is not None and line_in.unit_price_paise != line.unit_price_paise:
                    line.unit_price_paise = line_in.unit_price_paise
                    line.price_source = PriceSource.ADMIN_EDIT
                line.line_total_paise = line.quantity_packets * line.unit_price_paise
                total_paise += line.line_total_paise
                new_lines.append(line)
            else:
                # New line added by admin
                product = db.scalar(
                    select(Product).options(selectinload(Product.item)).where(Product.id == line_in.product_id)
                )
                if not product:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {line_in.product_id} not found"
                    )
                price = (
                    line_in.unit_price_paise
                    if line_in.unit_price_paise is not None
                    else get_effective_product_price(db, order.customer_id, product.id)[0]
                )
                src = PriceSource.ADMIN_EDIT if line_in.unit_price_paise is not None else PriceSource.PRICE_LIST
                ltotal = line_in.quantity_packets * price
                total_paise += ltotal
                new_line = OrderLine(
                    product_id=product.id,
                    quantity_packets=line_in.quantity_packets,
                    unit_price_paise=price,
                    line_total_paise=ltotal,
                    price_source=src,
                )
                order.lines.append(new_line)
                new_lines.append(new_line)

        order.lines = new_lines
        order.total_amount_paise = total_paise

    new_values = {
        "notes": order.notes,
        "total_amount_paise": order.total_amount_paise,
        "lines": [
            {
                "product_id": l.product_id,
                "quantity_packets": l.quantity_packets,
                "unit_price_paise": l.unit_price_paise,
                "price_source": l.price_source.value,
            }
            for l in order.lines
        ],
    }

    log_audit(
        db=db,
        user=user,
        action="ORDER_UPDATED",
        entity_type="Order",
        entity_id=order.id,
        old_values=old_values,
        new_values=new_values,
    )

    db.commit()
    db.refresh(order)
    return attach_order_details(db, order)


def approve_order(
    db: Session, order_id: int, user: User, approve_with_shortage: bool = False
) -> Order:
    """
    Approves an order in ONE transaction:
    - Row-locks finished goods Item records (SELECT ... FOR UPDATE) to prevent race conditions.
    - Evaluates Available-to-Promise (ATP).
    - Blocks with HTTP 409 if any line is short, unless approve_with_shortage=True is explicitly confirmed.
    - Updates order status to APPROVED and records status history and audit log.
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

    if order.status != OrderStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve order {order.order_no} with status {order.status.value}. Only SUBMITTED orders can be approved.",
        )

    # 1. Acquire row lock on each product's Item row (SELECT ... FOR UPDATE)
    for line in order.lines:
        if line.product and line.product.item_id:
            db.scalar(
                select(Item).where(Item.id == line.product.item_id).with_for_update()
            )

    # 2. Check stock availability against ATP
    shortages = []
    for line in order.lines:
        atp = available_to_promise(db, line.product_id, exclude_order_id=order.id)
        shortage = max(0, line.quantity_packets - atp["available"])
        if shortage > 0:
            product_name = line.product.item.name if (line.product and line.product.item) else f"Product {line.product_id}"
            shortages.append(
                {
                    "product_id": line.product_id,
                    "product_name": product_name,
                    "requested": line.quantity_packets,
                    "on_hand": atp["on_hand"],
                    "committed_elsewhere": atp["committed_elsewhere"],
                    "available": atp["available"],
                    "shortage": shortage,
                    "ok": False,
                }
            )

    if shortages and not approve_with_shortage:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Insufficient stock for order approval",
                "shortages": shortages,
            },
        )

    from_status = order.status
    now = datetime.now(timezone.utc)
    order.status = OrderStatus.APPROVED
    order.approved_by = user.id
    order.approved_at = now

    notes = "Approved by admin"
    if shortages:
        notes += " (approved with shortage override)"

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.APPROVED,
        user_id=user.id,
        timestamp=now,
        notes=notes,
    )
    order.status_history.append(history)

    log_audit(
        db=db,
        user=user,
        action="ORDER_APPROVED",
        entity_type="Order",
        entity_id=order.id,
        old_values={"status": from_status.value},
        new_values={
            "status": OrderStatus.APPROVED.value,
            "approved_by": user.id,
            "approved_at": str(now),
            "approved_with_shortage": bool(shortages),
        },
    )

    db.commit()
    db.refresh(order)
    return attach_order_details(db, order)


def reject_order(db: Session, order_id: int, reason: str, user: User) -> Order:
    """
    Rejects an order (Admin only).
    Requires an explicit rejection reason (min 3 chars).
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

    if order.status != OrderStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject order {order.order_no} with status {order.status.value}. Only SUBMITTED orders can be rejected.",
        )

    if not reason or len(reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A non-empty rejection reason of at least 3 characters is required.",
        )

    from_status = order.status
    now = datetime.now(timezone.utc)
    order.status = OrderStatus.REJECTED
    order.rejection_reason = reason.strip()

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.REJECTED,
        user_id=user.id,
        timestamp=now,
        notes=f"Rejected: {order.rejection_reason}",
    )
    order.status_history.append(history)

    log_audit(
        db=db,
        user=user,
        action="ORDER_REJECTED",
        entity_type="Order",
        entity_id=order.id,
        old_values={"status": from_status.value},
        new_values={
            "status": OrderStatus.REJECTED.value,
            "rejection_reason": order.rejection_reason,
        },
    )

    db.commit()
    db.refresh(order)
    return attach_order_details(db, order)


def get_salesman_customers(db: Session, salesman_id: int) -> list[SalesmanCustomerResponse]:
    """Returns active customers assigned to a specific salesman."""
    stmt = (
        select(Customer)
        .where(
            Customer.assigned_salesman_id == salesman_id,
            Customer.is_active.is_(True),
        )
        .order_by(Customer.name.asc())
    )
    customers = db.scalars(stmt).all()
    return [SalesmanCustomerResponse.model_validate(c) for c in customers]


def get_salesman_products_with_prices(
    db: Session, customer_id: int
) -> list[SalesmanProductResponse]:
    """
    Returns active finished products along with the customer's effective price.
    Checks customer override first, then standard price list.
    """
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    products = db.scalars(
        select(Product)
        .join(Item, Item.id == Product.item_id)
        .options(selectinload(Product.item))
        .where(Item.is_active.is_(True))
        .order_by(Item.name.asc())
    ).all()

    now = datetime.now(timezone.utc)
    results = []
    for prod in products:
        try:
            price_paise, source = get_effective_product_price(db, customer_id, prod.id, as_of=now)
            results.append(
                SalesmanProductResponse(
                    product_id=prod.id,
                    name=prod.item.name,
                    pack_size_desc=prod.pack_size_desc,
                    packets_per_carton=prod.packets_per_carton,
                    price_paise=price_paise,
                    price_source=source,
                )
            )
        except HTTPException:
            continue

    return results


def get_salesman_sales_summary(
    db: Session,
    salesman_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[CustomerSalesSummaryResponse]:
    """
    Aggregates order counts and total value customer-wise for a salesman.
    Excludes REJECTED and CANCELLED orders.
    """
    stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_amount_paise), 0).label("total_value_paise"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .where(
            Order.salesman_id == salesman_id,
            Order.status.notin_([OrderStatus.REJECTED, OrderStatus.CANCELLED]),
        )
        .group_by(Customer.id, Customer.name)
        .order_by(desc("total_value_paise"))
    )
    if from_date:
        stmt = stmt.where(Order.order_date >= from_date)
    if to_date:
        stmt = stmt.where(Order.order_date <= to_date)

    rows = db.execute(stmt).all()
    return [
        CustomerSalesSummaryResponse(
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            order_count=r.order_count,
            total_value_paise=r.total_value_paise,
        )
        for r in rows
    ]
