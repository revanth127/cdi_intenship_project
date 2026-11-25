from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.item import ItemResponse


class BOMItemBase(BaseModel):
    item_id: int
    quantity_per_batch: int = Field(..., gt=0, description="Quantity per batch in BASE UNITS (e.g. 40000 for 40 kg)")
    unit_for_display: str = Field(..., max_length=16, description="Unit for human display, e.g. 'kg'")
    variance_tolerance_pct: Optional[Decimal] = Field(
        None, ge=0, le=100, description="Optional override variance tolerance percentage for this item"
    )


class BOMItemCreate(BOMItemBase):
    pass


class BOMItemResponse(BOMItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bom_id: int
    item: Optional[ItemResponse] = None


class BOMBase(BaseModel):
    product_id: int
    version: int = Field(1, gt=0)
    batch_output_packets: int = Field(..., gt=0, description="Standard batch yield in packets")
    is_active: bool = True


class BOMCreate(BOMBase):
    items: list[BOMItemCreate] = []


class BOMResponse(BOMBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    items: list[BOMItemResponse] = []
