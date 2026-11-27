from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import math
from typing import Optional, Union
from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.bom import BOM, BOMItem
from app.models.costing import OverheadCategory, OverheadEntry, OverheadStatus, RunCostSheet
from app.models.item import Item
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.stock import MovementType, StockMovement
from app.models.user import User
from app.schemas.costing import (
    AllocatedOverheadLine,
    MaterialConsumptionItem,
    OverheadCreate,
    OverheadResponse,
    ProductCostSummaryResponse,
    RunCostDetailResponse,
    RunCostListItemResponse,
    RunCostSheetResponse,
)
from app.services.audit import log_audit
from app.services.stock import get_current_unit_cost
from app.utils.money import calculate_line_total_paise

logger = logging.getLogger("costing_service")


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime object is timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(dt_val: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """Parses optional datetime string or object, normalizing query string spaces to +."""
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


def record_overhead(db: Session, payload: OverheadCreate, user: User) -> OverheadEntry:
    """
    Records an overhead expenditure (Labour, Gas, Power, Other).
    - Either production_run_id is specified (direct overhead charged fully to that run).
    - OR month (YYYY-MM) is specified without a run (allocated proportionally to good packets across that month's POSTED runs).
    - Overheads are never written into the stock ledger to preserve ledger immutability.
    - Automatically triggers recomputation of affected run cost sheets.
    - Records audit log entry.
    """
    if payload.amount_paise <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Overhead amount must be positive integer paise.",
        )

    now = datetime.now(timezone.utc)
    entry_date = ensure_utc(payload.entry_date) or now

    run = None
    month = payload.month
    if payload.production_run_id is not None:
        run = db.get(ProductionRun, payload.production_run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Production run {payload.production_run_id} not found",
            )
        if not month:
            month = ensure_utc(run.run_date).strftime("%Y-%m")
    else:
        if not month:
            month = entry_date.strftime("%Y-%m")

    overhead = OverheadEntry(
        entry_date=entry_date,
        category=payload.category,
        amount_paise=payload.amount_paise,
        production_run_id=payload.production_run_id,
        month=month,
        description=payload.description,
        status=OverheadStatus.ACTIVE,
        created_by=user.id,
    )
    db.add(overhead)
    db.commit()
    db.refresh(overhead)

    log_audit(
        db=db,
        user=user,
        action="OVERHEAD_CREATED",
        entity_type="OverheadEntry",
        entity_id=overhead.id,
        new_values={
            "category": overhead.category.value,
            "amount_paise": overhead.amount_paise,
            "production_run_id": overhead.production_run_id,
            "month": overhead.month,
            "description": overhead.description,
        },
    )

    # Recompute affected run cost sheets
    if overhead.production_run_id is not None:
        if run and run.status == ProductionRunStatus.POSTED:
            run_cost(db, overhead.production_run_id)
    elif overhead.month:
        recompute_month_runs(db, overhead.month)

    return overhead


def void_overhead(db: Session, overhead_id: int, reason: str, user: User) -> OverheadEntry:
    """
    Voids an erroneous overhead entry (Admin only).
    - Preserves row and audit trail with void reason and timestamp.
    - Recomputes affected cost sheets immediately.
    """
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mandatory void reason of at least 3 characters is required.",
        )

    overhead = db.get(OverheadEntry, overhead_id)
    if not overhead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Overhead entry {overhead_id} not found",
        )

    if overhead.status == OverheadStatus.VOIDED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Overhead entry {overhead_id} is already VOIDED.",
        )

    now = datetime.now(timezone.utc)
    old_status = overhead.status.value
    overhead.status = OverheadStatus.VOIDED
    overhead.voided_at = now
    overhead.void_reason = reason.strip()

    db.commit()
    db.refresh(overhead)

    log_audit(
        db=db,
        user=user,
        action="OVERHEAD_VOIDED",
        entity_type="OverheadEntry",
        entity_id=overhead.id,
        old_values={"status": old_status},
        new_values={
            "status": OverheadStatus.VOIDED.value,
            "voided_at": str(now),
            "void_reason": overhead.void_reason,
        },
    )

    # Recompute affected run cost sheets
    if overhead.production_run_id is not None:
        r = db.get(ProductionRun, overhead.production_run_id)
        if r and r.status == ProductionRunStatus.POSTED:
            run_cost(db, overhead.production_run_id)
    elif overhead.month:
        recompute_month_runs(db, overhead.month)

    return overhead


