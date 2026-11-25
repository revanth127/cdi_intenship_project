from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.schemas.supplier import SupplierCreate, SupplierResponse, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT
# Write: ADMIN
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[SupplierResponse], dependencies=[Depends(ALLOW_READ)])
def list_suppliers(
    is_active: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Supplier).where(Supplier.is_active == is_active).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)):
    if payload.gstin:
        existing = db.scalar(select(Supplier).where(Supplier.gstin == payload.gstin))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Supplier with GSTIN {payload.gstin} already exists",
            )

    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/{supplier_id}", response_model=SupplierResponse, dependencies=[Depends(ALLOW_READ)])
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.put("/{supplier_id}", response_model=SupplierResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(supplier, field, val)

    db.commit()
    db.refresh(supplier)
    return supplier
