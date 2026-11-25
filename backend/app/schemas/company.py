from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CompanySettingsBase(BaseModel):
    company_name: str = Field(..., max_length=255)
    gstin: str = Field(..., min_length=15, max_length=15)
    state_code: str = Field("33", min_length=2, max_length=2, description="Default: 33 for Tamil Nadu")
    address: str
    financial_year_start_month: int = Field(4, ge=1, le=12, description="1-12 (April=4)")
    variance_tolerance_pct: Decimal = Field(Decimal("3.00"), ge=0, description="Allowed variance % in production")
    invoice_prefix: str = Field("INV-", max_length=16)


class CompanySettingsCreate(CompanySettingsBase):
    pass


class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = Field(None, max_length=255)
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    address: Optional[str] = None
    financial_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    variance_tolerance_pct: Optional[Decimal] = Field(None, ge=0)
    invoice_prefix: Optional[str] = Field(None, max_length=16)


class CompanySettingsResponse(CompanySettingsBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
