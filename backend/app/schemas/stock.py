from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.stock import MovementType


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    movement_date: datetime
    movement_type: MovementType
    quantity_base: int
    unit_cost: Decimal
    value_paise: int
    source_type: str
    source_id: Optional[str] = None
    reverses_movement_id: Optional[int] = None
    batch_no: Optional[str] = None
    created_by: Optional[int] = None
    note: Optional[str] = None


class StockAdjustmentCreate(BaseModel):
    item_id: int
    delta: int = Field(..., description="Signed base units delta (+ to add stock, - to reduce)")
    reason: str = Field(..., min_length=3, max_length=255, description="Mandatory audit explanation")
    unit_cost: Optional[Decimal] = Field(None, description="Optional unit cost override in paise per base unit")


class StockSummaryResponse(BaseModel):
    item_id: int
    name: str
    item_type: str
    base_unit: str
    display_unit: str
    opening_balance_base: int
    receipts_base: int
    issues_base: int
    adjustments_base: int
    closing_balance_base: int
    closing_balance_display: str
    weighted_avg_cost_paise: Decimal
    total_value_paise: int
    total_value_rupees: str
    reconciled: bool


class StockLedgerEntryResponse(BaseModel):
    id: int
    date: datetime
    movement_type: str
    in_qty_base: int
    out_qty_base: int
    running_balance_base: int
    unit_cost: Decimal
    value_paise: int
    source_type: str
    source_id: Optional[str] = None
    reverses_movement_id: Optional[int] = None
    created_by: Optional[int] = None
    note: Optional[str] = None


class StockReconciliationResponse(BaseModel):
    status: str
    total_items_checked: int
    mismatches: list[dict[str, Any]] = []
