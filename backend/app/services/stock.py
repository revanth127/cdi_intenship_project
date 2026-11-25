from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.item import Item, ItemType
from app.models.stock import MovementType, StockMovement
from app.models.user import User
from app.services.audit import log_audit
from app.utils.units import from_base

logger = logging.getLogger("stock_service")


class InsufficientStockError(HTTPException):
    """Raised when an inventory issue would result in negative stock."""
    def __init__(self, item_id: int, available: int, requested: int, item_name: str = ""):
        detail = {
            "error": "Insufficient stock",
            "item_id": item_id,
            "item_name": item_name,
            "available_base": available,
            "requested_base": requested,
            "message": f"Cannot issue {requested} base units for item {item_id}; only {available} available.",
        }
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def get_balance(db: Session, item_id: int, as_of: Optional[datetime] = None) -> int:
    """
    Computes the current stock balance in BASE UNITS as the sum of all immutable ledger entries.
    Supports point-in-time 'as_of' audits.
    """
    stmt = select(func.coalesce(func.sum(StockMovement.quantity_base), 0)).where(
        StockMovement.item_id == item_id
    )
    if as_of:
        stmt = stmt.where(StockMovement.movement_date <= as_of)
    return int(db.scalar(stmt) or 0)


def get_valuation(db: Session, item_id: int, as_of: Optional[datetime] = None) -> dict[str, Any]:
    """
    Computes the Moving Weighted Average Cost and total inventory valuation.
    
    Valuation Method: 'Moving Weighted Average'
    - Receipts increase total quantity and total monetary value. The new unit cost is:
        (Previous Inventory Value + Receipt Value) / (Previous Quantity + Receipt Quantity)
    - Issues decrease quantity and value at the prevailing average cost.
    - All calculations maintain 6 decimal places of precision (Numeric(18,6)) in paise per base unit.
    """
    stmt = (
        select(StockMovement)
        .where(StockMovement.item_id == item_id)
        .order_by(StockMovement.movement_date.asc(), StockMovement.id.asc())
    )
    if as_of:
        stmt = stmt.where(StockMovement.movement_date <= as_of)

    movements = db.scalars(stmt).all()

    current_qty = 0
    current_val_paise = Decimal("0")
    current_unit_cost = Decimal("0.000000")

    for m in movements:
        if m.quantity_base > 0:
            new_qty = current_qty + m.quantity_base
            new_val = current_val_paise + Decimal(m.value_paise)
            if new_qty > 0:
                current_unit_cost = (new_val / Decimal(new_qty)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
            current_qty = new_qty
            current_val_paise = new_val
        elif m.quantity_base < 0:
            current_qty += m.quantity_base
            current_val_paise += Decimal(m.value_paise)
            if current_qty <= 0:
                current_qty = 0
                current_val_paise = Decimal("0")
                current_unit_cost = Decimal("0.000000")
            elif m.movement_type == MovementType.REVERSAL:
                # When a purchase receipt is reversed, recompute average cost from remaining inventory
                current_unit_cost = (current_val_paise / Decimal(current_qty)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )

    return {
        "item_id": item_id,
        "balance_base": current_qty,
        "weighted_avg_cost_paise": current_unit_cost,
        "total_value_paise": int(current_val_paise.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }


def get_current_unit_cost(db: Session, item_id: int) -> Decimal:
    """Returns the prevailing moving weighted average cost in paise per base unit."""
    val = get_valuation(db, item_id)
    return val["weighted_avg_cost_paise"]


def post_movement(
    db: Session,
    item_id: int,
    movement_type: MovementType,
    quantity_base: int,
    unit_cost: Decimal,
    source_type: str,
    source_id: Optional[str | int] = None,
    user: Optional[User] = None,
    reverses_movement_id: Optional[int] = None,
    note: Optional[str] = None,
    batch_no: Optional[str] = None,
    expiry_date: Optional[datetime] = None,
    movement_date: Optional[datetime] = None,
) -> StockMovement:
    """
    The SOLE gateway function authorized to insert rows into the immutable stock_movements ledger.
    Enforces row locking and prevents negative stock on inventory issues.
    """
    if quantity_base == 0:
        raise ValueError("quantity_base cannot be zero in a stock movement.")

    # Concurrency protection: Lock the Item row (SELECT ... FOR UPDATE) on issues/consumption
    if quantity_base < 0:
        # SQLite ignores FOR UPDATE gracefully, while PostgreSQL locks the row
        item = db.scalar(
            select(Item).where(Item.id == item_id).with_for_update()
        )
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

        available_stock = get_balance(db, item_id)
        if available_stock + quantity_base < 0:
            raise InsufficientStockError(
                item_id=item_id,
                available=available_stock,
                requested=abs(quantity_base),
                item_name=item.name,
            )

    # Compute signed whole paise value using ROUND_HALF_UP
    val_paise_dec = Decimal(quantity_base) * Decimal(unit_cost)
    value_paise = int(val_paise_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    now = datetime.now(timezone.utc)
    movement = StockMovement(
        item_id=item_id,
        movement_date=movement_date or now,
        movement_type=movement_type,
        quantity_base=quantity_base,
        unit_cost=Decimal(unit_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        value_paise=value_paise,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        reverses_movement_id=reverses_movement_id,
        batch_no=batch_no,
        expiry_date=expiry_date,
        created_by=user.id if user else None,
        created_at=now,
        note=note,
    )
    db.add(movement)
    db.flush()
    return movement


def post_adjustment(
    db: Session,
    item_id: int,
    delta: int,
    reason: str,
    user: User,
    unit_cost_override: Optional[Decimal] = None,
) -> StockMovement:
    """
    Posts an inventory adjustment with mandatory audit explanation.
    Valued at prevailing weighted average cost unless an explicit override is supplied.
    """
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mandatory explanation reason must be provided for stock adjustments.",
        )
    if delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adjustment delta cannot be zero.",
        )

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    unit_cost = unit_cost_override if unit_cost_override is not None else get_current_unit_cost(db, item_id)
    if unit_cost <= 0 and item.opening_rate_paise:
        unit_cost = item.opening_rate_paise

    old_balance = get_balance(db, item_id)
    movement = post_movement(
        db=db,
        item_id=item_id,
        movement_type=MovementType.ADJUSTMENT,
        quantity_base=delta,
        unit_cost=unit_cost,
        source_type="ADJUSTMENT",
        source_id=reason.strip(),
        user=user,
        note=reason.strip(),
    )

    new_balance = old_balance + delta
    log_audit(
        db=db,
        user=user,
        action="STOCK_ADJUSTMENT",
        entity_type="Item",
        entity_id=item_id,
        old_values={"balance_base": old_balance},
        new_values={"balance_base": new_balance, "delta": delta, "reason": reason.strip()},
    )
    return movement


def get_stock_summary(
    db: Session,
    item_type: Optional[ItemType] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """
    Returns inventory summary with audit reconciliation breakdown:
    opening + receipts - issues + adjustments = closing
    """
    stmt = select(Item).where(Item.is_active == True)
    if item_type:
        stmt = stmt.where(Item.item_type == item_type)
    items = db.scalars(stmt).all()

    summary_list = []
    for item in items:
        # Opening balance before from_date
        opening_qty = 0
        if from_date:
            opening_qty = int(
                db.scalar(
                    select(func.coalesce(func.sum(StockMovement.quantity_base), 0)).where(
                        StockMovement.item_id == item.id,
                        StockMovement.movement_date < from_date,
                    )
                )
                or 0
            )

        # Period query for receipts, issues, adjustments
        p_stmt = select(StockMovement).where(StockMovement.item_id == item.id)
        if from_date:
            p_stmt = p_stmt.where(StockMovement.movement_date >= from_date)
        if to_date:
            p_stmt = p_stmt.where(StockMovement.movement_date <= to_date)

        period_movements = db.scalars(p_stmt).all()

        receipts_qty = 0
        issues_qty = 0
        adjustments_qty = 0

        for m in period_movements:
            if m.movement_type == MovementType.ADJUSTMENT:
                adjustments_qty += m.quantity_base
            elif m.quantity_base > 0:
                receipts_qty += m.quantity_base
            else:
                issues_qty += abs(m.quantity_base)

        # Closing balance as of to_date
        closing_qty = get_balance(db, item.id, as_of=to_date)
        val = get_valuation(db, item.id, as_of=to_date)

        summary_list.append({
            "item_id": item.id,
            "name": item.name,
            "item_type": item.item_type.value,
            "base_unit": item.base_unit,
            "display_unit": item.display_unit,
            "opening_balance_base": opening_qty,
            "receipts_base": receipts_qty,
            "issues_base": issues_qty,
            "adjustments_base": adjustments_qty,
            "closing_balance_base": closing_qty,
            "closing_balance_display": str(from_base(closing_qty, item.display_unit)),
            "weighted_avg_cost_paise": val["weighted_avg_cost_paise"],
            "total_value_paise": val["total_value_paise"],
            "total_value_rupees": f"{(Decimal(val['total_value_paise']) / Decimal(100)):.2f}",
            "reconciled": (opening_qty + receipts_qty - issues_qty + adjustments_qty) == closing_qty,
        })

    return summary_list


def get_stock_ledger(
    db: Session,
    item_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """
    Returns the granular stock ledger for an item with running balance.
    """
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    stmt = (
        select(StockMovement)
        .where(StockMovement.item_id == item_id)
        .order_by(StockMovement.movement_date.asc(), StockMovement.id.asc())
    )
    all_movements = db.scalars(stmt).all()

    running_bal = 0
    ledger_entries = []

    for m in all_movements:
        running_bal += m.quantity_base
        in_qty = m.quantity_base if m.quantity_base > 0 else 0
        out_qty = abs(m.quantity_base) if m.quantity_base < 0 else 0

        # Filter by date range for output view while preserving accurate running balance
        if from_date and m.movement_date < from_date:
            continue
        if to_date and m.movement_date > to_date:
            continue

        ledger_entries.append({
            "id": m.id,
            "date": m.movement_date,
            "movement_type": m.movement_type.value,
            "in_qty_base": in_qty,
            "out_qty_base": out_qty,
            "running_balance_base": running_bal,
            "unit_cost": m.unit_cost,
            "value_paise": m.value_paise,
            "source_type": m.source_type,
            "source_id": m.source_id,
            "reverses_movement_id": m.reverses_movement_id,
            "created_by": m.created_by,
            "note": m.note,
        })

    return ledger_entries


def reconcile_stock(db: Session) -> dict[str, Any]:
    """
    Re-evaluates every item's ledger to guarantee mathematical integrity:
    opening + receipts - issues + adjustments == closing.
    """
    summary = get_stock_summary(db)
    mismatches = [s for s in summary if not s["reconciled"]]
    return {
        "status": "reconciled" if not mismatches else "mismatch_detected",
        "total_items_checked": len(summary),
        "mismatches": mismatches,
    }
