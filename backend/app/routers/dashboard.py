from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.user import UserRole
from app.schemas.dashboard import DashboardSummaryResponse
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Executive Dashboard"])

ALLOW_DASHBOARD_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)


@router.get("/summary", response_model=DashboardSummaryResponse, dependencies=[Depends(ALLOW_DASHBOARD_READ)])
def get_dashboard_summary(
    range: str = Query("today", pattern="^(today|7d|30d|mtd)$", description="Date range: today, 7d, 30d, mtd"),
    as_of: Optional[str] = Query(None, description="Point-in-time calculation (ISO datetime format)"),
    db: Session = Depends(get_db),
):
    """
    Returns unified executive dashboard payload:
    - today: orders received (count, value), orders pending approval, invoices raised, dispatches made, payments collected
    - stock: per finished product on-hand and available-to-promise; raw and packaging items below reorder level (or lowest 5)
    - variance_alerts: last 30 days of flagged production lines, newest first (run no, item, planned, actual, variance %)
    - receivables: total outstanding, ageing buckets, top 5 customers by dues
    - costing: per product cost per packet, selling price, margin %
    - sales_trend: daily taxable sales for the last 30 days
    Permissions: OWNER, ADMIN, and ACCOUNTANT. (SALESMAN and PRODUCTION no access).
    """
    return dashboard_service.get_dashboard_summary(db=db, as_of=as_of, range_param=range)
