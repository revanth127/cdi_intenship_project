from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.item import Item, ItemType
from app.models.user import UserRole
from app.schemas.item import ItemCreate, ItemResponse, ItemUpdate

router = APIRouter(prefix="/items", tags=["Items"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT, PRODUCTION
# Write: ADMIN
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[ItemResponse], dependencies=[Depends(ALLOW_READ)])
def list_items(
    item_type: ItemType | None = None,
    is_active: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Item).where(Item.is_active == is_active)
    if item_type:
        stmt = stmt.where(Item.item_type == item_type)
    stmt = stmt.offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Item).where(Item.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item with name {payload.name!r} already exists",
        )
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=ItemResponse, dependencies=[Depends(ALLOW_READ)])
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.put("/{item_id}", response_model=ItemResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(item, field, val)

    db.commit()
    db.refresh(item)
    return item
