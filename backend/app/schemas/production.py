from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.production import ProductionRunStatus
from app.schemas.item import ItemResponse


class ProductionRunLineBase(BaseModel):
    item_id: int
    planned_qty_base: int = Field(..., ge=0)
    actual_qty_base: Optional[int] = Field(None, ge=0)
    damaged_qty_base: int = Field(0, ge=0)
    variance_qty_base: Optional[int] = None
    variance_pct: Optional[Decimal] = None
    is_flagged: bool = False
    unit_cost: Optional[Decimal] = None
    value_paise: Optional[int] = None
    unit_for_display: str


class ProductionRunLineUpdate(BaseModel):
    item_id: int
    actual_qty_base: Optional[int] = Field(None, ge=0)
    actual_qty: Optional[Decimal] = Field(None, ge=0, description="Quantity in display unit (kg, L, etc.)")
    unit: Optional[str] = Field(None, description="Optional unit override (e.g. 'kg', 'L', 'piece')")
    damaged_qty_base: Optional[int] = Field(None, ge=0)
    damaged_qty: Optional[Decimal] = Field(None, ge=0, description="Damaged quantity in display unit")


class ProductionRunLineResponse(ProductionRunLineBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    item: Optional[ItemResponse] = None


class ProductionRunCreate(BaseModel):
    product_id: int
    bom_id: Optional[int] = None
    batches: Optional[Decimal] = Field(None, gt=0, description="Number of standard batches to produce")
    batch_size: Optional[int] = Field(None, gt=0, description="Target packets to produce")
    batch_size_packets: Optional[int] = Field(None, gt=0, description="Target packets to produce")
    run_date: Optional[datetime] = None
    notes: Optional[str] = None


class ProductionRunUpdate(BaseModel):
    actual_good_packets: Optional[int] = Field(None, ge=0)
    run_date: Optional[datetime] = None
    notes: Optional[str] = None
    lines: list[ProductionRunLineUpdate] = []


class ProductionRunCancel(BaseModel):
    reason: str = Field(..., min_length=3, description="Audit reason for cancelling the production run")


class LineVarianceReport(BaseModel):
    item_id: int
    item_name: str
    display_unit: str
    planned_qty_base: int
    actual_qty_base: Optional[int] = None
    difference_qty_base: Optional[int] = None  # actual - planned
    variance_pct: Optional[Decimal] = None
    tolerance_pct: Decimal
    is_flagged: bool = False
    damaged_qty_base: int = 0
    unit_cost_paise: Optional[Decimal] = None
    value_paise: Optional[int] = None


class YieldVarianceReport(BaseModel):
    expected_output_packets: int
    actual_good_packets: Optional[int] = None
    wastage_packets: Optional[int] = None
    yield_variance_pct: Optional[Decimal] = None
    tolerance_pct: Decimal
    is_flagged: bool = False


class ProductionRunVarianceReport(BaseModel):
    yield_report: YieldVarianceReport
    lines: list[LineVarianceReport]


class ProductionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_no: str
    product_id: int
    bom_id: int
    bom_version: int
    run_date: datetime
    batches: Decimal
    batch_size_packets: Optional[int] = None
    status: ProductionRunStatus
    expected_output_packets: int
    actual_good_packets: Optional[int] = None
    wastage_packets: Optional[int] = None
    yield_variance_pct: Optional[Decimal] = None
    is_yield_flagged: bool = False
    total_material_cost_paise: Optional[int] = None
    unit_material_cost_paise: Optional[Decimal] = None
    created_by: int
    posted_by: Optional[int] = None
    posted_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: list[ProductionRunLineResponse] = []
    variance_report: Optional[ProductionRunVarianceReport] = None


class VarianceAlertLine(BaseModel):
    item_id: int
    item_name: str
    display_unit: str
    planned_qty_base: int
    actual_qty_base: int
    variance_qty_base: int
    variance_pct: Decimal
    tolerance_pct: Decimal
    damaged_qty_base: int = 0


class VarianceAlertResponse(BaseModel):
    run_id: int
    run_no: str
    product_id: int
    product_name: str
    run_date: datetime
    status: ProductionRunStatus
    expected_output_packets: int
    actual_good_packets: Optional[int] = None
    wastage_packets: Optional[int] = None
    yield_variance_pct: Optional[Decimal] = None
    is_yield_flagged: bool = False
    tolerance_pct: Decimal
    flagged_lines: list[VarianceAlertLine] = []
