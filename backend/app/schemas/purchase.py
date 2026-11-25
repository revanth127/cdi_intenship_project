from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.purchase import PurchaseStatus


class PurchaseLineCreate(BaseModel):
    item_id: int
    quantity_entered: Decimal = Field(..., gt=0, description="Quantity in commercial unit (e.g. 60 for 60 kg)")
    unit_entered: str = Field(..., max_length=16, description="Commercial unit (e.g. 'kg', 'L', 'piece')")
    rate_paise: int = Field(..., gt=0, description="Purchase rate per entered unit in whole paise (e.g. 4500 for Rs 45/kg)")


class PurchaseLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_id: int
    item_id: int
    quantity_base: int
    unit_entered: str
    rate_paise: int
    line_total_paise: int


class PurchaseCreate(BaseModel):
    supplier_id: int
    supplier_invoice_no: Optional[str] = Field(None, max_length=64)
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None
    lines: list[PurchaseLineCreate] = Field(..., min_length=1)


class PurchaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_no: str
    supplier_id: int
    supplier_invoice_no: Optional[str] = None
    purchase_date: datetime
    status: PurchaseStatus
    total_paise: int
    created_by: Optional[int] = None
    notes: Optional[str] = None
    lines: list[PurchaseLineResponse] = []
