from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.item import ItemResponse


class VariantPackagingCreate(BaseModel):
    item_id: int = Field(..., description="ID of packaging Item (must be PACKAGING type)")
    qty_base: int = Field(1, gt=0, description="Base units of packaging item")
    per_packets: int = Field(1, gt=0, description="Per number of finished packets (e.g. 1 per 1, or 1 per 20)")
    unit_for_display: str = Field("piece", description="Display unit, e.g. 'piece'")


class PackagingSpecResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    item_id: int
    qty_base: int
    per_packets: int
    unit_for_display: str
    item: Optional[ItemResponse] = None


class ProductBase(BaseModel):
    item_id: int
    family_id: Optional[int] = None
    pack_name: Optional[str] = None
    pack_size_desc: Optional[str] = Field(None, max_length=64, description="E.g. '200 g'")
    net_weight_g: int = Field(200, gt=0, description="Net weight in grams")
    packets_per_carton: int = Field(20, gt=0, description="Packets packed in 1 shipper carton")
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    pack_name: Optional[str] = None
    pack_size_desc: Optional[str] = Field(None, max_length=64)
    net_weight_g: Optional[int] = Field(None, gt=0)
    packets_per_carton: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item: Optional[ItemResponse] = None
    packaging_specs: list[PackagingSpecResponse] = []
