from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    name: str = Field(..., max_length=255)
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    state_code: str = Field(..., min_length=2, max_length=2)
    address: Optional[str] = None
    phone: str = Field(..., max_length=32)
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=32)
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
