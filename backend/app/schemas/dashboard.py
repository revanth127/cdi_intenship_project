from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TodaySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    orders_received_count: int = 0
    orders_received_value_paise: int = 0
    orders_pending_approval_count: int = 0
    invoices_raised_count: int = 0
    invoices_raised_value_paise: int = 0
    dispatches_made_count: int = 0
    payments_collected_paise: int = 0
    payments_collected_count: int = 0


class FinishedGoodStock(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    item_id: int
    pack_size_desc: str
    on_hand_packets: int
    committed_packets: int
    available_to_promise_packets: int


class ReorderAlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    item_name: str
    item_type: str
    base_unit: str
    display_unit: str
    current_stock_base: int
    reorder_level_base: Optional[int] = None
    deficit_base: Optional[int] = None


class StockSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finished_goods: list[FinishedGoodStock] = []
    reorder_alerts: list[ReorderAlertItem] = []


class VarianceAlertSummaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    run_no: str
    run_date: datetime
    product_name: str
    item_id: int
    item_name: str
    planned_qty_base: int
    actual_qty_base: int
    difference_qty_base: int
    variance_pct: Decimal
    display_unit: str
    tolerance_pct: Decimal


class TopDebtorCustomer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str
    total_outstanding_paise: int
    oldest_invoice_date: Optional[datetime] = None


class ReceivablesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_outstanding_paise: int
    bucket_0_30_paise: int
    bucket_31_60_paise: int
    bucket_61_90_paise: int
    bucket_90_plus_paise: int
    unallocated_advance_paise: int
    top_debtors: list[TopDebtorCustomer] = []


class CostingMarginSummaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    cost_per_packet: Decimal
    selling_price: Decimal
    margin_per_packet: Decimal
    margin_pct: Decimal


class DailySalesTrendItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    taxable_sales_paise: int
    taxable_sales_rupees: Decimal
    invoice_count: int


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: datetime
    today: TodaySummary
    stock: StockSummary
    variance_alerts: list[VarianceAlertSummaryItem] = []
    receivables: ReceivablesSummary
    costing: list[CostingMarginSummaryItem] = []
    sales_trend: list[DailySalesTrendItem] = []
