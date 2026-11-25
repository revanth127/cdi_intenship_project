from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.customer import CustomerType


class CustomerBase(BaseModel):
    name: str = Field(..., max_length=255)
    customer_type: CustomerType
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    state_code: str = Field(..., min_length=2, max_length=2, description="2-digit State Code (e.g. '33')")
    address: str
    phone: str = Field(..., max_length=32)
    assigned_salesman_id: Optional[int] = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    customer_type: Optional[CustomerType] = None
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=32)
    assigned_salesman_id: Optional[int] = None
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
