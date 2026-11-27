from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import time
from typing import Optional, Union
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.bom import BOMItem
from app.models.invoice import Dispatch, DispatchStatus, Invoice, InvoiceStatus
from app.models.item import Item, ItemType
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.schemas.dashboard import (
    CostingMarginSummaryItem,
    DailySalesTrendItem,
    DashboardSummaryResponse,
    FinishedGoodStock,
    ReceivablesSummary,
    ReorderAlertItem,
    StockSummary,
    TodaySummary,
    TopDebtorCustomer,
    VarianceAlertSummaryItem,
)
from app.services.costing import product_cost_summary
from app.services.orders import available_to_promise
from app.services.production import get_default_tolerance
from app.services.receivables import get_receivables_ageing
from app.services.stock import get_balance

logger = logging.getLogger("dashboard_service")

# Short-lived 30-second cache
_CACHE: dict[str, tuple[float, DashboardSummaryResponse]] = {}
CACHE_TTL_SECONDS = 30


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(dt_val: Optional[Union[datetime, str]]) -> Optional[datetime]:
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        return ensure_utc(dt_val)
    dt_str = str(dt_val).strip()
    if not dt_str:
        return None
    if " " in dt_str and "+" not in dt_str and dt_str.count("-") >= 2:
        parts = dt_str.rsplit(" ", 1)
        if len(parts) == 2 and ":" in parts[1]:
            dt_str = f"{parts[0]}+{parts[1]}"
    try:
        dt = datetime.fromisoformat(dt_str)
        return ensure_utc(dt)
    except Exception:
        return None