def recompute_month_runs(db: Session, month: str) -> None:
    """Recomputes cost sheets for all POSTED production runs in a given calendar month (YYYY-MM)."""
    runs = db.scalars(
        select(ProductionRun).where(
            ProductionRun.status == ProductionRunStatus.POSTED,
        )
    ).all()
    for r in runs:
        if ensure_utc(r.run_date).strftime("%Y-%m") == month:
            run_cost(db, r.id)


def get_allocated_overheads_for_run(
    db: Session, run: ProductionRun
) -> tuple[int, int, int, int, int, list[AllocatedOverheadLine]]:
    """
    Computes total overheads allocated to a run:
    1. Direct overheads entered against this run.
    2. Share of unassigned monthly overheads entered for that month,
       split proportionally across that month's POSTED runs based on good packets produced.
       The rounding remainder is distributed to the largest share so no paise is lost.

    Returns:
      (labour_paise, gas_paise, power_paise, other_paise, total_overheads_paise, lines)
    """
    run_month = ensure_utc(run.run_date).strftime("%Y-%m")

    # 1. Direct active overheads
    direct_entries = db.scalars(
        select(OverheadEntry).where(
            OverheadEntry.production_run_id == run.id,
            OverheadEntry.status == OverheadStatus.ACTIVE,
        )
    ).all()

    # 2. Monthly active overheads with no run assigned
    monthly_entries = db.scalars(
        select(OverheadEntry).where(
            OverheadEntry.production_run_id.is_(None),
            OverheadEntry.month == run_month,
            OverheadEntry.status == OverheadStatus.ACTIVE,
        )
    ).all()

    # Fetch all POSTED runs in this month to compute proportion
    month_posted_runs = db.scalars(
        select(ProductionRun).where(
            ProductionRun.status == ProductionRunStatus.POSTED,
        )
    ).all()
    month_posted_runs = [
        r for r in month_posted_runs if ensure_utc(r.run_date).strftime("%Y-%m") == run_month
    ]

    total_good_packets_in_month = sum(
        (r.actual_good_packets or 0) for r in month_posted_runs
    )

    lines: list[AllocatedOverheadLine] = []
    labour_paise = 0
    gas_paise = 0
    power_paise = 0
    other_paise = 0

    # Process direct entries
    for d in direct_entries:
        amt = d.amount_paise
        if d.category == OverheadCategory.LABOUR:
            labour_paise += amt
        elif d.category == OverheadCategory.GAS:
            gas_paise += amt
        elif d.category == OverheadCategory.POWER:
            power_paise += amt
        elif d.category == OverheadCategory.OTHER:
            other_paise += amt

        lines.append(
            AllocatedOverheadLine(
                overhead_id=d.id,
                category=d.category,
                description=d.description,
                is_direct=True,
                total_entry_amount_paise=amt,
                allocated_amount_paise=amt,
            )
        )

    # Process monthly shared entries
    if monthly_entries and total_good_packets_in_month > 0:
        # Sort runs by good packets desc, then id asc for stable remainder allocation
        sorted_runs = sorted(
            month_posted_runs,
            key=lambda r: (r.actual_good_packets or 0, -r.id),
            reverse=True,
        )

        for m in monthly_entries:
            total_amt = m.amount_paise
            # Compute base shares
            allocated_map: dict[int, int] = {}
            allocated_sum = 0
            for r in sorted_runs:
                pkts = r.actual_good_packets or 0
                share = (total_amt * pkts) // total_good_packets_in_month
                allocated_map[r.id] = share
                allocated_sum += share

            # Distribute rounding remainder to largest shares
            remainder = total_amt - allocated_sum
            for i in range(remainder):
                r_target = sorted_runs[i % len(sorted_runs)]
                allocated_map[r_target.id] += 1

            run_share = allocated_map.get(run.id, 0)
            if run_share > 0:
                if m.category == OverheadCategory.LABOUR:
                    labour_paise += run_share
                elif m.category == OverheadCategory.GAS:
                    gas_paise += run_share
                elif m.category == OverheadCategory.POWER:
                    power_paise += run_share
                elif m.category == OverheadCategory.OTHER:
                    other_paise += run_share

                lines.append(
                    AllocatedOverheadLine(
                        overhead_id=m.id,
                        category=m.category,
                        description=m.description,
                        is_direct=False,
                        total_entry_amount_paise=total_amt,
                        allocated_amount_paise=run_share,
                    )
                )

    total_overheads_paise = labour_paise + gas_paise + power_paise + other_paise
    return (
        labour_paise,
        gas_paise,
        power_paise,
        other_paise,
        total_overheads_paise,
        lines,
    )


