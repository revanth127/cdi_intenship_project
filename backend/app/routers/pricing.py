from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.pricing import CustomerPriceOverride, PriceList, PriceListItem
from app.models.user import UserRole
from app.schemas.pricing import (
    CustomerPriceOverrideCreate,
    CustomerPriceOverrideResponse,
    PriceListCreate,
    PriceListItemCreate,
    PriceListItemResponse,
    PriceListResponse,
)

router = APIRouter(prefix="/pricing", tags=["Pricing"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT, SALESMAN
# Write: ADMIN
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("/price-lists", response_model=list[PriceListResponse], dependencies=[Depends(ALLOW_READ)])
def list_price_lists(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(PriceList).options(selectinload(PriceList.items)).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("/price-lists", response_model=PriceListResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_price_list(payload: PriceListCreate, db: Session = Depends(get_db)):
    price_list = PriceList(**payload.model_dump())
    db.add(price_list)
    db.commit()
    db.refresh(price_list)
    return price_list


@router.post("/price-list-items", response_model=PriceListItemResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def add_price_list_item(payload: PriceListItemCreate, db: Session = Depends(get_db)):
    item = PriceListItem(**payload.model_dump(exclude_unset=True))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/customer-overrides", response_model=CustomerPriceOverrideResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def add_customer_override(payload: CustomerPriceOverrideCreate, db: Session = Depends(get_db)):
    override = CustomerPriceOverride(**payload.model_dump(exclude_unset=True))
    db.add(override)
    db.commit()
    db.refresh(override)
    return override
