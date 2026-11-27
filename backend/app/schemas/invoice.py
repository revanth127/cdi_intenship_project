from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.invoice import CreditNoteStatus, DispatchStatus, InvoiceStatus


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    description: str
    hsn_code: str
    quantity_packets: int
    unit_price_paise: int
    taxable_paise: int
    gst_rate_bp: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    line_total_paise: int


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_no: str
    financial_year: str
    invoice_date: datetime
    order_id: Optional[int] = None
    customer_id: int
    status: InvoiceStatus

    # Seller Snapshot
    seller_name: str
    seller_gstin: str
    seller_address: str
    seller_state_code: str

    # Buyer Snapshot
    buyer_name: str
    buyer_gstin: Optional[str] = None
    buyer_address: str
    buyer_state_code: str

    place_of_supply_state_code: str
    is_igst: bool

    taxable_total_paise: int
    cgst_total_paise: int
    sgst_total_paise: int
    igst_total_paise: int
    round_off_paise: int
    grand_total_paise: int
    grand_total_in_words: Optional[str] = None

    created_by: Optional[int] = None
    created_at: datetime
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None

    lines: list[InvoiceLineResponse] = []
    is_dispatched: bool = False


class DispatchCreate(BaseModel):
    vehicle_no: Optional[str] = Field(None, max_length=64, description="Vehicle number for shipping")
    dispatch_date: Optional[datetime] = None


class DispatchLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_line_id: int
    quantity_packets: int


class DispatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispatch_no: str
    invoice_id: int
    dispatch_date: datetime
    vehicle_no: Optional[str] = None
    status: DispatchStatus
    created_by: Optional[int] = None
    created_at: datetime
    lines: list[DispatchLineResponse] = []


class CreditNoteCreate(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory reason for issuing credit note / cancellation")
    return_stock: bool = Field(True, description="Whether to post SALES_RETURN stock movements if dispatched")


class CreditNoteLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_line_id: Optional[int] = None
    product_id: int
    description: str
    hsn_code: str
    quantity_packets: int
    unit_price_paise: int
    taxable_paise: int
    gst_rate_bp: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    line_total_paise: int


class CreditNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    credit_note_no: str
    financial_year: str
    credit_note_date: datetime
    invoice_id: int
    customer_id: int
    reason: str
    return_stock: bool
    status: CreditNoteStatus

    seller_name: str
    seller_gstin: str
    seller_address: str
    seller_state_code: str

    buyer_name: str
    buyer_gstin: Optional[str] = None
    buyer_address: str
    buyer_state_code: str

    place_of_supply_state_code: str
    is_igst: bool

    taxable_total_paise: int
    cgst_total_paise: int
    sgst_total_paise: int
    igst_total_paise: int
    round_off_paise: int
    grand_total_paise: int
    grand_total_in_words: Optional[str] = None

    created_by: Optional[int] = None
    created_at: datetime
    lines: list[CreditNoteLineResponse] = []


class ShareLinkResponse(BaseModel):
    share_token: str
    public_url: str
    whatsapp_url: Optional[str] = None
    email_url: Optional[str] = None
    expires_at: datetime
