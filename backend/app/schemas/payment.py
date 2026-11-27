from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentMode, PaymentStatus


class PaymentAllocationCreate(BaseModel):
    invoice_id: int = Field(..., description="ID of the invoice to allocate payment against")
    amount_paise: int = Field(..., gt=0, description="Amount in paise to allocate")


class PaymentAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_id: int
    invoice_id: int
    invoice_no: Optional[str] = None
    amount_paise: int


class PaymentCreate(BaseModel):
    customer_id: int = Field(..., description="ID of the customer making the payment")
    amount_paise: int = Field(..., gt=0, description="Total payment amount in integer paise")
    mode: PaymentMode = Field(..., description="Payment mode: CASH, UPI, BANK, CHEQUE")
    payment_date: Optional[datetime] = Field(None, description="Payment timestamp (defaults to current UTC)")
    reference_no: Optional[str] = Field(None, max_length=64, description="Cheque / UTR / Transaction reference")
    notes: Optional[str] = Field(None, description="Optional payment notes")
    allocations: Optional[list[PaymentAllocationCreate]] = Field(
        None, description="Specific invoice allocations. If omitted, FIFO auto-allocation is applied."
    )


class PaymentReverse(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory explanation for reversing payment")


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_no: str
    customer_id: int
    customer_name: Optional[str] = None
    payment_date: datetime
    amount_paise: int
    allocated_paise: int = 0
    unallocated_advance_paise: int = 0
    mode: PaymentMode
    reference_no: Optional[str] = None
    status: PaymentStatus
    reversed_at: Optional[datetime] = None
    reverse_reason: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    allocations: list[PaymentAllocationResponse] = []