def standard_cost(db: Session, product_id: int) -> tuple[Decimal, int]:
    """
    Computes planned standard cost of one batch from the family BOM + variant packaging specs
    at current weighted-average inventory rates:
      Standard cost per packet = (ingredient cost per batch + packaging cost for the expected packets) / expected packets
    Returns:
      (standard_cost_per_packet_rupees, batch_material_cost_paise)
    """
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.packaging_specs))
        .where(Product.id == product_id)
    )
    if not product:
        return Decimal("0.0000"), 0

    bom = db.scalar(
        select(BOM)
        .options(selectinload(BOM.items).selectinload(BOMItem.item))
        .where(BOM.family_id == product.family_id, BOM.is_active == True)
        .order_by(desc(BOM.version))
        .limit(1)
    )
    if not bom:
        bom = db.scalar(
            select(BOM)
            .options(selectinload(BOM.items).selectinload(BOMItem.item))
            .where(BOM.is_active == True)
            .order_by(desc(BOM.version))
            .limit(1)
        )
    if not bom or not bom.items:
        return Decimal("0.0000"), 0

    net_weight = product.net_weight_g if product.net_weight_g else 200
    expected_output_g = bom.expected_output_g if hasattr(bom, "expected_output_g") and bom.expected_output_g else 40000
    expected_packets = math.floor(expected_output_g / net_weight) if net_weight > 0 else 200

    # 1. Ingredient cost per batch
    ingredient_cost_paise = 0
    for bi in bom.items:
        wac_rate = get_current_unit_cost(db, bi.item_id)
        line_paise = calculate_line_total_paise(bi.quantity_per_batch, wac_rate)
        ingredient_cost_paise += line_paise

    # 2. Packaging cost for expected packets
    packaging_cost_paise = 0
    for ps in product.packaging_specs:
        planned_units = math.ceil((expected_packets * ps.qty_base) / ps.per_packets)
        wac_rate = get_current_unit_cost(db, ps.item_id)
        line_paise = calculate_line_total_paise(planned_units, wac_rate)
        packaging_cost_paise += line_paise

    total_batch_cost_paise = ingredient_cost_paise + packaging_cost_paise

    if expected_packets > 0:
        cost_per_pkt = (
            (Decimal(total_batch_cost_paise) / Decimal("100")) / Decimal(expected_packets)
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    else:
        cost_per_pkt = Decimal("0.0000")

    return cost_per_pkt, total_batch_cost_paise


def run_cost(db: Session, run_id: int) -> RunCostDetailResponse:
    """
    Calculates full cost breakdown for a production run:
    - Material cost: sum of value_paise from its PRODUCTION_ISSUE ledger rows (absolute value).
      Always read directly from the ledger so costing and stock agree.
    - Overheads: direct overheads + allocated share of monthly overheads.
    - Good packets: actual good output produced.
    - Cost per packet: (material cost + allocated overheads) / GOOD packets.
      Wastage and yield loss are therefore absorbed by the good packets.
    - Planned standard cost per packet from BOM.
    - Cost of loss: financial value of yield shortfall and excess material consumption.
    - Regenerates and persists RunCostSheet derived snapshot.
    """
    run = db.scalar(
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.product).selectinload(Product.item),
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
        )
        .where(ProductionRun.id == run_id)
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Production run {run_id} not found",
        )

    # 1. Read Material Cost strictly from immutable stock ledger issues
    issue_movements = db.scalars(
        select(StockMovement)
        .options(selectinload(StockMovement.item))
        .where(
            StockMovement.source_type == "PRODUCTION_RUN",
            StockMovement.source_id == str(run.id),
            StockMovement.movement_type == MovementType.PRODUCTION_ISSUE,
        )
        .order_by(StockMovement.id.asc())
    ).all()

    material_cost_paise = 0
    material_breakdown: list[MaterialConsumptionItem] = []

    if issue_movements:
        for mv in issue_movements:
            val = abs(mv.value_paise)
            material_cost_paise += val
            material_breakdown.append(
                MaterialConsumptionItem(
                    item_id=mv.item_id,
                    item_name=mv.item.name,
                    base_unit=mv.item.base_unit,
                    display_unit=mv.item.display_unit,
                    quantity_base=abs(mv.quantity_base),
                    unit_cost_paise=mv.unit_cost,
                    value_paise=val,
                )
            )
    else:
        # Fallback for draft runs where stock movements haven't been posted yet
        for line in run.lines:
            val = line.value_paise or 0
            material_cost_paise += val
            unit_cost = line.unit_cost or Decimal("0")
            material_breakdown.append(
                MaterialConsumptionItem(
                    item_id=line.item_id,
                    item_name=line.item.name if line.item else f"Item {line.item_id}",
                    base_unit=line.item.base_unit if line.item else "unit",
                    display_unit=line.unit_for_display,
                    quantity_base=line.actual_qty_base or line.planned_qty_base,
                    unit_cost_paise=unit_cost,
                    value_paise=val,
                )
            )

    # 2. Overheads Breakdown
    (
        labour_paise,
        gas_paise,
        power_paise,
        other_paise,
        total_overheads_paise,
        overhead_lines,
    ) = get_allocated_overheads_for_run(db, run)
    gas_power_paise = gas_paise + power_paise

    # 3. Totals and Per-Packet Figures
    total_cost_paise = material_cost_paise + total_overheads_paise
    good_pkts = run.actual_good_packets or 0

    if good_pkts > 0:
        total_rupees = Decimal(total_cost_paise) / Decimal("100")
        cpp_raw = total_rupees / Decimal(good_pkts)
        cost_per_packet_4dp = cpp_raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        cost_per_packet_2dp = cpp_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        mat_rupees = Decimal(material_cost_paise) / Decimal("100")
        mat_cpp_raw = mat_rupees / Decimal(good_pkts)
        mat_cost_per_packet = mat_cpp_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        ovh_rupees = Decimal(total_overheads_paise) / Decimal("100")
        ovh_cpp_raw = ovh_rupees / Decimal(good_pkts)
        ovh_cost_per_packet = ovh_cpp_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        cost_per_packet_4dp = Decimal("0.0000")
        cost_per_packet_2dp = Decimal("0.00")
        mat_cost_per_packet = Decimal("0.00")
        ovh_cost_per_packet = Decimal("0.00")

    # 4. Standard planned cost from BOM & Cost of Loss
    planned_cpp, std_batch_cost_paise = standard_cost(db, run.product_id)

    # Standard value of the good output packets produced
    if run.expected_output_packets > 0:
        std_unit_paise = Decimal(std_batch_cost_paise) / Decimal(run.expected_output_packets)
        std_good_output_value_paise = int(
            (Decimal(good_pkts) * std_unit_paise).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        cost_of_loss_paise = max(0, material_cost_paise - std_good_output_value_paise)
    else:
        cost_of_loss_paise = 0

    now = datetime.now(timezone.utc)

    # 5. Persist snapshot in RunCostSheet
    cost_sheet = db.scalar(select(RunCostSheet).where(RunCostSheet.run_id == run.id))
    if not cost_sheet:
        cost_sheet = RunCostSheet(
            run_id=run.id,
            material_cost_paise=material_cost_paise,
            labour_paise=labour_paise,
            gas_power_paise=gas_power_paise,
            other_paise=other_paise,
            total_cost_paise=total_cost_paise,
            good_packets=good_pkts,
            cost_per_packet=cost_per_packet_4dp,
            planned_cost_per_packet=planned_cpp,
            cost_of_loss_paise=cost_of_loss_paise,
            computed_at=now,
        )
        db.add(cost_sheet)
    else:
        cost_sheet.material_cost_paise = material_cost_paise
        cost_sheet.labour_paise = labour_paise
        cost_sheet.gas_power_paise = gas_power_paise
        cost_sheet.other_paise = other_paise
        cost_sheet.total_cost_paise = total_cost_paise
        cost_sheet.good_packets = good_pkts
        cost_sheet.cost_per_packet = cost_per_packet_4dp
        cost_sheet.planned_cost_per_packet = planned_cpp
        cost_sheet.cost_of_loss_paise = cost_of_loss_paise
        cost_sheet.computed_at = now

    db.commit()

    product_name = run.product.item.name if run.product and run.product.item else f"Product {run.product_id}"

    return RunCostDetailResponse(
        run_id=run.id,
        run_no=run.run_no,
        product_id=run.product_id,
        product_name=product_name,
        run_date=run.run_date,
        status=run.status.value,
        expected_output_packets=run.expected_output_packets,
        good_packets=good_pkts,
        wastage_packets=run.wastage_packets,
        yield_variance_pct=run.yield_variance_pct,
        material_cost_paise=material_cost_paise,
        material_cost_per_packet=mat_cost_per_packet,
        material_breakdown=material_breakdown,
        labour_paise=labour_paise,
        gas_power_paise=gas_power_paise,
        other_paise=other_paise,
        total_overheads_paise=total_overheads_paise,
        overhead_cost_per_packet=ovh_cost_per_packet,
        overheads_breakdown=overhead_lines,
        total_cost_paise=total_cost_paise,
        cost_per_packet=cost_per_packet_2dp,
        cost_per_packet_4dp=cost_per_packet_4dp,
        planned_cost_per_packet=planned_cpp,
        cost_of_loss_paise=cost_of_loss_paise,
        computed_at=now,
    )


def get_product_selling_price(db: Session, product_id: int) -> int:
    """Retrieves selling price in paise from the active default price list for the product."""
    pli = db.scalar(
        select(PriceListItem)
        .join(PriceList, PriceList.id == PriceListItem.price_list_id)
        .where(
            PriceListItem.product_id == product_id,
            PriceList.is_active == True,
        )
        .order_by(desc(PriceList.is_default), desc(PriceListItem.effective_from))
        .limit(1)
    )
    if pli:
        return pli.price_paise
    return 0


def product_cost_summary(
    db: Session,
    product_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> ProductCostSummaryResponse:
    """
    Computes weighted average cost across production runs for a product in the given date range:
      total_cost / total_good_packets
    WEIGHTED, NOT an average of per-run averages!
    Computes margin against effective selling price from price list.
    """
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.item))
        .where(Product.id == product_id)
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )

    stmt = select(ProductionRun).where(
        ProductionRun.product_id == product_id,
        ProductionRun.status == ProductionRunStatus.POSTED,
    )
    start_dt = ensure_utc(from_date)
    end_dt = ensure_utc(to_date)
    if start_dt:
        stmt = stmt.where(ProductionRun.run_date >= start_dt)
    if end_dt:
        stmt = stmt.where(ProductionRun.run_date <= end_dt)

    runs = db.scalars(stmt.order_by(ProductionRun.run_date.asc())).all()

    total_mat_paise = 0
    total_ovh_paise = 0
    total_cost_paise = 0
    total_good_pkts = 0

    for r in runs:
        detail = run_cost(db, r.id)
        total_mat_paise += detail.material_cost_paise
        total_ovh_paise += detail.total_overheads_paise
        total_cost_paise += detail.total_cost_paise
        total_good_pkts += detail.good_packets

    if total_good_pkts > 0:
        total_rupees = Decimal(total_cost_paise) / Decimal("100")
        cpp_raw = total_rupees / Decimal(total_good_pkts)
        cpp_4dp = cpp_raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        cpp_2dp = cpp_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        cpp_raw = Decimal("0.0000")
        cpp_4dp = Decimal("0.0000")
        cpp_2dp = Decimal("0.00")

    # Selling Price & Margins
    selling_price_paise = get_product_selling_price(db, product_id)
    selling_price_rupees = (Decimal(selling_price_paise) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if selling_price_rupees > 0:
        margin_per_packet = (selling_price_rupees - cpp_raw).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        margin_pct = (
            ((selling_price_rupees - cpp_raw) / selling_price_rupees) * Decimal("100")
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    else:
        margin_per_packet = Decimal("0.00")
        margin_pct = Decimal("0.0")

    # Price before tax / GST excluded margin
    # In our system, price in PriceListItem is strictly before tax (taxable value)
    gst_rate_bp = product.item.gst_rate_bp if product.item else 0
    price_before_tax = selling_price_rupees
    margin_after_gst_excluded = margin_per_packet

    product_name = product.item.name if product.item else f"Product {product_id}"

    return ProductCostSummaryResponse(
        product_id=product.id,
        product_name=product_name,
        total_material_paise=total_mat_paise,
        total_overheads_paise=total_ovh_paise,
        total_cost_paise=total_cost_paise,
        good_packets=total_good_pkts,
        cost_per_packet=cpp_2dp,
        cost_per_packet_4dp=cpp_4dp,
        selling_price_paise=selling_price_paise,
        selling_price=selling_price_rupees,
        margin_per_packet=margin_per_packet,
        margin_pct=margin_pct,
        gst_rate_bp=gst_rate_bp,
        price_before_tax=price_before_tax,
        margin_after_gst_excluded=margin_after_gst_excluded,
        runs_count=len(runs),
    )


def list_runs_cost(
    db: Session,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[RunCostListItemResponse]:
    """Lists POSTED production runs with cost per packet each in the date range."""
    stmt = select(ProductionRun).where(
        ProductionRun.status == ProductionRunStatus.POSTED,
    )
    start_dt = ensure_utc(from_date)
    end_dt = ensure_utc(to_date)
    if start_dt:
        stmt = stmt.where(ProductionRun.run_date >= start_dt)
    if end_dt:
        stmt = stmt.where(ProductionRun.run_date <= end_dt)

    runs = db.scalars(stmt.order_by(desc(ProductionRun.run_date))).all()
    results: list[RunCostListItemResponse] = []

    for r in runs:
        detail = run_cost(db, r.id)
        results.append(
            RunCostListItemResponse(
                run_id=detail.run_id,
                run_no=detail.run_no,
                product_id=detail.product_id,
                product_name=detail.product_name,
                run_date=detail.run_date,
                status=detail.status,
                good_packets=detail.good_packets,
                material_cost_paise=detail.material_cost_paise,
                overhead_paise=detail.total_overheads_paise,
                total_cost_paise=detail.total_cost_paise,
                cost_per_packet=detail.cost_per_packet,
                cost_per_packet_4dp=detail.cost_per_packet_4dp,
            )
        )

    return results
