from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.bom import BOM, BOMItem
from app.models.item import Item, ItemType
from app.models.product import Product, ProductFamily
from app.models.production import ProductionRun, ProductionRunStatus
from app.models.user import User, UserRole
from app.services.audit import log_audit
from app.schemas.bom import BOMCreate, BOMResponse

router = APIRouter(prefix="/boms", tags=["BOMs"])

ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[BOMResponse], dependencies=[Depends(ALLOW_READ)])
def list_boms(
    family_id: int | None = None,
    product_id: int | None = None,
    is_active: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(BOM).options(selectinload(BOM.items).selectinload(BOMItem.item))
    if is_active is not None:
        stmt = stmt.where(BOM.is_active == is_active)
    if family_id:
        stmt = stmt.where(BOM.family_id == family_id)
    elif product_id:
        prod = db.get(Product, product_id)
        if prod:
            stmt = stmt.where(BOM.family_id == prod.family_id)
    stmt = stmt.offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=BOMResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_bom(
    payload: BOMCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Determine family_id
    family_id = payload.family_id
    if not family_id and payload.product_id:
        prod = db.get(Product, payload.product_id)
        if prod and prod.family_id:
            family_id = prod.family_id
        elif prod:
            family = db.scalar(select(ProductFamily).where(ProductFamily.name == "Murukku"))
            if not family:
                family = ProductFamily(name="Murukku", hsn_code="1905", gst_rate_bp=500, is_active=True)
                db.add(family)
                db.flush()
            prod.family_id = family.id
            family_id = family.id

    if not family_id:
        family = db.scalar(select(ProductFamily).limit(1))
        if family:
            family_id = family.id
        else:
            family = ProductFamily(name="Default Family", hsn_code="1905", gst_rate_bp=500, is_active=True)
            db.add(family)
            db.flush()
            family_id = family.id

    # Validate raw material type invariant
    for item_data in payload.items:
        it = db.get(Item, item_data.item_id)
        if not it:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_data.item_id} not found")
        if it.item_type != ItemType.RAW_MATERIAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"BOM items must be of type RAW_MATERIAL (got {it.item_type.value})",
            )

    existing = db.scalar(
        select(BOM).where(BOM.family_id == family_id, BOM.version == payload.version)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BOM for Family {family_id} Version {payload.version} already exists",
        )

    if payload.is_active:
        db.execute(
            update(BOM).where(BOM.family_id == family_id).values(is_active=False)
        )

    bom = BOM(
        family_id=family_id,
        version=payload.version,
        expected_output_g=payload.expected_output_g or 40000,
        is_active=payload.is_active,
    )
    for item_data in payload.items:
        bom.items.append(
            BOMItem(
                item_id=item_data.item_id,
                quantity_per_batch=item_data.quantity_per_batch or item_data.quantity_per_batch_base or 0,
                unit_for_display=item_data.unit_for_display,
                variance_tolerance_pct=item_data.variance_tolerance_pct or item_data.tolerance_override,
            )
        )

    db.add(bom)
    db.flush()
    log_audit(
        db=db,
        user=current_user,
        action="BOM_VERSION_CREATED",
        entity_type="BOM",
        entity_id=str(bom.id),
        new_values={
            "family_id": bom.family_id,
            "version": bom.version,
            "expected_output_g": bom.expected_output_g,
            "is_active": bom.is_active,
        },
    )
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
def activate_bom(
    bom_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activates this BOM version and automatically deactivates all other versions for the same family.
    Ensures invariant: exactly one active BOM per family.
    """
    bom = db.scalar(select(BOM).options(selectinload(BOM.items)).where(BOM.id == bom_id))
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")

    db.execute(
        update(BOM).where(BOM.family_id == bom.family_id).values(is_active=False)
    )
    bom.is_active = True
    log_audit(
        db=db,
        user=current_user,
        action="BOM_VERSION_ACTIVATED",
        entity_type="BOM",
        entity_id=str(bom.id),
        old_values={"is_active": False},
        new_values={"is_active": True, "family_id": bom.family_id, "version": bom.version},
    )
    db.commit()
    db.refresh(bom)
    return bom


@router.put("/{bom_id}", response_model=BOMResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_bom(
    bom_id: int,
    payload: BOMCreate,
    create_new_version: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edits a BOM version.
    Rule: A BOM used by a posted run is never edited; saving creates a new version.
    """
    bom = db.scalar(select(BOM).options(selectinload(BOM.items)).where(BOM.id == bom_id))
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")

    # Validate raw material type invariant
    for item_data in payload.items:
        it = db.get(Item, item_data.item_id)
        if not it:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_data.item_id} not found")
        if it.item_type != ItemType.RAW_MATERIAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"BOM items must be of type RAW_MATERIAL (got {it.item_type.value})",
            )

    # Invariant: A BOM used by a posted run is never edited
    posted_run = db.scalar(
        select(ProductionRun).where(
            ProductionRun.bom_id == bom_id,
            ProductionRun.status == ProductionRunStatus.POSTED,
        )
    )
    if posted_run:
        if not create_new_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot modify BOM version {bom.version} because it has been used in posted production run "
                    f"'{posted_run.run_no}'. Create a new BOM version instead."
                ),
            )

        # Automatically create new version instead of mutating posted BOM
        max_v = db.scalar(
            select(func.max(BOM.version)).where(BOM.family_id == bom.family_id)
        ) or bom.version
        new_version = max_v + 1
        if payload.is_active:
            db.execute(update(BOM).where(BOM.family_id == bom.family_id).values(is_active=False))

        new_bom = BOM(
            family_id=bom.family_id,
            version=new_version,
            expected_output_g=payload.expected_output_g or bom.expected_output_g,
            is_active=payload.is_active,
        )
        for item_data in payload.items:
            new_bom.items.append(
                BOMItem(
                    item_id=item_data.item_id,
                    quantity_per_batch=item_data.quantity_per_batch or item_data.quantity_per_batch_base or 0,
                    unit_for_display=item_data.unit_for_display,
                    variance_tolerance_pct=item_data.variance_tolerance_pct or item_data.tolerance_override,
                )
            )
        db.add(new_bom)
        db.flush()
        log_audit(
            db=db,
            user=current_user,
            action="BOM_VERSION_CREATED",
            entity_type="BOM",
            entity_id=str(new_bom.id),
            new_values={
                "family_id": new_bom.family_id,
                "version": new_bom.version,
                "expected_output_g": new_bom.expected_output_g,
                "is_active": new_bom.is_active,
            },
        )
        db.commit()
        db.refresh(new_bom)
        return new_bom

    if payload.is_active:
        db.execute(
            update(BOM).where(BOM.family_id == bom.family_id, BOM.id != bom.id).values(is_active=False)
        )

    bom.expected_output_g = payload.expected_output_g or bom.expected_output_g
    bom.is_active = payload.is_active
    bom.items.clear()
    for item_data in payload.items:
        bom.items.append(
            BOMItem(
                item_id=item_data.item_id,
                quantity_per_batch=item_data.quantity_per_batch or item_data.quantity_per_batch_base or 0,
                unit_for_display=item_data.unit_for_display,
                variance_tolerance_pct=item_data.variance_tolerance_pct or item_data.tolerance_override,
            )
        )

    db.commit()
    db.refresh(bom)
    return bom
