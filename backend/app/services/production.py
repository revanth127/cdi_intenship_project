from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.item import Item, ItemType
from app.models.product import Product
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.stock import MovementType, StockMovement
from app.models.user import User
from app.schemas.production import (
    LineVarianceReport,
    ProductionRunCreate,
    ProductionRunUpdate,
    ProductionRunVarianceReport,
    VarianceAlertLine,
    VarianceAlertResponse,
    YieldVarianceReport,
)
from app.services.audit import log_audit
from app.services.stock import get_balance, get_current_unit_cost, post_movement
from app.utils.units import to_base

logger = logging.getLogger("production_service")


def generate_run_number(db: Session, run_date: Optional[datetime] = None) -> str:
    """Generates sequential run numbers in format PR-YYYY-XXXX (e.g. PR-2026-0001)."""
    target_year = (run_date or datetime.now(timezone.utc)).year
    prefix = f"PR-{target_year}-"
    stmt = (
        select(ProductionRun.run_no)
        .where(ProductionRun.run_no.like(f"{prefix}%"))
        .order_by(desc(ProductionRun.run_no))
        .limit(1)
    )
    last_no = db.scalar(stmt)
    if not last_no:
        seq = 1
    else:
        try:
            seq = int(last_no.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:04d}"


def get_default_tolerance(db: Session) -> Decimal:
    """Fetches company default variance tolerance percentage (default 3.00%)."""
    settings = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    if settings and settings.variance_tolerance_pct is not None:
        return settings.variance_tolerance_pct
    return Decimal("3.00")


def build_variance_report(db: Session, run: ProductionRun) -> ProductionRunVarianceReport:
    """
    Constructs a structured planned-vs-actual variance report for a production run.
    Reports per-item planned, actual, difference, percentage, and tolerance flag,
    along with finished goods yield and packaging wastage.
    """
    default_tolerance = get_default_tolerance(db)
    bom_items = db.scalars(select(BOMItem).where(BOMItem.bom_id == run.bom_id)).all()
    tolerance_map = {bi.item_id: bi.variance_tolerance_pct for bi in bom_items}

    yield_report = YieldVarianceReport(
        expected_output_packets=run.expected_output_packets,
        actual_good_packets=run.actual_good_packets,
        wastage_packets=run.wastage_packets,
        yield_variance_pct=run.yield_variance_pct,
        tolerance_pct=default_tolerance,
        is_flagged=run.is_yield_flagged,
    )

    line_reports = []
    for line in run.lines:
        effective_tolerance = tolerance_map.get(line.item_id)
        if effective_tolerance is None:
            effective_tolerance = default_tolerance

        item_name = line.item.name if line.item else f"Item {line.item_id}"
        line_reports.append(
            LineVarianceReport(
                item_id=line.item_id,
                item_name=item_name,
                display_unit=line.unit_for_display,
                planned_qty_base=line.planned_qty_base,
                actual_qty_base=line.actual_qty_base,
                difference_qty_base=line.variance_qty_base,
                variance_pct=line.variance_pct,
                tolerance_pct=effective_tolerance,
                is_flagged=line.is_flagged,
                damaged_qty_base=line.damaged_qty_base,
                unit_cost_paise=line.unit_cost,
                value_paise=line.value_paise,
            )
        )

    return ProductionRunVarianceReport(yield_report=yield_report, lines=line_reports)


def attach_variance_report(db: Session, run: ProductionRun) -> ProductionRun:
    """Attaches the computed variance_report object onto the ProductionRun instance."""
    run.variance_report = build_variance_report(db, run)
    return run


