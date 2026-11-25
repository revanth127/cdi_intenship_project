from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PriceListBase(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=255)
    is_default: bool = False
    is_active: bool = True


class PriceListCreate(PriceListBase):
    pass


class PriceListItemBase(BaseModel):
    price_list_id: int
    product_id: int
    price_paise: int = Field(..., ge=0, description="Price per packet in integer paise")
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class PriceListItemCreate(PriceListItemBase):
    pass


class PriceListItemResponse(PriceListItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    effective_from: datetime


class PriceListResponse(PriceListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    items: list[PriceListItemResponse] = []


class CustomerPriceOverrideBase(BaseModel):
    customer_id: int
    product_id: int
    price_paise: int = Field(..., ge=0)
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class CustomerPriceOverrideCreate(CustomerPriceOverrideBase):
    pass


class CustomerPriceOverrideResponse(CustomerPriceOverrideBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    effective_from: datetime
