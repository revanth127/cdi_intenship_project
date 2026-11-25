from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models.company import CompanySettings
from app.models.user import UserRole
from app.schemas.company import (
    CompanySettingsCreate,
    CompanySettingsResponse,
    CompanySettingsUpdate,
)

router = APIRouter(prefix="/company-settings", tags=["Company"])

# RBAC Permissions:
# Read: ADMIN, OWNER, ACCOUNTANT
# Write: ADMIN
ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)
ALLOW_WRITE = require_roles(UserRole.ADMIN)


@router.get("", response_model=CompanySettingsResponse, dependencies=[Depends(ALLOW_READ)])
def get_company_settings(db: Session = Depends(get_db)):
    settings = db.get(CompanySettings, 1)
    if not settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company settings not configured yet")
    return settings


@router.put("", response_model=CompanySettingsResponse, dependencies=[Depends(ALLOW_WRITE)])
def update_or_create_company_settings(payload: CompanySettingsCreate, db: Session = Depends(get_db)):
    settings = db.get(CompanySettings, 1)
    if not settings:
        settings = CompanySettings(id=1, **payload.model_dump())
        db.add(settings)
    else:
        for field, val in payload.model_dump(exclude_unset=True).items():
            setattr(settings, field, val)

    db.commit()
    db.refresh(settings)
    return settings
