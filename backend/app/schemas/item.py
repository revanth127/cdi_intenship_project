from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.item import ItemType


class ItemBase(BaseModel):
    name: str = Field(..., max_length=255)
    item_type: ItemType
    base_unit: str = Field(..., max_length=16, description="Base unit: 'g', 'ml', 'piece', 'packet'")
    display_unit: str = Field(..., max_length=16, description="Commercial unit: 'kg', 'L', 'piece', 'packet'")
    hsn_code: Optional[str] = Field(None, max_length=16)
    gst_rate_bp: int = Field(0, ge=0, le=10000, description="GST rate in basis points (500 = 5%)")
    reorder_level: Optional[int] = Field(None, ge=0, description="Reorder level in base units")
    is_active: bool = True
    opening_balance_qty: Optional[int] = Field(None, ge=0, description="Opening stock in base units")
    opening_rate_paise: Optional[Decimal] = Field(None, ge=0, description="Rate in paise per base unit")


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    item_type: Optional[ItemType] = None
    base_unit: Optional[str] = Field(None, max_length=16)
    display_unit: Optional[str] = Field(None, max_length=16)
    hsn_code: Optional[str] = Field(None, max_length=16)
    gst_rate_bp: Optional[int] = Field(None, ge=0, le=10000)
    reorder_level: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    opening_balance_qty: Optional[int] = Field(None, ge=0)
    opening_rate_paise: Optional[Decimal] = Field(None, ge=0)


class ItemResponse(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
