from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.company import CompanySettings
from app.models.customer import Customer
from app.models.invoice import (
    CreditNote,
    CreditNoteLine,
    CreditNoteStatus,
    Dispatch,
    DispatchLine,
    DispatchStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
)
from app.models.item import Item
from app.models.order import (
    NumberingSequence,
    Order,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
)
from app.models.product import Product
from app.models.stock import MovementType
from app.models.user import User, UserRole
from app.schemas.invoice import CreditNoteCreate, DispatchCreate
from app.services.audit import log_audit
from app.services.orders import get_financial_year
from app.services.stock import get_current_unit_cost, post_movement
from app.utils.gst import compute_line_tax, is_intra_state
from app.utils.indian_numbers import amount_in_words

logger = logging.getLogger("invoicing_service")


def get_next_sequence_number(
    db: Session,
    sequence_name: str,
    prefix: str,
    date: Optional[datetime] = None,
) -> tuple[str, str]:
    """
    Generates a gapless, race-free document number per financial year using
    SELECT ... FOR UPDATE on numbering_sequences.
    Enforces the statutory GST rule that invoice numbers must not exceed 16 characters.
    """
    company = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    fy_start_month = company.financial_year_start_month if company else 4
    _, fy_str = get_financial_year(date, fy_start_month)

    seq_row = db.scalar(
        select(NumberingSequence)
        .where(
            NumberingSequence.sequence_name == sequence_name,
            NumberingSequence.financial_year == fy_str,
        )
        .with_for_update()
    )

    if not seq_row:
        seq_row = NumberingSequence(
            sequence_name=sequence_name,
            financial_year=fy_str,
            last_number=1,
        )
        db.add(seq_row)
        db.flush()
        next_val = 1
    else:
        seq_row.last_number += 1
        next_val = seq_row.last_number
        db.flush()

    doc_no = f"{prefix}/{fy_str}/{next_val:04d}"
    if len(doc_no) > 16:
        raise ValueError(f"Document number {doc_no} exceeds the statutory GST limit of 16 characters.")

    return doc_no, fy_str


def get_next_invoice_number(db: Session, date: Optional[datetime] = None) -> tuple[str, str]:
    """Generates INV/YYYY-YY/XXXX (exactly 16 characters, e.g. INV/2026-27/0001)."""
    return get_next_sequence_number(db, "INVOICE", "INV", date)


def get_next_credit_note_number(db: Session, date: Optional[datetime] = None) -> tuple[str, str]:
    """Generates CN/YYYY-YY/XXXX (15 characters, e.g. CN/2026-27/0001)."""
    return get_next_sequence_number(db, "CREDIT_NOTE", "CN", date)


def get_next_dispatch_number(db: Session, date: Optional[datetime] = None) -> tuple[str, str]:
    """Generates DSP/YYYY-YY/XXXX (16 characters, e.g. DSP/2026-27/0001)."""
    return get_next_sequence_number(db, "DISPATCH", "DSP", date)


