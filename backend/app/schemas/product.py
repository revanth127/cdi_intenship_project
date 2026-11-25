from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.item import ItemResponse


class ProductBase(BaseModel):
    item_id: int
    pack_size_desc: str = Field(..., max_length=64, description="E.g. '200 g'")
    packets_per_carton: int = Field(20, gt=0, description="Packets packed in 1 shipper carton")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    pack_size_desc: Optional[str] = Field(None, max_length=64)
    packets_per_carton: Optional[int] = Field(None, gt=0)


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item: Optional[ItemResponse] = None
