from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.bom import BOM, BOMItem
from app.models.production import ProductionRun, ProductionRunStatus
from app.models.user import UserRole
from app.schemas.bom import BOMCreate, BOMResponse

router = APIRouter(prefix="/boms", tags=["BOMs"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT, PRODUCTION
# Write: ADMIN
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[BOMResponse], dependencies=[Depends(ALLOW_READ)])
def list_boms(
    product_id: int | None = None,
    is_active: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(BOM).options(selectinload(BOM.items).selectinload(BOMItem.item))
    if is_active is not None:
        stmt = stmt.where(BOM.is_active == is_active)
    if product_id:
        stmt = stmt.where(BOM.product_id == product_id)
    stmt = stmt.offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=BOMResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_bom(payload: BOMCreate, db: Session = Depends(get_db)):
    existing = db.scalar(
        select(BOM).where(BOM.product_id == payload.product_id, BOM.version == payload.version)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BOM for Product {payload.product_id} Version {payload.version} already exists",
        )

    # Enforce only 1 active BOM per product: deactivate older versions if newly created is active
    if payload.is_active:
        db.execute(
            update(BOM).where(BOM.product_id == payload.product_id).values(is_active=False)
        )

    bom = BOM(
        product_id=payload.product_id,
        version=payload.version,
        batch_output_packets=payload.batch_output_packets,
        is_active=payload.is_active,
    )
    for item_data in payload.items:
        bom.items.append(
            BOMItem(
                item_id=item_data.item_id,
                quantity_per_batch=item_data.quantity_per_batch,
                unit_for_display=item_data.unit_for_display,
                variance_tolerance_pct=item_data.variance_tolerance_pct,
            )
        )

    db.add(bom)
    db.commit()
    db.refresh(bom)
    return bom


@router.get("/{bom_id}", response_model=BOMResponse, dependencies=[Depends(ALLOW_READ)])
def get_bom(bom_id: int, db: Session = Depends(get_db)):
    stmt = select(BOM).options(selectinload(BOM.items).selectinload(BOMItem.item)).where(BOM.id == bom_id)
    bom = db.scalar(stmt)
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")
    return bom


@router.post("/{bom_id}/activate", response_model=BOMResponse, dependencies=[Depends(ALLOW_WRITE)])
def activate_bom(bom_id: int, db: Session = Depends(get_db)):
    """
    Activates this BOM version and automatically deactivates all other versions for the same product.
    Ensures invariant: exactly one active BOM per product.
    """
    bom = db.scalar(select(BOM).options(selectinload(BOM.items)).where(BOM.id == bom_id))
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")

    # Deactivate all versions for this product
    db.execute(
        update(BOM).where(BOM.product_id == bom.product_id).values(is_active=False)
    )
    bom.is_active = True
    db.commit()
    db.refresh(bom)
    return bom


@router.put("/{bom_id}", response_model=BOMResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_bom(bom_id: int, payload: BOMCreate, db: Session = Depends(get_db)):
    """
    Edits a BOM version. Prevents editing if this BOM version has ever been used in a POSTED production run.
    """
    bom = db.scalar(select(BOM).options(selectinload(BOM.items)).where(BOM.id == bom_id))
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")

    # Invariant: prevent editing a BOM used by a posted run
    posted_run = db.scalar(
        select(ProductionRun).where(
            ProductionRun.bom_id == bom_id,
            ProductionRun.status == ProductionRunStatus.POSTED,
        )
    )
    if posted_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot modify BOM version {bom.version} because it has been used in posted production run "
                f"'{posted_run.run_no}'. Create a new BOM version instead."
            ),
        )

    if payload.is_active:
        db.execute(
            update(BOM).where(BOM.product_id == bom.product_id, BOM.id != bom.id).values(is_active=False)
        )

    bom.batch_output_packets = payload.batch_output_packets
    bom.is_active = payload.is_active
    bom.items.clear()
    for item_data in payload.items:
        bom.items.append(
            BOMItem(
                item_id=item_data.item_id,
                quantity_per_batch=item_data.quantity_per_batch,
                unit_for_display=item_data.unit_for_display,
                variance_tolerance_pct=item_data.variance_tolerance_pct,
            )
        )

    db.commit()
    db.refresh(bom)
    return bom
