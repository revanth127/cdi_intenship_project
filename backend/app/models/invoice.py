from datetime import datetime, timezone
import enum
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class InvoiceStatus(str, enum.Enum):
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class DispatchStatus(str, enum.Enum):
    DISPATCHED = "DISPATCHED"
    REVERSED = "REVERSED"


class CreditNoteStatus(str, enum.Enum):
    POSTED = "POSTED"


class Invoice(Base):
    """
    Immutable GST Tax Invoice created from an APPROVED sales order.
    Contains complete seller and buyer master data snapshots to ensure
    historic accuracy regardless of subsequent edits.
    """
    __tablename__ = "invoices"

    __table_args__ = (
        CheckConstraint("taxable_total_paise >= 0", name="ck_invoices_taxable_non_negative"),
        CheckConstraint("grand_total_paise >= 0", name="ck_invoices_grand_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    financial_year: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # e.g. "2026-27"
    invoice_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", native_enum=False),
        nullable=False,
        default=InvoiceStatus.POSTED,
        index=True,
    )

    # Seller snapshot fields
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    seller_address: Mapped[str] = mapped_column(Text, nullable=False)
    seller_state_code: Mapped[str] = mapped_column(String(4), nullable=False)

    # Buyer snapshot fields
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    buyer_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_state_code: Mapped[str] = mapped_column(String(4), nullable=False)

    place_of_supply_state_code: Mapped[str] = mapped_column(String(4), nullable=False)
    is_igst: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    taxable_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cgst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    round_off_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    grand_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    order: Mapped[Optional["Order"]] = relationship("Order")
    customer: Mapped["Customer"] = relationship("Customer")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    lines: Mapped[list["InvoiceLine"]] = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id"
    )
    dispatches: Mapped[list["Dispatch"]] = relationship(
        "Dispatch", back_populates="invoice", cascade="all, delete-orphan", order_by="Dispatch.id"
    )
    credit_notes: Mapped[list["CreditNote"]] = relationship(
        "CreditNote", back_populates="invoice", order_by="CreditNote.id"
    )
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation", back_populates="invoice", order_by="PaymentAllocation.id"
    )


class InvoiceLine(Base):
    """
    Individual line item on a GST Tax Invoice.
    Stores snapshot of HSN, quantities, and line-level tax computations.
    """
    __tablename__ = "invoice_lines"

    __table_args__ = (
        CheckConstraint("quantity_packets > 0", name="ck_invoice_lines_quantity_positive"),
        CheckConstraint("unit_price_paise >= 0", name="ck_invoice_lines_unit_price_non_negative"),
        CheckConstraint("taxable_paise >= 0", name="ck_invoice_lines_taxable_non_negative"),
        CheckConstraint("line_total_paise >= 0", name="ck_invoice_lines_line_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    taxable_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    line_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
    product: Mapped["Product"] = relationship("Product")


class Dispatch(Base):
    """
    Physical dispatch record against an issued invoice.
    Tracks vehicle number and ledger stock movement reference.
    """
    __tablename__ = "dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispatch_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dispatch_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    vehicle_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[DispatchStatus] = mapped_column(
        Enum(DispatchStatus, name="dispatch_status_enum", native_enum=False),
        nullable=False,
        default=DispatchStatus.DISPATCHED,
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="dispatches")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    lines: Mapped[list["DispatchLine"]] = relationship(
        "DispatchLine", back_populates="dispatch", cascade="all, delete-orphan", order_by="DispatchLine.id"
    )


class DispatchLine(Base):
    """
    Line-level quantities dispatched against invoice lines.
    """
    __tablename__ = "dispatch_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispatch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dispatches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoice_lines.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_packets: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    dispatch: Mapped["Dispatch"] = relationship("Dispatch", back_populates="lines")
    invoice_line: Mapped["InvoiceLine"] = relationship("InvoiceLine")


class CreditNote(Base):
    """
    GST Credit Note reversing a posted Tax Invoice.
    Mirrors invoice financial snapshot with its own sequential document number.
    Optionally returns stock to factory inventory via SALES_RETURN movements.
    """
    __tablename__ = "credit_notes"

    __table_args__ = (
        CheckConstraint("taxable_total_paise >= 0", name="ck_credit_notes_taxable_non_negative"),
        CheckConstraint("grand_total_paise >= 0", name="ck_credit_notes_grand_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    credit_note_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    financial_year: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    credit_note_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    return_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[CreditNoteStatus] = mapped_column(
        Enum(CreditNoteStatus, name="credit_note_status_enum", native_enum=False),
        nullable=False,
        default=CreditNoteStatus.POSTED,
    )

    # Seller snapshot fields
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    seller_address: Mapped[str] = mapped_column(Text, nullable=False)
    seller_state_code: Mapped[str] = mapped_column(String(4), nullable=False)

    # Buyer snapshot fields
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    buyer_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_state_code: Mapped[str] = mapped_column(String(4), nullable=False)

    place_of_supply_state_code: Mapped[str] = mapped_column(String(4), nullable=False)
    is_igst: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    taxable_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cgst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    round_off_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    grand_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="credit_notes")
    customer: Mapped["Customer"] = relationship("Customer")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    lines: Mapped[list["CreditNoteLine"]] = relationship(
        "CreditNoteLine", back_populates="credit_note", cascade="all, delete-orphan", order_by="CreditNoteLine.id"
    )


class CreditNoteLine(Base):
    """
    Line-level breakdown for GST Credit Note mirroring invoice line.
    """
    __tablename__ = "credit_note_lines"

    __table_args__ = (
        CheckConstraint("quantity_packets > 0", name="ck_credit_note_lines_quantity_positive"),
        CheckConstraint("unit_price_paise >= 0", name="ck_credit_note_lines_unit_price_non_negative"),
        CheckConstraint("taxable_paise >= 0", name="ck_credit_note_lines_taxable_non_negative"),
        CheckConstraint("line_total_paise >= 0", name="ck_credit_note_lines_line_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    credit_note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_line_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("invoice_lines.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    taxable_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    line_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    credit_note: Mapped["CreditNote"] = relationship("CreditNote", back_populates="lines")
    product: Mapped["Product"] = relationship("Product")
    invoice_line: Mapped[Optional["InvoiceLine"]] = relationship("InvoiceLine")
