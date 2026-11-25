from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.purchase import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import MovementType, StockMovement
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.purchase import PurchaseCreate
from app.services.audit import log_audit
from app.services.stock import post_movement
from app.utils.units import to_base

logger = logging.getLogger("purchase_service")


def _generate_purchase_no(db: Session) -> str:
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PO-{today_str}-"
    stmt = (
        select(func.count(Purchase.id))
        .where(Purchase.purchase_no.like(f"{prefix}%"))
    )
    count = (db.scalar(stmt) or 0) + 1
    return f"{prefix}{count:04d}"


def create_and_post_purchase(
    db: Session,
    payload: PurchaseCreate,
    user: User,
) -> Purchase:
    """
    Creates and immediately posts a purchase receipt.
    In the SAME database transaction:
    1. Creates Purchase and PurchaseLines records.
    2. Posts a positive PURCHASE movement in stock_movements for each line item.
    3. Writes an immutable audit trail entry.
    """
    supplier = db.get(Supplier, payload.supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {payload.supplier_id} not found",
        )

    purchase_no = _generate_purchase_no(db)
    now = datetime.now(timezone.utc)
    purchase_date = payload.purchase_date or now

    total_paise = 0
    lines_to_add = []
    movements_data = []

    for line_in in payload.lines:
        item = db.get(Item, line_in.item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {line_in.item_id} not found",
            )

        # Convert entered commercial quantity to canonical base units (grams, ml, pieces)
        qty_base = to_base(line_in.quantity_entered, line_in.unit_entered)

        # Line total in paise: (commercial quantity * rate per commercial unit)
        line_total_dec = Decimal(line_in.quantity_entered) * Decimal(line_in.rate_paise)
        line_total_paise = int(line_total_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total_paise += line_total_paise

        # Exact per-base-unit cost (paise per g/ml/piece) with 6 decimal places of precision
        unit_cost = (Decimal(line_total_paise) / Decimal(qty_base)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        lines_to_add.append({
            "item_id": line_in.item_id,
            "quantity_base": qty_base,
            "unit_entered": line_in.unit_entered,
            "rate_paise": line_in.rate_paise,
            "line_total_paise": line_total_paise,
            "unit_cost": unit_cost,
        })

    purchase = Purchase(
        purchase_no=purchase_no,
        supplier_id=supplier.id,
        supplier_invoice_no=payload.supplier_invoice_no,
        purchase_date=purchase_date,
        status=PurchaseStatus.POSTED,
        total_paise=total_paise,
        created_by=user.id,
        notes=payload.notes,
    )
    db.add(purchase)
    db.flush()

    # Create lines and post ledger movements in the same atomic transaction
    for l_data in lines_to_add:
        p_line = PurchaseLine(
            purchase_id=purchase.id,
            item_id=l_data["item_id"],
            quantity_base=l_data["quantity_base"],
            unit_entered=l_data["unit_entered"],
            rate_paise=l_data["rate_paise"],
            line_total_paise=l_data["line_total_paise"],
        )
        db.add(p_line)

        # Post immutable ledger row
        post_movement(
            db=db,
            item_id=l_data["item_id"],
            movement_type=MovementType.PURCHASE,
            quantity_base=l_data["quantity_base"],
            unit_cost=l_data["unit_cost"],
            source_type="PURCHASE",
            source_id=purchase.purchase_no,
            user=user,
            movement_date=purchase_date,
            note=f"Purchase receipt {purchase.purchase_no} from {supplier.name}",
        )

    # Record audit log
    log_audit(
        db=db,
        user=user,
        action="PURCHASE_POSTED",
        entity_type="Purchase",
        entity_id=purchase.id,
        old_values=None,
        new_values={
            "purchase_no": purchase.purchase_no,
            "supplier_id": supplier.id,
            "total_paise": total_paise,
            "lines_count": len(lines_to_add),
        },
    )

    db.commit()
    db.refresh(purchase)
    return purchase


def cancel_purchase(
    db: Session,
    purchase_id: int,
    user: User,
    reason: str = "Cancelled by user",
) -> Purchase:
    """
    Cancels a purchase receipt without deleting ledger rows.
    In the SAME atomic transaction:
    1. Sets purchase status to CANCELLED.
    2. Writes REVERSAL movements in stock_movements (negative quantity) linking to original rows.
    3. Fails with 409 if inventory has already been consumed and cannot be reversed.
    4. Writes an immutable audit trail entry.
    """
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase {purchase_id} not found",
        )
    if purchase.status == PurchaseStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Purchase {purchase.purchase_no} is already cancelled",
        )

    # Post REVERSAL movements for each line item
    for line in purchase.lines:
        orig_mov = db.scalar(
            select(StockMovement).where(
                StockMovement.source_type == "PURCHASE",
                StockMovement.source_id == purchase.purchase_no,
                StockMovement.item_id == line.item_id,
                StockMovement.quantity_base > 0,
            )
        )
        unit_cost = orig_mov.unit_cost if orig_mov else Decimal("0.000000")
        reverses_id = orig_mov.id if orig_mov else None

        # Reversal is negative quantity; post_movement checks available stock & prevents negative stock
        post_movement(
            db=db,
            item_id=line.item_id,
            movement_type=MovementType.REVERSAL,
            quantity_base=-line.quantity_base,
            unit_cost=unit_cost,
            source_type="REVERSAL",
            source_id=purchase.purchase_no,
            user=user,
            reverses_movement_id=reverses_id,
            note=f"Reversal of {purchase.purchase_no}: {reason}",
        )

    old_status = purchase.status.value
    purchase.status = PurchaseStatus.CANCELLED

    log_audit(
        db=db,
        user=user,
        action="PURCHASE_CANCELLED",
        entity_type="Purchase",
        entity_id=purchase.id,
        old_values={"status": old_status},
        new_values={"status": purchase.status.value, "reason": reason},
    )

    db.commit()
    db.refresh(purchase)
    return purchase
