from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from jose import JWTError, jwt
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.invoice import CreditNote, Dispatch, Invoice, InvoiceLine, InvoiceStatus
from app.models.order import Order
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.services.audit import log_audit
from app.schemas.audit import DocumentHistoryItem
from app.schemas.invoice import (
    CreditNoteCreate,
    CreditNoteResponse,
    DispatchCreate,
    DispatchResponse,
    InvoiceResponse,
    ShareLinkResponse,
)
from app.services import invoicing as invoicing_service
from app.services.pdf import generate_invoice_pdf

router = APIRouter(prefix="/invoices", tags=["Invoicing & Dispatches"])

ALLOW_READ = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT)
ALLOW_ADMIN = require_roles(UserRole.ADMIN)
ALLOW_AUTH = require_roles(UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN)


@router.get("", response_model=list[InvoiceResponse], dependencies=[Depends(ALLOW_READ)])
def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    customer_id: Optional[int] = Query(None),
    financial_year: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Lists GST Tax Invoices with optional status, customer, and date range filters.
    Available to ADMIN, OWNER, and ACCOUNTANT roles.
    """
    stmt = (
        select(Invoice)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.dispatches),
        )
        .order_by(desc(Invoice.invoice_date))
    )
    if status_filter:
        stmt = stmt.where(Invoice.status == status_filter)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if financial_year:
        stmt = stmt.where(Invoice.financial_year == financial_year)
    if from_date:
        stmt = stmt.where(Invoice.invoice_date >= from_date)
    if to_date:
        stmt = stmt.where(Invoice.invoice_date <= to_date)

    stmt = stmt.offset(skip).limit(limit)
    invoices = db.scalars(stmt).all()
    return [invoicing_service.attach_invoice_details(inv) for inv in invoices]


@router.get("/public/{share_token}/pdf")
def get_public_invoice_pdf(share_token: str, db: Session = Depends(get_db)):
    """
    Public, unauthenticated route for customers to download their GST Tax Invoice PDF
    via time-limited signed token received via WhatsApp or Email.
    """
    try:
        payload = jwt.decode(share_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "invoice_share":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
        invoice_id = payload.get("invoice_id")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired share link.")

    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.lines))
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    pdf_bytes = generate_invoice_pdf(invoice)
    log_audit(
        db=db,
        user=None,
        action="REPORT_EXPORTED",
        entity_type="Invoice",
        entity_id=str(invoice.id),
        new_values={"format": "PDF", "invoice_no": invoice.invoice_no, "public": True},
    )
    db.commit()
    safe_no = invoice.invoice_no.replace("/", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_no}.pdf"'},
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse, dependencies=[Depends(ALLOW_AUTH)])
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves full details of a specific GST Tax Invoice.
    Salesmen may only access invoices relating to their own assigned orders/customers.
    """
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.dispatches),
            selectinload(Invoice.order),
            selectinload(Invoice.customer),
        )
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    # Salesman isolation check
    if current_user.role == UserRole.SALESMAN:
        is_own_order = invoice.order and invoice.order.salesman_id == current_user.id
        is_own_customer = invoice.customer and invoice.customer.assigned_salesman_id == current_user.id
        if not (is_own_order or is_own_customer):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    return invoicing_service.attach_invoice_details(invoice)


