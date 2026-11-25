from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.customer import CustomerType
from app.models.order import OrderStatus, PriceSource


class OrderLineCreate(BaseModel):
    product_id: int
    quantity_packets: int = Field(..., gt=0, description="Quantity in packets requested")


class OrderCreate(BaseModel):
    client_uuid: str = Field(..., min_length=1, max_length=64, description="Idempotency key from mobile client")
    customer_id: int
    notes: Optional[str] = None
    lines: list[OrderLineCreate] = Field(..., min_length=1, description="Order line items")


class OrderLineUpdate(BaseModel):
    id: Optional[int] = None
    product_id: int
    quantity_packets: int = Field(..., gt=0)
    unit_price_paise: Optional[int] = Field(None, ge=0)


class OrderUpdate(BaseModel):
    notes: Optional[str] = None
    lines: Optional[list[OrderLineUpdate]] = None


class OrderReject(BaseModel):
    reason: str = Field(..., min_length=3, description="Audit reason for rejecting the order")


class OrderApprove(BaseModel):
    approve_with_shortage: bool = Field(False, description="Explicit admin override to approve despite stock shortage")


class StockAvailabilityLine(BaseModel):
    product_id: int
    product_name: str
    requested: int
    on_hand: int
    committed_elsewhere: int
    available: int
    shortage: int
    ok: bool


class TaxSummaryResponse(BaseModel):
    is_intra_state: bool
    taxable_amount_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_tax_paise: int
    grand_total_paise: int


class OrderLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    product_id: int
    product_name: Optional[str] = None
    quantity_packets: int
    unit_price_paise: int
    line_total_paise: int
    price_source: PriceSource
    stock_availability: Optional[StockAvailabilityLine] = None


class OrderStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    from_status: Optional[OrderStatus] = None
    to_status: OrderStatus
    user_id: Optional[int] = None
    timestamp: datetime
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    client_uuid: str
    customer_id: int
    customer_name: Optional[str] = None
    salesman_id: int
    salesman_name: Optional[str] = None
    order_date: datetime
    status: OrderStatus
    total_amount_paise: int
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    lines: list[OrderLineResponse] = []
    status_history: list[OrderStatusHistoryResponse] = []
    estimated_tax: Optional[TaxSummaryResponse] = None
    stock_availability: list[StockAvailabilityLine] = []


class SalesmanCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    customer_type: CustomerType
    gstin: Optional[str] = None
    state_code: str
    address: str
    phone: str


class SalesmanProductResponse(BaseModel):
    product_id: int
    name: str
    pack_size_desc: str
    packets_per_carton: int
    price_paise: int
    price_source: PriceSource


class CustomerSalesSummaryResponse(BaseModel):
    customer_id: int
    customer_name: str
    order_count: int
    total_value_paise: int
