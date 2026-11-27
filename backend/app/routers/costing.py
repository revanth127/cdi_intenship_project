from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.product import Product
from app.models.user import UserRole
from app.schemas.costing import (
    ProductCostSummaryResponse,
    RunCostDetailResponse,
    RunCostListItemResponse,
)
from app.services import costing as costing_service

router = APIRouter(prefix="/costing", tags=["Costing & Margins"])

ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)


@router.get("/runs/{run_id}", response_model=RunCostDetailResponse, dependencies=[Depends(ALLOW_READ)])
def get_run_cost(
    run_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieves full costing breakdown for a production run:
    - Material cost from stock ledger PRODUCTION_ISSUE rows.
    - Overheads (direct + allocated monthly share).
    - Cost per packet (absorbing wastage and yield loss).
    - Planned standard cost from BOM.
    - Cost of loss.
    Allowed roles: ADMIN, OWNER, ACCOUNTANT. (SALESMAN no access).
    """
    return costing_service.run_cost(db=db, run_id=run_id)


@router.get("/runs", response_model=list[RunCostListItemResponse], dependencies=[Depends(ALLOW_READ)])
def list_runs_cost(
    from_date: Optional[str] = Query(None, alias="from", description="Start date filter"),
    to_date: Optional[str] = Query(None, alias="to", description="End date filter"),
    db: Session = Depends(get_db),
):
    """
    Lists POSTED production runs with cost per packet each.
    Allowed roles: ADMIN, OWNER, ACCOUNTANT. (SALESMAN no access).
    """
    start_dt = costing_service.parse_datetime(from_date)
    end_dt = costing_service.parse_datetime(to_date)
    return costing_service.list_runs_cost(db=db, from_date=start_dt, to_date=end_dt)


@router.get("/products", response_model=list[ProductCostSummaryResponse], dependencies=[Depends(ALLOW_READ)])
def get_products_cost_summary(
    product_id: Optional[int] = Query(None, description="Optional single product filter"),
    from_date: Optional[str] = Query(None, alias="from", description="Start date filter"),
    to_date: Optional[str] = Query(None, alias="to", description="End date filter"),
    db: Session = Depends(get_db),
):
    """
    Computes per product:
    total material, overheads, total cost, good packets, cost per packet,
    selling price, margin per packet, margin %.
    Weighted average across runs, NOT an average of per-run costs!
    Allowed roles: ADMIN, OWNER, ACCOUNTANT. (SALESMAN no access).
    """
    start_dt = costing_service.parse_datetime(from_date)
    end_dt = costing_service.parse_datetime(to_date)

    if product_id:
        return [costing_service.product_cost_summary(db=db, product_id=product_id, from_date=start_dt, to_date=end_dt)]

    products = db.scalars(select(Product).order_by(Product.id.asc())).all()
    return [
        costing_service.product_cost_summary(db=db, product_id=p.id, from_date=start_dt, to_date=end_dt)
        for p in products
    ]
