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

    @property
    def quantity_per_batch_base(self) -> int:
        return self.quantity_per_batch

    @property
    def tolerance_override(self) -> Optional[Decimal]:
        return self.variance_tolerance_pct


class BOMItemCreate(BaseModel):
    item_id: int
    quantity_per_batch: Optional[int] = Field(None, gt=0)
    quantity_per_batch_base: Optional[int] = Field(None, gt=0)
    unit_for_display: str = Field("kg", max_length=16)
    variance_tolerance_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    tolerance_override: Optional[Decimal] = Field(None, ge=0, le=100)

    def model_post_init(self, __context):
        if self.quantity_per_batch is None and self.quantity_per_batch_base is not None:
            self.quantity_per_batch = self.quantity_per_batch_base
        elif self.quantity_per_batch is not None and self.quantity_per_batch_base is None:
            self.quantity_per_batch_base = self.quantity_per_batch
        if self.variance_tolerance_pct is None and self.tolerance_override is not None:
            self.variance_tolerance_pct = self.tolerance_override
        elif self.variance_tolerance_pct is not None and self.tolerance_override is None:
            self.tolerance_override = self.variance_tolerance_pct


class BOMItemResponse(BOMItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bom_id: int
    item: Optional[ItemResponse] = None


class BOMBase(BaseModel):
    family_id: Optional[int] = None
    product_id: Optional[int] = None
    version: int = Field(1, gt=0)
    expected_output_g: int = Field(40000, gt=0, description="Expected finished output grams per batch")
    batch_output_packets: Optional[int] = Field(None, description="Calculated packets yield")
    is_active: bool = True


class BOMCreate(BOMBase):
    items: list[BOMItemCreate] = []


class BOMResponse(BOMBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    items: list[BOMItemResponse] = []
