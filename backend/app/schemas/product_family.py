from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bom import BOMResponse
from app.schemas.item import ItemResponse
from app.schemas.product import PackagingSpecResponse, ProductResponse, VariantPackagingCreate


class ProductVariantCreate(BaseModel):
    pack_name: str = Field(..., max_length=128, description="Commercial pack name, e.g. 'Murukku 500 g'")
    net_weight_g: int = Field(..., gt=0, description="Net weight in grams")
    packets_per_carton: int = Field(..., gt=0, description="Number of packets per outer carton")
    selling_price: Decimal = Field(..., gt=0, description="Selling price per packet in Rupees (e.g. 120.00)")
    packaging: list[VariantPackagingCreate] = Field(default_factory=list, description="Packaging specifications")


class ProductFamilyBase(BaseModel):
    name: str = Field(..., max_length=128, description="Product family name, e.g. 'Murukku'")
    hsn_code: str = Field(..., max_length=16, description="HSN/SAC code")
    gst_rate_bp: int = Field(500, ge=0, description="GST rate in basis points (500 = 5.00%)")
    is_active: bool = True


class ProductFamilyCreate(ProductFamilyBase):
    pass


class ProductFamilyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    hsn_code: Optional[str] = Field(None, max_length=16)
    gst_rate_bp: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ProductFamilyResponse(ProductFamilyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    variants: list[ProductResponse] = []
    boms: list[BOMResponse] = []
