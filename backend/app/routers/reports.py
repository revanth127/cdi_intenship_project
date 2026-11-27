"""Reports & exports: GET /reports/{name}?from=&to=&as_of=&format=json|csv|xlsx|pdf."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.services import report_export
from app.services.audit import log_audit
from app.services.reports import REPORTS, list_reports, parse_ist_date

router = APIRouter(prefix="/reports", tags=["reports"])

# ADMIN, ACCOUNTANT, OWNER: all reports. PRODUCTION: stock + production only. SALESMAN: none.
ALL_REPORTS_ROLES = (UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.OWNER, UserRole.PRODUCTION)
PRODUCTION_SCOPE_ROLES = (UserRole.PRODUCTION,)

REPORT_FORMATS = {"json", "csv", "xlsx", "pdf"}


def _can_access(user: User, report: dict) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.OWNER):
        return True
    if user.role == UserRole.PRODUCTION:
        return report.get("scope") == "production"
    return False


@router.get("", dependencies=[Depends(require_roles(*ALL_REPORTS_ROLES))])
def get_reports_index(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List available reports for the caller's role."""
    return list_reports(current_user.role.value)


@router.get("/{name}")
def get_report(
    name: str,
    format: str = Query("json", description="json | csv | xlsx | pdf"),
    from_: Optional[str] = Query(None, alias="from", description="Start business date (IST, YYYY-MM-DD), inclusive"),
    to: Optional[str] = Query(None, description="End business date (IST, YYYY-MM-DD), inclusive"),
    as_of: Optional[str] = Query(None, description="Point-in-time business date (IST, YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run a report and render it in the requested format."""
    if current_user.role == UserRole.SALESMAN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Salesman role has no report access")
    if name not in REPORTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown report '{name}'")
    report_meta = REPORTS[name]
    if not _can_access(current_user, report_meta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role lacks access to this report")
    fmt = (format or "json").lower()
    if fmt not in REPORT_FORMATS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown format '{format}'. Use json|csv|xlsx|pdf.")

    try:
        from_date: Optional[date] = parse_ist_date(from_)
        to_date: Optional[date] = parse_ist_date(to)
        as_of_date: Optional[date] = parse_ist_date(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date: {exc}") from exc

    result = report_meta["fn"](db, from_date, to_date, as_of_date)

    # Log every export in audit_log
    log_audit(
        db=db,
        user=current_user,
        action="REPORT_EXPORTED",
        entity_type="Report",
        entity_id=name,
        new_values={
            "report": name,
            "format": fmt,
            "from": from_,
            "to": to,
            "as_of": as_of,
            "row_count": len(result.get("rows", [])),
        },
    )
    db.commit()

    filename = f"{name}"
    if fmt == "json":
        return report_export.to_json(result)
    if fmt == "csv":
        return Response(
            content=report_export.to_csv(result),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )
    if fmt == "xlsx":
        return Response(
            content=report_export.to_xlsx(result),
            media_type=report_export.CONTENT_TYPES["xlsx"],
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )
    return Response(
        content=report_export.to_pdf(result),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )
