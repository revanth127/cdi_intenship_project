from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.bom import BOM, BOMItem
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import PackagingSpec, Product, ProductFamily
from app.models.production import ProductionRun, ProductionRunStatus
from app.models.user import UserRole
from app.schemas.bom import BOMCreate, BOMResponse
from app.schemas.product import ProductResponse
from app.schemas.product_family import (
    ProductFamilyCreate,
    ProductFamilyResponse,
    ProductFamilyUpdate,
    ProductVariantCreate,
)

router = APIRouter(prefix="/product-families", tags=["Product Families"])

ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION, UserRole.SALESMAN)
ALLOW_WRITE = require_roles(UserRole.ADMIN, UserRole.PRODUCTION)
ALLOW_ADMIN = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[ProductFamilyResponse], dependencies=[Depends(ALLOW_READ)])
def list_product_families(
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lists all product families with variants and BOMs."""
    stmt = (
        select(ProductFamily)
        .options(
            selectinload(ProductFamily.variants).selectinload(Product.item),
            selectinload(ProductFamily.variants).selectinload(Product.packaging_specs).selectinload(PackagingSpec.item),
            selectinload(ProductFamily.boms).selectinload(BOM.items).selectinload(BOMItem.item),
        )
        .offset(skip)
        .limit(limit)
    )
    if is_active is not None:
        stmt = stmt.where(ProductFamily.is_active == is_active)
    return db.scalars(stmt).all()


@router.post("", response_model=ProductFamilyResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_ADMIN)])
def create_product_family(payload: ProductFamilyCreate, db: Session = Depends(get_db)):
    """Creates a new ProductFamily."""
    existing = db.scalar(select(ProductFamily).where(ProductFamily.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product family '{payload.name}' already exists",
        )

    family = ProductFamily(
        name=payload.name,
        hsn_code=payload.hsn_code,
        gst_rate_bp=payload.gst_rate_bp,
        is_active=payload.is_active,
    )
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


@router.get("/{family_id}", response_model=ProductFamilyResponse, dependencies=[Depends(ALLOW_READ)])
def get_product_family(family_id: int, db: Session = Depends(get_db)):
    family = db.scalar(
        select(ProductFamily)
        .options(
            selectinload(ProductFamily.variants).selectinload(Product.item),
            selectinload(ProductFamily.variants).selectinload(Product.packaging_specs).selectinload(PackagingSpec.item),
            selectinload(ProductFamily.boms).selectinload(BOM.items).selectinload(BOMItem.item),
        )
        .where(ProductFamily.id == family_id)
    )
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product family {family_id} not found")
    return family


@router.post("/{family_id}/variants", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_ADMIN)])
def create_variant(
    family_id: int,
    payload: ProductVariantCreate,
    db: Session = Depends(get_db),
):
    """
    In ONE transaction:
    1. Creates the finished-goods Item for this variant.
    2. Creates the Product variant linked to the family.
    3. Creates PackagingSpec rows (validates item_type is PACKAGING).
    4. Creates a PriceListItem entry on the default PriceList.
    """
    family = db.get(ProductFamily, family_id)
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product family {family_id} not found")

    # Validate packaging specs before making changes
    for pkg in payload.packaging:
        pkg_item = db.get(Item, pkg.item_id)
        if not pkg_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {pkg.item_id} not found")
        if pkg_item.item_type != ItemType.PACKAGING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PackagingSpec items must be of type PACKAGING (got {pkg_item.item_type.value})",
            )

    try:
        # 1. Create finished-goods Item
        finished_item = Item(
            name=payload.pack_name,
            item_type=ItemType.FINISHED_GOOD,
            base_unit="packet",
            display_unit="packet",
            hsn_code=family.hsn_code,
            gst_rate_bp=family.gst_rate_bp,
            opening_balance_qty=0,
            opening_rate_paise=Decimal("0.000000"),
        )
        db.add(finished_item)
        db.flush()

        # 2. Create Product variant
        product = Product(
            family_id=family.id,
            item_id=finished_item.id,
            pack_name=payload.pack_name,
            net_weight_g=payload.net_weight_g,
            packets_per_carton=payload.packets_per_carton,
            is_active=True,
        )
        db.add(product)
        db.flush()

        # 3. Create PackagingSpec rows
        for pkg in payload.packaging:
            ps = PackagingSpec(
                product_id=product.id,
                item_id=pkg.item_id,
                qty_base=pkg.qty_base,
                per_packets=pkg.per_packets,
                unit_for_display=pkg.unit_for_display or "piece",
            )
            db.add(ps)
            product.packaging_specs.append(ps)
        db.flush()

        # 4. Create PriceListItem entry
        price_list = db.scalar(
            select(PriceList).where(PriceList.is_default == True, PriceList.is_active == True)
        )
        if not price_list:
            price_list = db.scalar(select(PriceList).where(PriceList.is_active == True).limit(1))
        if price_list:
            selling_price_paise = int((payload.selling_price * Decimal("100")).quantize(Decimal("1")))
            pli = PriceListItem(
                price_list_id=price_list.id,
                product_id=product.id,
                price_paise=selling_price_paise,
                effective_from=datetime.now(timezone.utc),
            )
            db.add(pli)
            db.flush()

        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    refreshed_product = db.scalar(
        select(Product)
        .options(
            selectinload(Product.item),
            selectinload(Product.packaging_specs).selectinload(PackagingSpec.item),
        )
        .where(Product.id == product.id)
    )
    return refreshed_product


@router.get("/{family_id}/boms", response_model=list[BOMResponse], dependencies=[Depends(ALLOW_READ)])
def list_family_boms(family_id: int, db: Session = Depends(get_db)):
    """Lists all BOM versions for a product family."""
    family = db.get(ProductFamily, family_id)
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product family {family_id} not found")
    boms = db.scalars(
        select(BOM)
        .options(selectinload(BOM.items).selectinload(BOMItem.item))
        .where(BOM.family_id == family_id)
        .order_by(BOM.version.asc())
    ).all()
    return boms


@router.post("/{family_id}/boms", response_model=BOMResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_ADMIN)])
def create_family_bom(
    family_id: int,
    payload: BOMCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a new BOM version for this ProductFamily.
    Rejects any item that is not of type RAW_MATERIAL.
    """
    family = db.get(ProductFamily, family_id)
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product family {family_id} not found")

    # Validate raw material type constraint
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
            detail=f"BOM for Product Family {family_id} Version {payload.version} already exists",
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
    db.commit()
    db.refresh(bom)
    return bom


@router.post("/{family_id}/boms/{bom_id}/activate", response_model=BOMResponse, dependencies=[Depends(ALLOW_ADMIN)])
def activate_family_bom(family_id: int, bom_id: int, db: Session = Depends(get_db)):
    """Activates this BOM version and deactivates other versions for this family."""
    bom = db.scalar(
        select(BOM)
        .options(selectinload(BOM.items).selectinload(BOMItem.item))
        .where(BOM.id == bom_id, BOM.family_id == family_id)
    )
    if not bom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found for this family")

    db.execute(update(BOM).where(BOM.family_id == family_id).values(is_active=False))
    bom.is_active = True
    db.commit()
    db.refresh(bom)
    return bom