def recompute_variances(db: Session, run: ProductionRun) -> None:
    """
    Recalculates yield variance and line variances using Decimal arithmetic.
    
    Formulae:
      - Line variance %  = ((actual_qty - planned_qty) / planned_qty) * 100  (quantized to 2 dp, ROUND_HALF_UP)
      - Yield variance % = ((actual_good - expected) / expected) * 100       (quantized to 2 dp, ROUND_HALF_UP)
      - Wastage packets  = expected_output_packets - actual_good_packets

    Tolerance flagging rule:
      - Flags line if abs(variance_pct) > effective_tolerance (strict greater-than).
      - Effective tolerance is the per-BOM-item override if present, falling back to CompanySettings (default 3.00%).
      - Flags yield if abs(yield_variance_pct) > default_tolerance.
    """
    default_tolerance = get_default_tolerance(db)

    # 1. Yield variance calculation
    if run.actual_good_packets is not None and run.expected_output_packets > 0:
        run.wastage_packets = run.expected_output_packets - run.actual_good_packets
        diff_packets = Decimal(run.actual_good_packets) - Decimal(run.expected_output_packets)
        run.yield_variance_pct = (
            (diff_packets / Decimal(run.expected_output_packets)) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        run.is_yield_flagged = abs(run.yield_variance_pct) > default_tolerance
    else:
        run.wastage_packets = None
        run.yield_variance_pct = None
        run.is_yield_flagged = False

    # 2. Line variance calculation
    bom_items = db.scalars(select(BOMItem).where(BOMItem.bom_id == run.bom_id)).all()
    tolerance_map = {bi.item_id: bi.variance_tolerance_pct for bi in bom_items}

    for line in run.lines:
        if line.actual_qty_base is not None and line.planned_qty_base > 0:
            diff_qty = line.actual_qty_base - line.planned_qty_base
            line.variance_qty_base = diff_qty
            line.variance_pct = (
                (Decimal(diff_qty) / Decimal(line.planned_qty_base)) * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            effective_tolerance = tolerance_map.get(line.item_id)
            if effective_tolerance is None:
                effective_tolerance = default_tolerance

            # Strict greater-than rule: abs(variance_pct) > tolerance
            line.is_flagged = abs(line.variance_pct) > effective_tolerance
        else:
            line.variance_qty_base = None
            line.variance_pct = None
            line.is_flagged = False


def create_run(db: Session, payload: ProductionRunCreate, user: User) -> ProductionRun:
    """
    Creates a new DRAFT production run.
    Copies active BOM, scales line quantities by batches using ROUND_HALF_UP,
    and initializes planned quantities in integer base units.

    Accepts scaling either via:
      - `batches` (e.g. Decimal("1.0000"))
      - `batch_size_packets` / `batch_size` (e.g. 200 packets)
    """
    product = db.scalar(select(Product).where(Product.id == payload.product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {payload.product_id} not found")

    if payload.bom_id:
        bom = db.scalar(
            select(BOM)
            .options(selectinload(BOM.items))
            .where(BOM.id == payload.bom_id, BOM.product_id == product.id)
        )
        if not bom:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"BOM {payload.bom_id} not found for Product {payload.product_id}",
            )
    else:
        bom = db.scalar(
            select(BOM)
            .options(selectinload(BOM.items))
            .where(BOM.product_id == product.id, BOM.is_active.is_(True))
        )
        if not bom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No active BOM found for Product {payload.product_id}",
            )

    # Determine batches and expected output
    target_packets = payload.batch_size_packets or payload.batch_size
    if target_packets is not None:
        if target_packets <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch size packets must be positive")
        expected_output = target_packets
        batches = (Decimal(target_packets) / Decimal(bom.batch_output_packets)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    elif payload.batches is not None:
        batches = Decimal(payload.batches).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if batches <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batches must be positive")
        expected_output = int(
            (Decimal(bom.batch_output_packets) * batches).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        batches = Decimal("1.0000")
        expected_output = bom.batch_output_packets

    run_no = generate_run_number(db, payload.run_date)
    run_date = payload.run_date or datetime.now(timezone.utc)

    run = ProductionRun(
        run_no=run_no,
        product_id=product.id,
        bom_id=bom.id,
        bom_version=bom.version,
        run_date=run_date,
        batches=batches,
        batch_size_packets=expected_output,
        status=ProductionRunStatus.DRAFT,
        expected_output_packets=expected_output,
        created_by=user.id,
        notes=payload.notes,
    )

    # Scale BOM items into integer base units with ROUND_HALF_UP
    # Formula: planned_qty_base = round(quantity_per_batch * batches, ROUND_HALF_UP)
    for bi in bom.items:
        planned_qty = int(
            (Decimal(bi.quantity_per_batch) * batches).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        line = ProductionRunLine(
            item_id=bi.item_id,
            planned_qty_base=planned_qty,
            actual_qty_base=None,
            damaged_qty_base=0,
            unit_for_display=bi.unit_for_display,
        )
        run.lines.append(line)

    db.add(run)
    db.commit()
    db.refresh(run)

    log_audit(
        db=db,
        user=user,
        action="PRODUCTION_RUN_CREATED",
        entity_type="ProductionRun",
        entity_id=run.id,
        new_values={
            "run_no": run.run_no,
            "product_id": run.product_id,
            "bom_id": run.bom_id,
            "bom_version": run.bom_version,
            "batches": str(run.batches),
            "batch_size_packets": run.batch_size_packets,
            "expected_output_packets": run.expected_output_packets,
        },
    )

    return attach_variance_report(db, run)


def update_run(db: Session, run_id: int, payload: ProductionRunUpdate, user: User) -> ProductionRun:
    """
    Edits a DRAFT production run (actual quantities, output, damaged items).
    Supports entering quantities in display units (kg, L, pieces) with automatic
    conversion to integer base units via to_base().

    Enforces packaging rule:
      For primary packaging (e.g. pouches with 1 pouch per packet):
      actual consumption = pieces used in good packets + pieces damaged.

    Audits all changes with old/new values.
    """
    run = db.scalar(
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
            selectinload(ProductionRun.product),
        )
        .where(ProductionRun.id == run_id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Production run {run_id} not found")

    if run.status != ProductionRunStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit production run {run.run_no} with status {run.status.value}. Only DRAFT runs can be edited.",
        )

    old_values = {
        "actual_good_packets": run.actual_good_packets,
        "notes": run.notes,
        "lines": [
            {
                "item_id": l.item_id,
                "actual_qty_base": l.actual_qty_base,
                "damaged_qty_base": l.damaged_qty_base,
            }
            for l in run.lines
        ],
    }

    if payload.actual_good_packets is not None:
        run.actual_good_packets = payload.actual_good_packets
    if payload.notes is not None:
        run.notes = payload.notes
    if payload.run_date is not None:
        run.run_date = payload.run_date

    # Update line actuals and damaged quantities
    line_map = {l.item_id: l for l in run.lines}
    explicit_actual_items = set()

    for line_in in payload.lines:
        if line_in.item_id in line_map:
            target_line = line_map[line_in.item_id]

            # 1. Update damaged quantity (if provided in base units or display units)
            if line_in.damaged_qty_base is not None:
                target_line.damaged_qty_base = line_in.damaged_qty_base
            elif line_in.damaged_qty is not None:
                unit = line_in.unit or target_line.unit_for_display
                target_line.damaged_qty_base = to_base(line_in.damaged_qty, unit)

            # 2. Update actual quantity (if provided in base units or display units)
            if line_in.actual_qty_base is not None:
                target_line.actual_qty_base = line_in.actual_qty_base
                explicit_actual_items.add(line_in.item_id)
            elif line_in.actual_qty is not None:
                unit = line_in.unit or target_line.unit_for_display
                target_line.actual_qty_base = to_base(line_in.actual_qty, unit)
                explicit_actual_items.add(line_in.item_id)
            else:
                # If actual_qty was not explicitly provided, but damaged_qty was entered
                # for primary packaging (1 unit per packet):
                # actual consumption = pieces used in good packets + pieces damaged
                if (
                    run.actual_good_packets is not None
                    and target_line.planned_qty_base == run.expected_output_packets
                ):
                    target_line.actual_qty_base = run.actual_good_packets + target_line.damaged_qty_base
                    explicit_actual_items.add(line_in.item_id)

    # 3. Synchronize any 1-to-1 primary packaging line where actual wasn't explicitly overridden
    # when actual_good_packets was supplied
    if run.actual_good_packets is not None:
        for line in run.lines:
            if line.item_id not in explicit_actual_items and line.planned_qty_base == run.expected_output_packets:
                if line.damaged_qty_base > 0 or line.actual_qty_base is not None:
                    line.actual_qty_base = run.actual_good_packets + line.damaged_qty_base

    recompute_variances(db, run)

    new_values = {
        "actual_good_packets": run.actual_good_packets,
        "notes": run.notes,
        "lines": [
            {
                "item_id": l.item_id,
                "actual_qty_base": l.actual_qty_base,
                "damaged_qty_base": l.damaged_qty_base,
            }
            for l in run.lines
        ],
    }

    log_audit(
        db=db,
        user=user,
        action="PRODUCTION_RUN_UPDATED",
        entity_type="ProductionRun",
        entity_id=run.id,
        old_values=old_values,
        new_values=new_values,
    )

    db.commit()
    db.refresh(run)
    return attach_variance_report(db, run)


def post_run(db: Session, run_id: int, user: User) -> ProductionRun:
    """
    Posts a production run atomically in ONE database transaction:
    1. Pre-validates stock for all consumption lines. If ANY line is short, rolls back and raises 409 listing all shortages.
    2. Writes PRODUCTION_ISSUE movements for all consumption lines at current weighted average cost.
    3. Writes one PRODUCTION_OUTPUT movement for finished goods packets, valued at total_material_cost / actual_good_packets.
    4. Marks run POSTED, records poster and timestamp, and stores final financial metrics.
    5. Audits the posting action.
    6. Posting twice is impossible (idempotent guard: raises 409 Conflict).
    """
    run = db.scalar(
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
            selectinload(ProductionRun.product),
        )
        .where(ProductionRun.id == run_id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Production run {run_id} not found")

    if run.status == ProductionRunStatus.POSTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Production run {run.run_no} is already POSTED.",
        )
    if run.status == ProductionRunStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot post CANCELLED production run {run.run_no}.",
        )

    if run.actual_good_packets is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Actual good packets must be recorded before posting the production run.",
        )

    # For lines where actual_qty_base was not explicitly specified:
    for line in run.lines:
        if line.actual_qty_base is None:
            if run.actual_good_packets is not None and line.planned_qty_base == run.expected_output_packets:
                line.actual_qty_base = run.actual_good_packets + line.damaged_qty_base
            else:
                line.actual_qty_base = line.planned_qty_base

    recompute_variances(db, run)

    # Step 1: Pre-validation of inventory availability across all consumption lines
    shortages = []
    for line in run.lines:
        if line.actual_qty_base and line.actual_qty_base > 0:
            current_bal = get_balance(db, line.item_id)
            if current_bal < line.actual_qty_base:
                shortage_qty = line.actual_qty_base - current_bal
                item_name = line.item.name if line.item else f"Item {line.item_id}"
                shortages.append(
                    {
                        "item_id": line.item_id,
                        "item_name": item_name,
                        "required_base": line.actual_qty_base,
                        "available_base": current_bal,
                        "shortage_base": shortage_qty,
                    }
                )

    if shortages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Insufficient stock for production run",
                "shortages": shortages,
            },
        )

    # Step 2: Post PRODUCTION_ISSUE for each consumption line
    total_material_cost_paise = 0
    for line in run.lines:
        actual_qty = line.actual_qty_base or 0
        if actual_qty > 0:
            unit_cost = get_current_unit_cost(db, line.item_id)
            mv = post_movement(
                db=db,
                item_id=line.item_id,
                movement_type=MovementType.PRODUCTION_ISSUE,
                quantity_base=-actual_qty,
                unit_cost=unit_cost,
                source_type="PRODUCTION_RUN",
                source_id=str(run.id),
                user=user,
                note=f"Production issue for run {run.run_no}",
                movement_date=run.run_date,
            )
            line.unit_cost = mv.unit_cost
            line.value_paise = abs(mv.value_paise)
            total_material_cost_paise += abs(mv.value_paise)
        else:
            line.unit_cost = Decimal("0")
            line.value_paise = 0

    # Step 3: Post PRODUCTION_OUTPUT for finished goods packets
    actual_good = run.actual_good_packets
    if actual_good > 0:
        unit_fg_cost = (Decimal(total_material_cost_paise) / Decimal(actual_good)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    else:
        unit_fg_cost = Decimal("0")

    post_movement(
        db=db,
        item_id=run.product.item_id,
        movement_type=MovementType.PRODUCTION_OUTPUT,
        quantity_base=actual_good,
        unit_cost=unit_fg_cost,
        source_type="PRODUCTION_RUN",
        source_id=str(run.id),
        user=user,
        note=f"Production output for run {run.run_no}: {actual_good} packets",
        movement_date=run.run_date,
    )

    # Step 4: Update run state and financial results
    run.total_material_cost_paise = total_material_cost_paise
    run.unit_material_cost_paise = unit_fg_cost
    run.status = ProductionRunStatus.POSTED
    run.posted_by = user.id
    run.posted_at = datetime.now(timezone.utc)

    # Step 5: Audit log
    log_audit(
        db=db,
        user=user,
        action="PRODUCTION_RUN_POSTED",
        entity_type="ProductionRun",
        entity_id=run.id,
        old_values={"status": "DRAFT"},
        new_values={
            "status": "POSTED",
            "run_no": run.run_no,
            "total_material_cost_paise": total_material_cost_paise,
            "unit_material_cost_paise": str(unit_fg_cost),
            "actual_good_packets": actual_good,
        },
    )

    db.commit()
    db.refresh(run)
    return attach_variance_report(db, run)


def cancel_run(db: Session, run_id: int, reason: str, user: User) -> ProductionRun:
    """
    Cancels a production run (ADMIN only).
    If run was POSTED, reverses all stock movements with REVERSAL entries in the ledger.
    """
    run = db.scalar(
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
            selectinload(ProductionRun.product),
        )
        .where(ProductionRun.id == run_id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Production run {run_id} not found")

    if run.status == ProductionRunStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Production run {run.run_no} is already CANCELLED.",
        )

    old_status = run.status.value

    # If POSTED, reverse all associated stock movements
    if run.status == ProductionRunStatus.POSTED:
        movements = db.scalars(
            select(StockMovement).where(
                StockMovement.source_type == "PRODUCTION_RUN",
                StockMovement.source_id == str(run.id),
                StockMovement.movement_type.in_(
                    [MovementType.PRODUCTION_ISSUE, MovementType.PRODUCTION_OUTPUT]
                ),
            )
        ).all()

        for mv in movements:
            post_movement(
                db=db,
                item_id=mv.item_id,
                movement_type=MovementType.REVERSAL,
                quantity_base=-mv.quantity_base,
                unit_cost=mv.unit_cost,
                source_type="PRODUCTION_RUN",
                source_id=str(run.id),
                reverses_movement_id=mv.id,
                user=user,
                note=f"Reversal of production run {run.run_no}: {reason}",
            )

    run.status = ProductionRunStatus.CANCELLED

    log_audit(
        db=db,
        user=user,
        action="PRODUCTION_RUN_CANCELLED",
        entity_type="ProductionRun",
        entity_id=run.id,
        old_values={"status": old_status},
        new_values={"status": "CANCELLED", "reason": reason},
    )

    db.commit()
    db.refresh(run)
    return attach_variance_report(db, run)


def get_variance_alerts(
    db: Session, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None
) -> list[VarianceAlertResponse]:
    """
    Fetches production runs where yield or material consumption exceeded tolerance thresholds.
    Filters by run_date range if provided.
    """
    default_tolerance = get_default_tolerance(db)
    stmt = (
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.product).selectinload(Product.item),
            selectinload(ProductionRun.lines).selectinload(ProductionRunLine.item),
        )
        .order_by(desc(ProductionRun.run_date))
    )
    if from_date:
        stmt = stmt.where(ProductionRun.run_date >= from_date)
    if to_date:
        stmt = stmt.where(ProductionRun.run_date <= to_date)

    runs = db.scalars(stmt).all()
    results = []

    for run in runs:
        bom_items = db.scalars(select(BOMItem).where(BOMItem.bom_id == run.bom_id)).all()
        tolerance_map = {bi.item_id: bi.variance_tolerance_pct for bi in bom_items}

        flagged_lines = []
        for line in run.lines:
            if line.is_flagged:
                effective_tol = tolerance_map.get(line.item_id) or default_tolerance
                flagged_lines.append(
                    VarianceAlertLine(
                        item_id=line.item_id,
                        item_name=line.item.name if line.item else f"Item {line.item_id}",
                        display_unit=line.unit_for_display,
                        planned_qty_base=line.planned_qty_base,
                        actual_qty_base=line.actual_qty_base or 0,
                        variance_qty_base=line.variance_qty_base or 0,
                        variance_pct=line.variance_pct or Decimal("0.00"),
                        tolerance_pct=effective_tol,
                        damaged_qty_base=line.damaged_qty_base,
                    )
                )

        if run.is_yield_flagged or flagged_lines:
            results.append(
                VarianceAlertResponse(
                    run_id=run.id,
                    run_no=run.run_no,
                    product_id=run.product_id,
                    product_name=run.product.item.name if (run.product and run.product.item) else f"Product {run.product_id}",
                    run_date=run.run_date,
                    status=run.status,
                    expected_output_packets=run.expected_output_packets,
                    actual_good_packets=run.actual_good_packets,
                    wastage_packets=run.wastage_packets,
                    yield_variance_pct=run.yield_variance_pct,
                    is_yield_flagged=run.is_yield_flagged,
                    tolerance_pct=default_tolerance,
                    flagged_lines=flagged_lines,
                )
            )

    return results
