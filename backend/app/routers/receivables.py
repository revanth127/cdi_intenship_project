from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.customer import Customer
from app.models.user import User, UserRole
from app.services.audit import log_audit
from app.schemas.payment import PaymentAllocationResponse
from app.schemas.receivables import (
    CollectionsSummaryResponse,
    CustomerOutstandingResponse,
    CustomerStatementResponse,
    ReceivablesAgeingResponse,
)
from app.services import receivables as receivables_service

router = APIRouter(tags=["Receivables & Ageing"])

ALLOW_ADMIN = require_roles(UserRole.ADMIN)
ALLOW_MANAGEMENT = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)
ALLOW_AUTH = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN)


@router.get("/receivables/outstanding", dependencies=[Depends(ALLOW_AUTH)])
def get_outstanding(
    customer_id: Optional[int] = Query(None, description="Optional customer ID"),
    as_of: Optional[str] = Query(None, description="Point-in-time calculation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Computes outstanding balances per customer and per open invoice.
    Salesmen may only view outstandings for their own assigned customers.
    """
    target_dt = receivables_service.parse_datetime(as_of)
    if customer_id:
        customer = db.get(Customer, customer_id)
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

        # Salesman row-level isolation
        if current_user.role == UserRole.SALESMAN and customer.assigned_salesman_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

        return receivables_service.get_customer_outstanding(db=db, customer_id=customer_id, as_of=target_dt)
    else:
        # Multiple customers
        if current_user.role == UserRole.SALESMAN:
            customers = db.scalars(
                select(Customer).where(Customer.assigned_salesman_id == current_user.id, Customer.is_active == True)
            ).all()
        else:
            customers = db.scalars(
                select(Customer).where(Customer.is_active == True).order_by(Customer.name.asc())
            ).all()

        return [
            receivables_service.get_customer_outstanding(db=db, customer_id=c.id, as_of=target_dt)
            for c in customers
        ]


@router.get("/receivables/ageing", response_model=ReceivablesAgeingResponse, dependencies=[Depends(ALLOW_AUTH)])
def get_ageing(
    as_of: Optional[str] = Query(None, description="Cut-off date for ageing calculation"),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculates statutory receivables ageing report with 0-30, 31-60, 61-90, 90+ day buckets.
    Salesmen can only see ageing for their own assigned customers.
    """
    target_dt = receivables_service.parse_datetime(as_of)
    salesman_id = current_user.id if current_user.role == UserRole.SALESMAN else None

    if customer_id and current_user.role == UserRole.SALESMAN:
        cust = db.get(Customer, customer_id)
        if not cust or cust.assigned_salesman_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    res = receivables_service.get_receivables_ageing(
        db=db,
        as_of=target_dt,
        customer_id=customer_id,
        salesman_id=salesman_id,
    )
    log_audit(
        db=db,
        user=current_user,
        action="REPORT_EXPORTED",
        entity_type="ReceivablesAgeing",
        entity_id="ageing",
        new_values={"customer_id": customer_id, "as_of": as_of},
    )
    db.commit()
    return res


@router.get("/receivables/collections", response_model=CollectionsSummaryResponse, dependencies=[Depends(ALLOW_MANAGEMENT)])
def get_collections(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """
    Returns collections summary grouped by payment mode (Cash, UPI, Bank, Cheque) and by day.
    """
    start_dt = receivables_service.parse_datetime(from_date)
    end_dt = receivables_service.parse_datetime(to_date)
    return receivables_service.get_collections_summary(db=db, from_date=start_dt, to_date=end_dt)


@router.get("/customers/{customer_id}/statement", response_model=CustomerStatementResponse, dependencies=[Depends(ALLOW_AUTH)])
def get_customer_statement(
    customer_id: int,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates a formal Customer Statement of Account with opening balance,
    invoices (debit), credit notes (credit), payments (credit), and running balance.
    Closing balance matches customer outstanding balance.
    """
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    if current_user.role == UserRole.SALESMAN and customer.assigned_salesman_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    start_dt = receivables_service.parse_datetime(from_date)
    end_dt = receivables_service.parse_datetime(to_date)
    res = receivables_service.get_customer_statement(
        db=db, customer_id=customer_id, from_date=start_dt, to_date=end_dt
    )
    log_audit(
        db=db,
        user=current_user,
        action="REPORT_EXPORTED",
        entity_type="CustomerStatement",
        entity_id=str(customer_id),
        new_values={"from": from_date, "to": to_date},
    )
    db.commit()
    return res


@router.post("/customers/{customer_id}/allocate-advance", response_model=list[PaymentAllocationResponse], dependencies=[Depends(ALLOW_ADMIN)])
def allocate_advance(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Applies existing customer advance from POSTED payments to open invoices (FIFO, Admin only).
    """
    return receivables_service.allocate_advance(db=db, customer_id=customer_id, user=current_user)
