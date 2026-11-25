from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.item import Item, ItemType
from app.models.product import Product
from app.models.user import UserRole
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT, PRODUCTION, SALESMAN
# Write: ADMIN
ALLOW_READ = require_roles(
    UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION, UserRole.SALESMAN
)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[ProductResponse], dependencies=[Depends(ALLOW_READ)])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Product).options(selectinload(Product.item)).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    item = db.get(Item, payload.item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    if item.item_type != ItemType.FINISHED_GOOD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only items of type FINISHED_GOOD can be configured as a Product (got {item.item_type})",
        )

    existing = db.scalar(select(Product).where(Product.item_id == payload.item_id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists for this Item")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductResponse, dependencies=[Depends(ALLOW_READ)])
def get_product(product_id: int, db: Session = Depends(get_db)):
    stmt = select(Product).options(selectinload(Product.item)).where(Product.id == product_id)
    product = db.scalar(stmt)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(product, field, val)

    db.commit()
    db.refresh(product)
    return product