def get_dashboard_summary(
    db: Session,
    as_of: Optional[Union[datetime, str]] = None,
    range_param: str = "today",
    use_cache: bool = True,
) -> DashboardSummaryResponse:
    """
    Computes comprehensive executive dashboard summary as of a target point in time:
    - today: orders received (count, value), pending approval, invoices raised, dispatches, payments collected
    - stock: finished goods on-hand & ATP; raw/packaging reorder alerts
    - variance_alerts: last 30 days of flagged production lines, newest first
    - receivables: total outstanding, statutory ageing buckets, top 5 debtors
    - costing: per-product cost per packet, selling price, commercial margin %
    - sales_trend: daily taxable sales for the last 30 days
    """
    target_date = parse_datetime(as_of) or datetime.now(timezone.utc)
    cache_key = f"{target_date.isoformat()}_{range_param}"

    now_ts = time.time()
    if use_cache and cache_key in _CACHE:
        cached_ts, cached_data = _CACHE[cache_key]
        if now_ts - cached_ts < CACHE_TTL_SECONDS:
            return cached_data

    # 1. TODAY OPERATIONAL SNAPSHOT (supports range_param: today, 7d, 30d, mtd)
    start_of_day = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_of_day = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

    if range_param == "7d":
        start_of_period = start_of_day - timedelta(days=6)
    elif range_param == "30d":
        start_of_period = start_of_day - timedelta(days=29)
    elif range_param == "mtd":
        start_of_period = datetime(target_date.year, target_date.month, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:  # "today"
        start_of_period = start_of_day

    date_str = start_of_day.strftime("%Y-%m-%d")

    # Orders received today / period
    orders_stmt = select(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_amount_paise), 0),
    ).where(
        Order.order_date >= start_of_period,
        Order.order_date <= end_of_day,
        Order.status != OrderStatus.CANCELLED,
    )
    order_res = db.execute(orders_stmt).one()
    orders_count = int(order_res[0] or 0)
    orders_val = int(order_res[1] or 0)

    # Orders pending approval
    pending_stmt = select(func.count(Order.id)).where(
        Order.status == OrderStatus.SUBMITTED,
        Order.order_date <= end_of_day,
    )
    orders_pending = int(db.scalar(pending_stmt) or 0)

    # Invoices raised today / period
    inv_stmt = select(
        func.count(Invoice.id),
        func.coalesce(func.sum(Invoice.grand_total_paise), 0),
    ).where(
        Invoice.invoice_date >= start_of_period,
        Invoice.invoice_date <= end_of_day,
        Invoice.status == InvoiceStatus.POSTED,
    )
    inv_res = db.execute(inv_stmt).one()
    inv_count = int(inv_res[0] or 0)
    inv_val = int(inv_res[1] or 0)

    # Dispatches made today / period
    disp_stmt = select(func.count(Dispatch.id)).where(
        Dispatch.dispatch_date >= start_of_period,
        Dispatch.dispatch_date <= end_of_day,
        Dispatch.status == DispatchStatus.DISPATCHED,
    )
    disp_count = int(db.scalar(disp_stmt) or 0)

    # Payments collected today / period
    pay_stmt = select(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount_paise), 0),
    ).where(
        Payment.payment_date >= start_of_period,
        Payment.payment_date <= end_of_day,
        Payment.status == PaymentStatus.POSTED,
    )
    pay_res = db.execute(pay_stmt).one()
    pay_count = int(pay_res[0] or 0)
    pay_val = int(pay_res[1] or 0)

    today_summary = TodaySummary(
        date=date_str,
        orders_received_count=orders_count,
        orders_received_value_paise=orders_val,
        orders_pending_approval_count=orders_pending,
        invoices_raised_count=inv_count,
        invoices_raised_value_paise=inv_val,
        dispatches_made_count=disp_count,
        payments_collected_paise=pay_val,
        payments_collected_count=pay_count,
    )

    # 2. STOCK SUMMARY (Finished Goods ATP + Raw/Packaging Reorder Alerts)
    products = db.scalars(
        select(Product).options(selectinload(Product.item)).order_by(Product.id.asc())
    ).all()
    fg_stocks: list[FinishedGoodStock] = []
    for p in products:
        atp = available_to_promise(db, p.id)
        prod_name = p.item.name if p.item else f"Product {p.id}"
        fg_stocks.append(
            FinishedGoodStock(
                product_id=p.id,
                product_name=prod_name,
                item_id=p.item_id,
                pack_size_desc=p.pack_size_desc,
                on_hand_packets=atp["on_hand"],
                committed_packets=atp["committed_elsewhere"],
                available_to_promise_packets=atp["available"],
            )
        )

    raw_items = db.scalars(
        select(Item).where(
            Item.item_type.in_([ItemType.RAW_MATERIAL, ItemType.PACKAGING]),
            Item.is_active == True,
        ).order_by(Item.name.asc())
    ).all()

    reorder_alerts: list[ReorderAlertItem] = []
    items_with_balance = []
    for itm in raw_items:
        cur_bal = get_balance(db, itm.id)
        deficit = None
        is_below = False
        if itm.reorder_level is not None:
            if cur_bal < itm.reorder_level:
                deficit = itm.reorder_level - cur_bal
                is_below = True
        items_with_balance.append((itm, cur_bal, deficit, is_below))

    # Add items below reorder level
    below_items = [x for x in items_with_balance if x[3]]
    if below_items:
        for itm, cur_bal, deficit, _ in below_items:
            reorder_alerts.append(
                ReorderAlertItem(
                    item_id=itm.id,
                    item_name=itm.name,
                    item_type=itm.item_type.value,
                    base_unit=itm.base_unit,
                    display_unit=itm.display_unit,
                    current_stock_base=cur_bal,
                    reorder_level_base=itm.reorder_level,
                    deficit_base=deficit,
                )
            )
    else:
        # If no items below explicit reorder level, show the 5 lowest stock items
        lowest = sorted(items_with_balance, key=lambda x: x[1])[:5]
        for itm, cur_bal, deficit, _ in lowest:
            reorder_alerts.append(
                ReorderAlertItem(
                    item_id=itm.id,
                    item_name=itm.name,
                    item_type=itm.item_type.value,
                    base_unit=itm.base_unit,
                    display_unit=itm.display_unit,
                    current_stock_base=cur_bal,
                    reorder_level_base=itm.reorder_level,
                    deficit_base=deficit,
                )
            )

    stock_summary = StockSummary(
        finished_goods=fg_stocks,
        reorder_alerts=reorder_alerts,
    )

    # 3. VARIANCE ALERTS (Last 30 days of flagged production lines, newest first)
    start_30_var = target_date - timedelta(days=30)
    runs_stmt = (
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.product).selectinload(Product.item),
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
        )
        .where(
            ProductionRun.run_date >= start_30_var,
            ProductionRun.run_date <= target_date,
        )
        .order_by(desc(ProductionRun.run_date), desc(ProductionRun.id))
    )
    runs = db.scalars(runs_stmt).all()
    default_tolerance = get_default_tolerance(db)
    variance_items: list[VarianceAlertSummaryItem] = []

    for r in runs:
        bom_items = db.scalars(select(BOMItem).where(BOMItem.bom_id == r.bom_id)).all()
        tolerance_map = {bi.item_id: bi.variance_tolerance_pct for bi in bom_items}
        prod_name = r.product.item.name if r.product and r.product.item else f"Product {r.product_id}"

        for line in r.lines:
            if line.is_flagged:
                eff_tol = tolerance_map.get(line.item_id) or default_tolerance
                variance_items.append(
                    VarianceAlertSummaryItem(
                        run_id=r.id,
                        run_no=r.run_no,
                        run_date=r.run_date,
                        product_name=prod_name,
                        item_id=line.item_id,
                        item_name=line.item.name if line.item else f"Item {line.item_id}",
                        planned_qty_base=line.planned_qty_base,
                        actual_qty_base=line.actual_qty_base or 0,
                        difference_qty_base=line.variance_qty_base or 0,
                        variance_pct=line.variance_pct or Decimal("0.00"),
                        display_unit=line.unit_for_display,
                        tolerance_pct=eff_tol,
                    )
                )

    # 4. RECEIVABLES & AGEING (Total outstanding, statutory buckets, top 5 debtors)
    ageing = get_receivables_ageing(db, as_of=target_date)
    top_debtors_raw = [c for c in ageing.customers if c.total_outstanding_paise > 0]
    top_debtors_raw.sort(key=lambda c: c.total_outstanding_paise, reverse=True)
    top_debtors = [
        TopDebtorCustomer(
            customer_id=c.customer_id,
            customer_name=c.customer_name,
            total_outstanding_paise=c.total_outstanding_paise,
            oldest_invoice_date=c.oldest_invoice_date,
        )
        for c in top_debtors_raw[:5]
    ]

    receivables_summary = ReceivablesSummary(
        total_outstanding_paise=ageing.grand_total_outstanding_paise,
        bucket_0_30_paise=ageing.total_bucket_0_30_paise,
        bucket_31_60_paise=ageing.total_bucket_31_60_paise,
        bucket_61_90_paise=ageing.total_bucket_61_90_paise,
        bucket_90_plus_paise=ageing.total_bucket_90_plus_paise,
        unallocated_advance_paise=ageing.total_unallocated_advance_paise,
        top_debtors=top_debtors,
    )

    # 5. COSTING & COMMERCIAL MARGINS PER PRODUCT
    costing_items: list[CostingMarginSummaryItem] = []
    for p in products:
        c_sum = product_cost_summary(db, p.id, to_date=target_date)
        costing_items.append(
            CostingMarginSummaryItem(
                product_id=p.id,
                product_name=c_sum.product_name,
                cost_per_packet=c_sum.cost_per_packet,
                selling_price=c_sum.selling_price,
                margin_per_packet=c_sum.margin_per_packet,
                margin_pct=c_sum.margin_pct,
            )
        )

    # 6. SALES TREND (Daily taxable sales for the last 30 days)
    start_30_sales = (target_date - timedelta(days=29)).date()
    end_sales_dt = target_date.date()

    # Query posted invoices in window
    invoices_30 = db.scalars(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.POSTED,
            Invoice.invoice_date >= datetime(start_30_sales.year, start_30_sales.month, start_30_sales.day, 0, 0, 0, tzinfo=timezone.utc),
            Invoice.invoice_date <= end_of_day,
        )
    ).all()

    daily_sales_map: dict[str, dict[str, int]] = {}
    # Pre-populate all 30 days
    curr = start_30_sales
    while curr <= end_sales_dt:
        d_str = curr.strftime("%Y-%m-%d")
        daily_sales_map[d_str] = {"taxable": 0, "count": 0}
        curr += timedelta(days=1)

    for inv in invoices_30:
        inv_d_str = ensure_utc(inv.invoice_date).strftime("%Y-%m-%d")
        if inv_d_str in daily_sales_map:
            daily_sales_map[inv_d_str]["taxable"] += inv.taxable_total_paise
            daily_sales_map[inv_d_str]["count"] += 1

    sales_trend = [
        DailySalesTrendItem(
            date=d_key,
            taxable_sales_paise=data["taxable"],
            taxable_sales_rupees=(Decimal(data["taxable"]) / Decimal("100")).quantize(Decimal("0.01")),
            invoice_count=data["count"],
        )
        for d_key, data in sorted(daily_sales_map.items())
    ]

    response = DashboardSummaryResponse(
        as_of=target_date,
        today=today_summary,
        stock=stock_summary,
        variance_alerts=variance_items,
        receivables=receivables_summary,
        costing=costing_items,
        sales_trend=sales_trend,
    )

    if use_cache:
        _CACHE[cache_key] = (now_ts, response)

    return response


def clear_dashboard_cache() -> None:
    """Clears the short-lived in-memory dashboard cache."""
    _CACHE.clear()