@router.get("/{invoice_id}/pdf", dependencies=[Depends(ALLOW_AUTH)])
def get_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates and downloads the official GST Tax Invoice PDF.
    """
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.order),
            selectinload(Invoice.customer),
        )
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    if current_user.role == UserRole.SALESMAN:
        is_own_order = invoice.order and invoice.order.salesman_id == current_user.id
        is_own_customer = invoice.customer and invoice.customer.assigned_salesman_id == current_user.id
        if not (is_own_order or is_own_customer):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    pdf_bytes = generate_invoice_pdf(invoice)
    log_audit(
        db=db,
        user=current_user,
        action="REPORT_EXPORTED",
        entity_type="Invoice",
        entity_id=str(invoice.id),
        new_values={"format": "PDF", "invoice_no": invoice.invoice_no},
    )
    db.commit()
    safe_no = invoice.invoice_no.replace("/", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_no}.pdf"'},
    )


@router.get("/{invoice_id}/share-link", response_model=ShareLinkResponse, dependencies=[Depends(ALLOW_AUTH)])
def get_invoice_share_link(
    invoice_id: int,
    expires_hours: int = Query(168, ge=1, le=720, description="Link validity in hours (default 7 days)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates a signed time-limited public link for the invoice PDF,
    together with ready-to-send WhatsApp and email sharing URLs.
    """
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.order),
        )
        .where(Invoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    if current_user.role == UserRole.SALESMAN:
        is_own_order = invoice.order and invoice.order.salesman_id == current_user.id
        is_own_customer = invoice.customer and invoice.customer.assigned_salesman_id == current_user.id
        if not (is_own_order or is_own_customer):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    res = invoicing_service.generate_share_link(invoice, expires_hours=expires_hours)
    log_audit(
        db=db,
        user=current_user,
        action="INVOICE_SHARED",
        entity_type="Invoice",
        entity_id=str(invoice.id),
        new_values={"expires_hours": expires_hours, "share_url": res.get("share_url") if isinstance(res, dict) else getattr(res, "share_url", None)},
    )
    db.commit()
    return res


@router.post("/{invoice_id}/dispatch", response_model=DispatchResponse, dependencies=[Depends(ALLOW_ADMIN)])
def dispatch_invoice(
    invoice_id: int,
    payload: Optional[DispatchCreate] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dispatches goods against an issued Tax Invoice (Admin only).
    - Decrements finished-goods inventory via post_movement (type=DISPATCH).
    - Blocks with 409 Conflict if stock is insufficient.
    - Prevents double dispatch.
    - Transitions order status to DISPATCHED.
    """
    p = payload or DispatchCreate()
    return invoicing_service.dispatch_invoice(db=db, invoice_id=invoice_id, payload=p, user=current_user)


@router.post("/{invoice_id}/credit-note", response_model=CreditNoteResponse, dependencies=[Depends(ALLOW_ADMIN)])
def create_credit_note(
    invoice_id: int,
    payload: CreditNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancels a posted Tax Invoice by issuing a full statutory GST Credit Note (Admin only).
    - Reverses tax totals and marks invoice CANCELLED.
    - Restores inventory if previously dispatched (when return_stock=true).
    - Cancels associated order if not yet dispatched.
    """
    return invoicing_service.create_credit_note_for_invoice(
        db=db, invoice_id=invoice_id, payload=payload, user=current_user
    )


@router.get("/credit-notes/{credit_note_id}/pdf", dependencies=[Depends(ALLOW_READ)])
def get_credit_note_pdf(credit_note_id: int, db: Session = Depends(get_db)):
    """
    Generates and downloads the official GST Credit Note PDF.
    """
    credit_note = db.scalar(
        select(CreditNote)
        .options(
            selectinload(CreditNote.lines),
            selectinload(CreditNote.invoice),
        )
        .where(CreditNote.id == credit_note_id)
    )
    if not credit_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Credit Note {credit_note_id} not found")

    pdf_bytes = generate_invoice_pdf(credit_note)
    log_audit(
        db=db,
        user=None,
        action="REPORT_EXPORTED",
        entity_type="CreditNote",
        entity_id=str(credit_note.id),
        new_values={"format": "PDF", "credit_note_no": credit_note.credit_note_no},
    )
    db.commit()
    safe_no = credit_note.credit_note_no.replace("/", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_no}.pdf"'},
    )


@router.get("/{invoice_id}/history", response_model=list[DocumentHistoryItem], dependencies=[Depends(ALLOW_READ)])
def get_invoice_history(invoice_id: int, db: Session = Depends(get_db)):
    """
    Returns the complete chronological audit timeline for this invoice (what changed, by whom, when).
    Includes creation, sharing, dispatch, credit notes, exports, and any rejected edit attempts.
    """
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    from sqlalchemy import func
    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(
            func.lower(AuditLog.entity_type) == "invoice",
            AuditLog.entity_id == str(invoice_id),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    )
    logs = db.scalars(stmt).all()
    return [
        DocumentHistoryItem(
            id=l.id,
            action=l.action,
            entity_type=l.entity_type,
            entity_id=l.entity_id,
            user_id=l.user_id,
            user_name=l.user.full_name if l.user else None,
            request_id=l.request_id,
            ip_address=l.ip_address,
            old_values=l.old_values,
            new_values=l.new_values,
            created_at=l.created_at,
        )
        for l in logs
    ]


@router.put("/{invoice_id}", dependencies=[Depends(ALLOW_ADMIN)])
@router.patch("/{invoice_id}", dependencies=[Depends(ALLOW_ADMIN)])
def update_invoice(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Direct edits to posted invoices are strictly forbidden.
    Invoices are generated from approved orders and are immutable once posted.
    Logs an audit row with action 'edit_rejected' and the attempted fields, and returns 409 Conflict.
    """
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    log_audit(
        db=db,
        user=current_user,
        action="edit_rejected",
        entity_type="invoice",
        entity_id=str(invoice.id),
        old_values={"status": invoice.status.value, "invoice_no": invoice.invoice_no},
        new_values=payload,
    )
    db.commit()

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Cannot edit invoice {invoice.invoice_no}. Invoices are immutable once posted. "
            "Pre-invoice edits must be made on the order before approval. "
            "To cancel a posted invoice, issue a statutory credit note."
        ),
    )


@router.delete("/{invoice_id}", dependencies=[Depends(ALLOW_ADMIN)])
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletion of invoices is strictly forbidden.
    Logs an audit row with action 'edit_rejected' and returns 409 Conflict.
    """
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {invoice_id} not found")

    log_audit(
        db=db,
        user=current_user,
        action="edit_rejected",
        entity_type="invoice",
        entity_id=str(invoice.id),
        old_values={"status": invoice.status.value, "invoice_no": invoice.invoice_no},
        new_values={"attempted_action": "delete"},
    )
    db.commit()

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Posted invoices cannot be deleted. Use a credit note to cancel.",
    )
