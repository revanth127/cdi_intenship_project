from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.customer import Customer
from app.models.user import User, UserRole
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["Customers"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT, SALESMAN (SALESMAN reads only assigned customers)
# Write: ADMIN
ALLOW_READ_ROLES = (UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    is_active: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOW_READ_ROLES)),
):
    stmt = select(Customer).where(Customer.is_active == is_active)

    # Scoped row-level access control: Salesmen can only access their assigned customers
    if current_user.role == UserRole.SALESMAN:
        stmt = stmt.where(Customer.assigned_salesman_id == current_user.id)

    stmt = stmt.offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ALLOW_WRITE)])
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    if payload.gstin:
        existing = db.scalar(select(Customer).where(Customer.gstin == payload.gstin))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Customer with GSTIN {payload.gstin} already exists",
            )

    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOW_READ_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Enforce row-level isolation for salesmen
    if current_user.role == UserRole.SALESMAN and customer.assigned_salesman_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you are not assigned to this customer",
        )

    return customer


@router.put("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(customer, field, val)

    db.commit()
    db.refresh(customer)
    return customer