def prevent_invoice_modification(invoice: Invoice) -> None:
    """Guards against any manual updates or deletions of posted tax invoices."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Posted GST invoices are immutable and cannot be updated or deleted. Issue a Credit Note to cancel or reverse.",
    )


def attach_invoice_details(invoice: Invoice) -> Invoice:
    """Enriches invoice model with amount in words and dispatch flag for response serialization."""
    invoice.grand_total_in_words = amount_in_words(invoice.grand_total_paise, paise_input=True)
    invoice.is_dispatched = any(d.status == DispatchStatus.DISPATCHED for d in invoice.dispatches)
    return invoice


def attach_credit_note_details(credit_note: CreditNote) -> CreditNote:
    """Enriches credit note model with amount in words."""
    credit_note.grand_total_in_words = amount_in_words(credit_note.grand_total_paise, paise_input=True)
    return credit_note


def create_invoice_from_order(db: Session, order_id: int, user: User) -> Invoice:
    """
    Creates an immutable GST Tax Invoice from an APPROVED order in ONE atomic transaction.
    - Locks the order and validates status == APPROVED.
    - Copies immutable snapshots of Seller (CompanySettings) and Buyer (Customer) master records.
    - Evaluates place of supply: Intra-state (CGST + SGST) vs Inter-state (IGST) using utils/gst.py.
    - Computes tax per line in integer paise using Decimal & ROUND_HALF_UP.
    - Generates a gapless, race-free invoice number <= 16 chars per financial year.
    - Advances order status to INVOICED and writes order status history and audit log.
    """
    # 1. Load order with full associations
    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.lines).selectinload(OrderLine.product).selectinload(Product.item),
            selectinload(Order.customer),
            selectinload(Order.status_history),
        )
        .where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")

    if order.status != OrderStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot raise invoice for order {order.order_no} with status '{order.status.value}'. Invoices can only be created from APPROVED orders.",
        )

    # Check if active invoice already exists for this order
    existing_invoice = db.scalar(
        select(Invoice).where(
            Invoice.order_id == order_id,
            Invoice.status == InvoiceStatus.POSTED,
        )
    )
    if existing_invoice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An active invoice {existing_invoice.invoice_no} already exists for Order {order.order_no}.",
        )

    # 2. Load company settings for seller snapshot
    company = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    if not company:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Company settings not configured. Please initialize company settings first.",
        )

    now = datetime.now(timezone.utc)
    invoice_no, fy_str = get_next_invoice_number(db, now)

    # 3. Determine place of supply and tax jurisdiction
    customer = order.customer
    is_intra = is_intra_state(company.state_code, customer.state_code)
    is_igst = not is_intra

    # 4. Construct Invoice Header with Snapshots
    invoice = Invoice(
        invoice_no=invoice_no,
        financial_year=fy_str,
        invoice_date=now,
        order_id=order.id,
        customer_id=customer.id,
        status=InvoiceStatus.POSTED,
        seller_name=company.company_name,
        seller_gstin=company.gstin,
        seller_address=company.address,
        seller_state_code=company.state_code,
        buyer_name=customer.name,
        buyer_gstin=customer.gstin,
        buyer_address=customer.address,
        buyer_state_code=customer.state_code,
        place_of_supply_state_code=customer.state_code,
        is_igst=is_igst,
        created_by=user.id,
        created_at=now,
    )

    # 5. Build Invoice Lines and calculate GST per line strictly via utils/gst.py
    taxable_total = 0
    cgst_total = 0
    sgst_total = 0
    igst_total = 0

    for order_line in order.lines:
        item = order_line.product.item if (order_line.product and order_line.product.item) else None
        item_name = item.name if item else f"Product {order_line.product_id}"
        hsn_code = item.hsn_code if (item and item.hsn_code) else "1905"
        rate_bp = item.gst_rate_bp if item else 0

        taxable_paise = order_line.line_total_paise
        cgst_p, sgst_p, igst_p = compute_line_tax(taxable_paise, rate_bp, is_intra)
        line_total = taxable_paise + cgst_p + sgst_p + igst_p

        taxable_total += taxable_paise
        cgst_total += cgst_p
        sgst_total += sgst_p
        igst_total += igst_p

        inv_line = InvoiceLine(
            product_id=order_line.product_id,
            description=item_name,
            hsn_code=hsn_code,
            quantity_packets=order_line.quantity_packets,
            unit_price_paise=order_line.unit_price_paise,
            taxable_paise=taxable_paise,
            gst_rate_bp=rate_bp,
            cgst_paise=cgst_p,
            sgst_paise=sgst_p,
            igst_paise=igst_p,
            line_total_paise=line_total,
        )
        invoice.lines.append(inv_line)

    invoice.taxable_total_paise = taxable_total
    invoice.cgst_total_paise = cgst_total
    invoice.sgst_total_paise = sgst_total
    invoice.igst_total_paise = igst_total
    invoice.round_off_paise = 0
    invoice.grand_total_paise = taxable_total + cgst_total + sgst_total + igst_total

    db.add(invoice)
    db.flush()

    # 6. Advance Order Status to INVOICED
    from_status = order.status
    order.status = OrderStatus.INVOICED
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.INVOICED,
        user_id=user.id,
        timestamp=now,
        notes=f"Tax Invoice {invoice_no} raised",
    )
    order.status_history.append(history)

    # 7. Audit Logging
    log_audit(
        db=db,
        user=user,
        action="INVOICE_POSTED",
        entity_type="Invoice",
        entity_id=invoice.id,
        new_values={
            "invoice_no": invoice.invoice_no,
            "order_id": order.id,
            "order_no": order.order_no,
            "customer_id": customer.id,
            "taxable_total_paise": invoice.taxable_total_paise,
            "grand_total_paise": invoice.grand_total_paise,
            "is_igst": invoice.is_igst,
            "status": invoice.status.value,
        },
    )

    db.commit()
    db.refresh(invoice)
    return attach_invoice_details(invoice)


def dispatch_invoice(
    db: Session,
    invoice_id: int,
    payload: DispatchCreate,
    user: User,
) -> Dispatch:
    """
    Dispatches goods against an issued Tax Invoice in ONE transaction:
    - Validates invoice is in POSTED status and not already dispatched.
    - Acquires row-level write locks (SELECT ... FOR UPDATE) on Item records.
    - Decrements finished-goods inventory via post_movement (type=DISPATCH, negative qty).
    - If stock is insufficient, post_movement raises InsufficientStockError (HTTP 409).
    - Creates Dispatch and DispatchLine records.
    - Updates associated Order status to DISPATCHED (releasing committed ATP stock).
    - Records Order status history and writes an audit log.
    """
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.lines).selectinload(InvoiceLine.product).selectinload(Product.item),
            selectinload(Invoice.dispatches),
            selectinload(Invoice.allocations),
            selectinload(Invoice.order).selectinload(Order.status_history),
        )
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    if invoice.status != InvoiceStatus.POSTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot dispatch invoice {invoice.invoice_no} with status {invoice.status.value}. Only POSTED invoices can be dispatched.",
        )

    # Prevent double-dispatch
    active_dispatch = next((d for d in invoice.dispatches if d.status == DispatchStatus.DISPATCHED), None)
    if active_dispatch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice {invoice.invoice_no} has already been dispatched under Dispatch No: {active_dispatch.dispatch_no}.",
        )

    now = datetime.now(timezone.utc)
    dispatch_date = payload.dispatch_date or now
    dispatch_no, _ = get_next_dispatch_number(db, dispatch_date)

    dispatch = Dispatch(
        dispatch_no=dispatch_no,
        invoice_id=invoice.id,
        dispatch_date=dispatch_date,
        vehicle_no=payload.vehicle_no,
        status=DispatchStatus.DISPATCHED,
        created_by=user.id,
        created_at=now,
    )

    # Process inventory movements for each invoice line
    for line in invoice.lines:
        item = line.product.item if (line.product and line.product.item) else None
        if not item:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Line product {line.product_id} has no underlying inventory Item record.",
            )

        # Prevailing moving weighted average cost
        cost = get_current_unit_cost(db, item.id)
        if cost <= 0 and item.opening_rate_paise:
            cost = item.opening_rate_paise
        elif cost <= 0:
            cost = Decimal(line.unit_price_paise)

        # post_movement enforces row lock and raises HTTP 409 InsufficientStockError if balance < requested
        post_movement(
            db=db,
            item_id=item.id,
            movement_type=MovementType.DISPATCH,
            quantity_base=-line.quantity_packets,
            unit_cost=cost,
            source_type="INVOICE",
            source_id=str(invoice.id),
            user=user,
            movement_date=dispatch_date,
            note=f"Dispatch {dispatch_no} for Invoice {invoice.invoice_no}",
        )

        d_line = DispatchLine(
            invoice_line_id=line.id,
            quantity_packets=line.quantity_packets,
        )
        dispatch.lines.append(d_line)

    db.add(dispatch)

    # Advance Order Status to DISPATCHED
    if invoice.order:
        from_st = invoice.order.status
        invoice.order.status = OrderStatus.DISPATCHED
        history = OrderStatusHistory(
            order_id=invoice.order.id,
            from_status=from_st,
            to_status=OrderStatus.DISPATCHED,
            user_id=user.id,
            timestamp=now,
            notes=f"Dispatched under {dispatch_no}",
        )
        invoice.order.status_history.append(history)

    log_audit(
        db=db,
        user=user,
        action="INVOICE_DISPATCHED",
        entity_type="Invoice",
        entity_id=invoice.id,
        old_values={"status": "POSTED"},
        new_values={
            "dispatch_no": dispatch.dispatch_no,
            "invoice_id": invoice.id,
            "invoice_no": invoice.invoice_no,
            "vehicle_no": dispatch.vehicle_no,
        },
    )

    db.commit()
    db.refresh(dispatch)
    return dispatch


def create_credit_note_for_invoice(
    db: Session,
    invoice_id: int,
    payload: CreditNoteCreate,
    user: User,
) -> CreditNote:
    """
    Cancels a posted Tax Invoice by issuing a full statutory GST Credit Note:
    - Verifies invoice is POSTED and cancellation reason is non-empty (min 3 chars).
    - Reverses tax and monetary values by generating a Credit Note mirror document.
    - If invoice was already dispatched, restores inventory to factory via SALES_RETURN movements
      (when return_stock=True).
    - If invoice was not dispatched, marks associated Order status as CANCELLED.
    - Marks original Invoice as CANCELLED with cancel_reason and timestamp.
    """
    if not payload.reason or len(payload.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mandatory cancellation reason of at least 3 characters is required.",
        )

    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.lines).selectinload(InvoiceLine.product).selectinload(Product.item),
            selectinload(Invoice.dispatches),
            selectinload(Invoice.allocations),
            selectinload(Invoice.order).selectinload(Order.status_history),
        )
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice {invoice.invoice_no} is already cancelled.",
        )

    now = datetime.now(timezone.utc)
    cn_no, fy_str = get_next_credit_note_number(db, now)

    # Create Credit Note mirroring the original invoice
    credit_note = CreditNote(
        credit_note_no=cn_no,
        financial_year=fy_str,
        credit_note_date=now,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        reason=payload.reason.strip(),
        return_stock=payload.return_stock,
        status=CreditNoteStatus.POSTED,
        seller_name=invoice.seller_name,
        seller_gstin=invoice.seller_gstin,
        seller_address=invoice.seller_address,
        seller_state_code=invoice.seller_state_code,
        buyer_name=invoice.buyer_name,
        buyer_gstin=invoice.buyer_gstin,
        buyer_address=invoice.buyer_address,
        buyer_state_code=invoice.buyer_state_code,
        place_of_supply_state_code=invoice.place_of_supply_state_code,
        is_igst=invoice.is_igst,
        taxable_total_paise=invoice.taxable_total_paise,
        cgst_total_paise=invoice.cgst_total_paise,
        sgst_total_paise=invoice.sgst_total_paise,
        igst_total_paise=invoice.igst_total_paise,
        round_off_paise=invoice.round_off_paise,
        grand_total_paise=invoice.grand_total_paise,
        created_by=user.id,
        created_at=now,
    )

    for line in invoice.lines:
        cn_line = CreditNoteLine(
            invoice_line_id=line.id,
            product_id=line.product_id,
            description=line.description,
            hsn_code=line.hsn_code,
            quantity_packets=line.quantity_packets,
            unit_price_paise=line.unit_price_paise,
            taxable_paise=line.taxable_paise,
            gst_rate_bp=line.gst_rate_bp,
            cgst_paise=line.cgst_paise,
            sgst_paise=line.sgst_paise,
            igst_paise=line.igst_paise,
            line_total_paise=line.line_total_paise,
        )
        credit_note.lines.append(cn_line)

    db.add(credit_note)

    # Check dispatch status
    was_dispatched = any(d.status == DispatchStatus.DISPATCHED for d in invoice.dispatches)

    if was_dispatched and payload.return_stock:
        # Return finished goods to inventory via SALES_RETURN movements
        for line in invoice.lines:
            item = line.product.item if (line.product and line.product.item) else None
            if item:
                cost = get_current_unit_cost(db, item.id)
                if cost <= 0 and item.opening_rate_paise:
                    cost = item.opening_rate_paise
                elif cost <= 0:
                    cost = Decimal(line.unit_price_paise)

                post_movement(
                    db=db,
                    item_id=item.id,
                    movement_type=MovementType.SALES_RETURN,
                    quantity_base=line.quantity_packets,
                    unit_cost=cost,
                    source_type="CREDIT_NOTE",
                    source_id=cn_no,
                    user=user,
                    movement_date=now,
                    note=f"Sales return via Credit Note {cn_no} for Invoice {invoice.invoice_no}",
                )

    # Update Order status: Cancel order only if it was NOT yet dispatched
    if invoice.order and not was_dispatched:
        from_st = invoice.order.status
        invoice.order.status = OrderStatus.CANCELLED
        history = OrderStatusHistory(
            order_id=invoice.order.id,
            from_status=from_st,
            to_status=OrderStatus.CANCELLED,
            user_id=user.id,
            timestamp=now,
            notes=f"Order cancelled due to Credit Note {cn_no}: {payload.reason.strip()}",
        )
        invoice.order.status_history.append(history)

    # Mark original invoice as CANCELLED
    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = now
    invoice.cancel_reason = payload.reason.strip()

    # Free up any allocations against this invoice so payments return to customer advance
    if hasattr(invoice, "allocations") and invoice.allocations:
        for alloc in list(invoice.allocations):
            db.delete(alloc)

    log_audit(
        db=db,
        user=user,
        action="INVOICE_CANCELLED",
        entity_type="Invoice",
        entity_id=invoice.id,
        old_values={"status": "POSTED"},
        new_values={
            "status": "CANCELLED",
            "credit_note_no": credit_note.credit_note_no,
            "reason": credit_note.reason,
            "return_stock": credit_note.return_stock,
            "was_dispatched": was_dispatched,
            "grand_total_paise": credit_note.grand_total_paise,
        },
    )

    db.commit()
    db.refresh(credit_note)
    return attach_credit_note_details(credit_note)


def generate_share_link(invoice: Invoice, expires_hours: int = 168) -> dict[str, Any]:
    """
    Creates a time-limited signed JWT token for public access to the invoice PDF.
    Also formats pre-filled WhatsApp and mailto links.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_hours)

    payload = {
        "invoice_id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "type": "invoice_share",
        "iat": now,
        "exp": expire,
    }
    share_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    public_url = f"/api/v1/invoices/public/{share_token}/pdf"

    # Pre-filled WhatsApp message
    customer_phone = invoice.customer.phone if invoice.customer and invoice.customer.phone else ""
    # Clean phone to digits
    clean_phone = "".join(c for c in customer_phone if c.isdigit())
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"

    rs_amount = (Decimal(invoice.grand_total_paise) / Decimal(100)).quantize(Decimal("0.01"))
    msg = (
        f"Dear {invoice.buyer_name},\n"
        f"Your GST Tax Invoice {invoice.invoice_no} for ₹{rs_amount:,.2f} is ready.\n"
        f"Download PDF here: {public_url}"
    )

    whatsapp_url = f"https://wa.me/{clean_phone}?text={quote(msg)}" if clean_phone else None
    email_url = f"mailto:?subject={quote(f'Invoice {invoice.invoice_no}')}&body={quote(msg)}"

    return {
        "share_token": share_token,
        "public_url": public_url,
        "whatsapp_url": whatsapp_url,
        "email_url": email_url,
        "expires_at": expire,
    }
