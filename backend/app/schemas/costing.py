from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.costing import OverheadCategory, OverheadStatus


class OverheadCreate(BaseModel):
    category: OverheadCategory = Field(..., description="LABOUR, GAS, POWER, or OTHER")
    amount_paise: int = Field(..., gt=0, description="Amount in positive integer paise")
    production_run_id: Optional[int] = Field(None, description="Optional link to specific run")
    month: Optional[str] = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Month in YYYY-MM format when not linked to a run")
    entry_date: Optional[datetime] = Field(None, description="Date of expenditure (defaults to now UTC)")
    description: Optional[str] = Field(None, description="Detailed description of overhead expenditure")


class OverheadVoid(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory audit reason for voiding overhead entry")


class OverheadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: datetime
    category: OverheadCategory
    amount_paise: int
    production_run_id: Optional[int] = None
    month: Optional[str] = None
    description: Optional[str] = None
    status: OverheadStatus
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime


class MaterialConsumptionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    item_name: str
    base_unit: str
    display_unit: str
    quantity_base: int
    unit_cost_paise: Decimal
    value_paise: int


class AllocatedOverheadLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overhead_id: int
    category: OverheadCategory
    description: Optional[str] = None
    is_direct: bool
    total_entry_amount_paise: int
    allocated_amount_paise: int


class RunCostSheetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    material_cost_paise: int
    labour_paise: int
    gas_power_paise: int
    other_paise: int
    total_cost_paise: int
    good_packets: int
    cost_per_packet: Decimal
    planned_cost_per_packet: Decimal
    cost_of_loss_paise: int
    computed_at: datetime


class RunCostDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    run_no: str
    product_id: int
    product_name: str
    run_date: datetime
    status: str
    expected_output_packets: int
    good_packets: int
    wastage_packets: Optional[int] = None
    yield_variance_pct: Optional[Decimal] = None
    material_cost_paise: int
    material_cost_per_packet: Decimal
    material_breakdown: list[MaterialConsumptionItem] = []
    labour_paise: int
    gas_power_paise: int
    other_paise: int
    total_overheads_paise: int
    overhead_cost_per_packet: Decimal
    overheads_breakdown: list[AllocatedOverheadLine] = []
    total_cost_paise: int
    cost_per_packet: Decimal
    cost_per_packet_4dp: Decimal
    planned_cost_per_packet: Decimal
    cost_of_loss_paise: int
    computed_at: datetime


class ProductCostSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    total_material_paise: int
    total_overheads_paise: int
    total_cost_paise: int
    good_packets: int
    cost_per_packet: Decimal
    cost_per_packet_4dp: Decimal
    selling_price_paise: int
    selling_price: Decimal
    margin_per_packet: Decimal
    margin_pct: Decimal
    gst_rate_bp: int
    price_before_tax: Decimal
    margin_after_gst_excluded: Decimal
    runs_count: int


class RunCostListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    run_no: str
    product_id: int
    product_name: str
    run_date: datetime
    status: str
    good_packets: int
    material_cost_paise: int
    overhead_paise: int
    total_cost_paise: int
    cost_per_packet: Decimal
    cost_per_packet_4dp: Decimal
