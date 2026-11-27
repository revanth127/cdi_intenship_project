from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class InvoiceOutstandingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    invoice_no: str
    invoice_date: datetime
    customer_id: int
    customer_name: str
    grand_total_paise: int
    credit_notes_total_paise: int
    paid_allocations_paise: int
    outstanding_paise: int
    age_days: int
    status: str


class CustomerOutstandingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str
    total_invoiced_paise: int
    total_credit_notes_paise: int
    total_payments_paise: int
    open_invoices_outstanding_paise: int
    unallocated_advance_paise: int
    total_outstanding_paise: int  # Can be negative indicating advance credit balance
    invoices: list[InvoiceOutstandingResponse] = []


class AgeingCustomerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str
    assigned_salesman_id: Optional[int] = None
    assigned_salesman_name: Optional[str] = None
    bucket_0_30_paise: int = 0
    bucket_31_60_paise: int = 0
    bucket_61_90_paise: int = 0
    bucket_90_plus_paise: int = 0
    gross_outstanding_paise: int = 0
    unallocated_advance_paise: int = 0
    total_outstanding_paise: int = 0
    oldest_invoice_date: Optional[datetime] = None


class ReceivablesAgeingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: datetime
    total_bucket_0_30_paise: int
    total_bucket_31_60_paise: int
    total_bucket_61_90_paise: int
    total_bucket_90_plus_paise: int
    total_unallocated_advance_paise: int
    grand_total_outstanding_paise: int
    customers: list[AgeingCustomerRow] = []


class StatementTransaction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime
    type: str  # "INVOICE", "CREDIT_NOTE", "PAYMENT"
    reference_no: str
    description: str
    debit_paise: int = 0
    credit_paise: int = 0
    running_balance_paise: int = 0


class CustomerStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str
    from_date: datetime
    to_date: datetime
    opening_balance_paise: int
    total_debits_paise: int
    total_credits_paise: int
    closing_balance_paise: int
    transactions: list[StatementTransaction] = []


class DailyCollectionItem(BaseModel):
    date: str
    cash_paise: int = 0
    upi_paise: int = 0
    bank_paise: int = 0
    cheque_paise: int = 0
    total_paise: int = 0
    count: int = 0


class CollectionsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_date: datetime
    to_date: datetime
    total_cash_paise: int
    total_upi_paise: int
    total_bank_paise: int
    total_cheque_paise: int
    grand_total_collected_paise: int
    payment_count: int
    daily_breakdown: list[DailyCollectionItem] = []
