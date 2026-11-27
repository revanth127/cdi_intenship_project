from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.company import CompanySettings
from app.models.customer import Customer
from app.models.invoice import CreditNote, CreditNoteStatus, Invoice, InvoiceLine, InvoiceStatus
from app.models.payment import Payment, PaymentAllocation, PaymentMode, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.payment import PaymentCreate
from app.schemas.receivables import (
    AgeingCustomerRow,
    CollectionsSummaryResponse,
    CustomerOutstandingResponse,
    CustomerStatementResponse,
    DailyCollectionItem,
    InvoiceOutstandingResponse,
    ReceivablesAgeingResponse,
    StatementTransaction,
)
from app.services.audit import log_audit
from app.services.invoicing import get_next_sequence_number

logger = logging.getLogger("receivables_service")


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime object is timezone-aware UTC for safe comparisons across SQLite and Postgres."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(dt_val: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """Parses optional datetime string or object, normalizing query string URL-decoding spaces to +."""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        return ensure_utc(dt_val)
    dt_str = str(dt_val).strip()
    if not dt_str:
        return None
    if " " in dt_str and "+" not in dt_str and dt_str.count("-") >= 2:
        parts = dt_str.rsplit(" ", 1)
        if len(parts) == 2 and ":" in parts[1]:
            dt_str = f"{parts[0]}+{parts[1]}"
    try:
        dt = datetime.fromisoformat(dt_str)
        return ensure_utc(dt)
    except Exception:
        return None


def get_next_receipt_number(db: Session, date: Optional[datetime] = None) -> tuple[str, str]:
    """Generates sequential receipt number RCT/YYYY-YY/XXXX <= 16 characters."""
    return get_next_sequence_number(db, "PAYMENT", "RCT", date)


def attach_payment_details(payment: Payment) -> Payment:
    """Computes allocated and unallocated advance amounts for payment serialization."""
    alloc_sum = sum(a.amount_paise for a in payment.allocations)
    payment.allocated_paise = alloc_sum
    if payment.status == PaymentStatus.POSTED:
        payment.unallocated_advance_paise = max(0, payment.amount_paise - alloc_sum)
    else:
        payment.unallocated_advance_paise = 0

    if payment.customer:
        payment.customer_name = payment.customer.name
    return payment


def invoice_outstanding(
    db: Session,
    invoice: Invoice,
    as_of: Optional[datetime] = None,
) -> int:
    """
    Computes the outstanding unpaid balance of an invoice as of a specific date:
      outstanding = grand_total_paise - credit_notes_total - posted_allocations
    Cancelled invoices always have outstanding = 0.
    """
    if invoice.status == InvoiceStatus.CANCELLED:
        return 0

    grand_total = invoice.grand_total_paise
    target_date = ensure_utc(as_of)

    # Sum of posted credit notes against this invoice up to as_of
    cn_total = 0
    for cn in invoice.credit_notes:
        if cn.status == CreditNoteStatus.POSTED:
            if target_date is None or ensure_utc(cn.credit_note_date) <= target_date:
                cn_total += cn.grand_total_paise

    # Sum of posted payment allocations against this invoice up to as_of
    alloc_total = 0
    for alloc in invoice.allocations:
        if alloc.payment.status == PaymentStatus.POSTED:
            if target_date is None or ensure_utc(alloc.payment.payment_date) <= target_date:
                alloc_total += alloc.amount_paise

    return max(0, grand_total - cn_total - alloc_total)


def customer_unallocated_advance(
    db: Session,
    customer_id: int,
    as_of: Optional[datetime] = None,
) -> int:
    """
    Computes the total unallocated advance held for a customer from all POSTED payments.
    """
    target_date = ensure_utc(as_of)
    stmt = (
        select(Payment)
        .options(selectinload(Payment.allocations))
        .where(
            Payment.customer_id == customer_id,
            Payment.status == PaymentStatus.POSTED,
        )
    )
    if target_date:
        stmt = stmt.where(Payment.payment_date <= target_date)

    payments = db.scalars(stmt).all()
    total_advance = 0

    for p in payments:
        alloc_sum = 0
        for a in p.allocations:
            if target_date is None or ensure_utc(p.payment_date) <= target_date:
                alloc_sum += a.amount_paise
        advance = max(0, p.amount_paise - alloc_sum)
        total_advance += advance

    return total_advance


def get_customer_outstanding(
    db: Session,
    customer_id: int,
    as_of: Optional[datetime] = None,
) -> CustomerOutstandingResponse:
    """
    Calculates complete receivables status for a customer:
    - sum of invoice outstandings
    - unallocated advance
    - net receivable (positive for amount due, negative for advance credit balance)
    """
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    target_date = ensure_utc(as_of) or datetime.now(timezone.utc)

    # 1. Query POSTED invoices up to target_date
    inv_stmt = (
        select(Invoice)
        .options(
            selectinload(Invoice.credit_notes),
            selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
        )
        .where(
            Invoice.customer_id == customer_id,
            Invoice.status == InvoiceStatus.POSTED,
            Invoice.invoice_date <= target_date,
        )
        .order_by(Invoice.invoice_date.asc(), Invoice.id.asc())
    )
    invoices = db.scalars(inv_stmt).all()

    inv_responses = []
    total_invoiced = 0
    total_credit_notes = 0
    total_open_outstanding = 0

    for inv in invoices:
        total_invoiced += inv.grand_total_paise
        cn_sum = sum(
            cn.grand_total_paise
            for cn in inv.credit_notes
            if cn.status == CreditNoteStatus.POSTED and ensure_utc(cn.credit_note_date) <= target_date
        )
        total_credit_notes += cn_sum

        paid_sum = sum(
            a.amount_paise
            for a in inv.allocations
            if a.payment.status == PaymentStatus.POSTED and ensure_utc(a.payment.payment_date) <= target_date
        )

        out = invoice_outstanding(db, inv, target_date)
        age = max(0, (target_date.date() - ensure_utc(inv.invoice_date).date()).days)

        if out > 0:
            total_open_outstanding += out
            inv_responses.append(
                InvoiceOutstandingResponse(
                    invoice_id=inv.id,
                    invoice_no=inv.invoice_no,
                    invoice_date=inv.invoice_date,
                    customer_id=customer.id,
                    customer_name=customer.name,
                    grand_total_paise=inv.grand_total_paise,
                    credit_notes_total_paise=cn_sum,
                    paid_allocations_paise=paid_sum,
                    outstanding_paise=out,
                    age_days=age,
                    status=inv.status.value,
                )
            )

    # 2. Total POSTED Payments up to target_date
    p_stmt = select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
        Payment.customer_id == customer_id,
        Payment.status == PaymentStatus.POSTED,
        Payment.payment_date <= target_date,
    )
    total_payments = int(db.scalar(p_stmt) or 0)

    # 3. Unallocated Advance
    advance = customer_unallocated_advance(db, customer_id, target_date)

    # 4. Net Outstanding (positive = customer owes; negative = advance credit)
    net_outstanding = total_open_outstanding - advance

    return CustomerOutstandingResponse(
        customer_id=customer.id,
        customer_name=customer.name,
        total_invoiced_paise=total_invoiced,
        total_credit_notes_paise=total_credit_notes,
        total_payments_paise=total_payments,
        open_invoices_outstanding_paise=total_open_outstanding,
        unallocated_advance_paise=advance,
        total_outstanding_paise=net_outstanding,
        invoices=inv_responses,
    )


def post_payment(db: Session, payload: PaymentCreate, user: User) -> Payment:
    """
    Posts a customer payment in ONE transaction:
    - Generates sequential receipt number RCT/YYYY-YY/XXXX.
    - If allocations are supplied: validates each allocation against invoice outstanding.
      Over-allocation is strictly blocked with HTTP 409 Conflict.
    - If allocations are omitted: applies FIFO auto-allocation to oldest open invoices first.
    - Any unallocated excess is held as customer advance.
    - Records audit log entry.
    """
    customer = db.get(Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {payload.customer_id} not found")
    if not customer.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot record payment for inactive customer")

    if payload.amount_paise <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount must be greater than zero.")

    now = datetime.now(timezone.utc)
    payment_date = ensure_utc(payload.payment_date) or now
    receipt_no, _ = get_next_receipt_number(db, payment_date)

    payment = Payment(
        receipt_no=receipt_no,
        customer_id=customer.id,
        payment_date=payment_date,
        amount_paise=payload.amount_paise,
        mode=payload.mode,
        reference_no=payload.reference_no,
        status=PaymentStatus.POSTED,
        notes=payload.notes,
        created_by=user.id,
        created_at=now,
    )

    # Allocation processing
    if payload.allocations is not None and len(payload.allocations) > 0:
        alloc_total = sum(a.amount_paise for a in payload.allocations)
        if alloc_total > payload.amount_paise:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total allocation ({alloc_total} paise) exceeds payment amount ({payload.amount_paise} paise).",
            )

        for alloc in payload.allocations:
            inv = db.scalar(
                select(Invoice)
                .options(
                    selectinload(Invoice.credit_notes),
                    selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
                )
                .where(Invoice.id == alloc.invoice_id)
            )
            if not inv:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice {alloc.invoice_id} not found")
            if inv.customer_id != customer.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invoice {inv.invoice_no} does not belong to Customer {customer.name}",
                )
            if inv.status != InvoiceStatus.POSTED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot allocate payment to invoice {inv.invoice_no} with status '{inv.status.value}'",
                )

            current_out = invoice_outstanding(db, inv)
            if alloc.amount_paise > current_out:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Allocation amount of {alloc.amount_paise} paise exceeds "
                        f"current outstanding of {current_out} paise for Invoice {inv.invoice_no}."
                    ),
                )

            pa = PaymentAllocation(
                invoice_id=inv.id,
                amount_paise=alloc.amount_paise,
            )
            payment.allocations.append(pa)
    else:
        # FIFO Auto-allocation: oldest invoice first
        open_invoices = db.scalars(
            select(Invoice)
            .options(
                selectinload(Invoice.credit_notes),
                selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
            )
            .where(
                Invoice.customer_id == customer.id,
                Invoice.status == InvoiceStatus.POSTED,
            )
            .order_by(Invoice.invoice_date.asc(), Invoice.id.asc())
        ).all()

        remaining_paise = payload.amount_paise
        for inv in open_invoices:
            if remaining_paise <= 0:
                break
            cur_out = invoice_outstanding(db, inv)
            if cur_out <= 0:
                continue

            alloc_amt = min(remaining_paise, cur_out)
            pa = PaymentAllocation(
                invoice_id=inv.id,
                amount_paise=alloc_amt,
            )
            payment.allocations.append(pa)
            remaining_paise -= alloc_amt

    db.add(payment)
    db.commit()
    db.refresh(payment)

    log_audit(
        db=db,
        user=user,
        action="PAYMENT_POSTED",
        entity_type="Payment",
        entity_id=payment.id,
        new_values={
            "receipt_no": payment.receipt_no,
            "customer_id": payment.customer_id,
            "amount_paise": payment.amount_paise,
            "mode": payment.mode.value,
            "allocations_count": len(payment.allocations),
        },
    )

    return attach_payment_details(payment)


def reverse_payment(db: Session, payment_id: int, reason: str, user: User) -> Payment:
    """
    Reverses a posted payment (Admin only).
    - Preserves payment row and allocation links for statutory audit trail.
    - Transitions status to REVERSED, which immediately removes its effect from invoice and customer outstandings.
    - Records audit log entry.
    """
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mandatory reversal reason of at least 3 characters is required.",
        )

    payment = db.scalar(
        select(Payment)
        .options(selectinload(Payment.allocations), selectinload(Payment.customer))
        .where(Payment.id == payment_id)
    )
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payment {payment_id} not found")

    if payment.status == PaymentStatus.REVERSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment {payment.receipt_no} is already reversed.",
        )

    now = datetime.now(timezone.utc)
    payment.status = PaymentStatus.REVERSED
    payment.reversed_at = now
    payment.reverse_reason = reason.strip()

    log_audit(
        db=db,
        user=user,
        action="PAYMENT_REVERSED",
        entity_type="Payment",
        entity_id=payment.id,
        old_values={"status": PaymentStatus.POSTED.value},
        new_values={
            "status": PaymentStatus.REVERSED.value,
            "reversed_at": str(now),
            "reverse_reason": payment.reverse_reason,
        },
    )

    db.commit()
    db.refresh(payment)
    return attach_payment_details(payment)


def allocate_advance(db: Session, customer_id: int, user: User) -> list[PaymentAllocation]:
    """
    Applies existing unallocated advance from POSTED payments to open invoices (FIFO, Admin only).
    """
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    # Payments with unallocated balance
    payments = db.scalars(
        select(Payment)
        .options(selectinload(Payment.allocations))
        .where(
            Payment.customer_id == customer.id,
            Payment.status == PaymentStatus.POSTED,
        )
        .order_by(Payment.payment_date.asc(), Payment.id.asc())
    ).all()

    # Open invoices
    open_invoices = db.scalars(
        select(Invoice)
        .options(
            selectinload(Invoice.credit_notes),
            selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
        )
        .where(
            Invoice.customer_id == customer.id,
            Invoice.status == InvoiceStatus.POSTED,
        )
        .order_by(Invoice.invoice_date.asc(), Invoice.id.asc())
    ).all()

    new_allocations = []

    for p in payments:
        alloc_sum = sum(a.amount_paise for a in p.allocations)
        unalloc = max(0, p.amount_paise - alloc_sum)
        if unalloc <= 0:
            continue

        for inv in open_invoices:
            if unalloc <= 0:
                break
            cur_out = invoice_outstanding(db, inv)
            if cur_out <= 0:
                continue

            amt = min(unalloc, cur_out)
            pa = PaymentAllocation(
                payment_id=p.id,
                invoice_id=inv.id,
                amount_paise=amt,
            )
            db.add(pa)
            new_allocations.append(pa)
            unalloc -= amt

    if new_allocations:
        db.commit()
        log_audit(
            db=db,
            user=user,
            action="ADVANCE_ALLOCATED",
            entity_type="Customer",
            entity_id=customer.id,
            new_values={"new_allocations_count": len(new_allocations)},
        )

    return new_allocations


def get_receivables_ageing(
    db: Session,
    as_of: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    salesman_id: Optional[int] = None,
) -> ReceivablesAgeingResponse:
    """
    Computes receivables ageing breakdown per customer as of a specific date.
    Age is measured from invoice_date to as_of date.
    Statutory Buckets:
      - 0-30 days: (0 <= days <= 30)
      - 31-60 days: (31 <= days <= 60)
      - 61-90 days: (61 <= days <= 90)
      - 90+ days: (days > 90)
    Accounts for payments and credit notes strictly up to the as_of date.
    """
    target_date = ensure_utc(as_of) or datetime.now(timezone.utc)

    stmt = select(Customer).where(Customer.is_active == True)
    if customer_id:
        stmt = stmt.where(Customer.id == customer_id)
    if salesman_id:
        stmt = stmt.where(Customer.assigned_salesman_id == salesman_id)

    customers = db.scalars(stmt.order_by(Customer.name.asc())).all()

    total_b0 = 0
    total_b31 = 0
    total_b61 = 0
    total_b90 = 0
    total_adv = 0
    total_out = 0

    rows: list[AgeingCustomerRow] = []

    for cust in customers:
        # Load invoices up to target_date
        invs = db.scalars(
            select(Invoice)
            .options(
                selectinload(Invoice.credit_notes),
                selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
            )
            .where(
                Invoice.customer_id == cust.id,
                Invoice.status == InvoiceStatus.POSTED,
                Invoice.invoice_date <= target_date,
            )
            .order_by(Invoice.invoice_date.asc())
        ).all()

        b0 = 0
        b31 = 0
        b61 = 0
        b90 = 0
        oldest_date = None

        for inv in invs:
            out = invoice_outstanding(db, inv, as_of=target_date)
            if out > 0:
                if oldest_date is None:
                    oldest_date = inv.invoice_date
                age_days = (target_date.date() - ensure_utc(inv.invoice_date).date()).days
                if age_days <= 30:
                    b0 += out
                elif age_days <= 60:
                    b31 += out
                elif age_days <= 90:
                    b61 += out
                else:
                    b90 += out

        gross_out = b0 + b31 + b61 + b90
        adv = customer_unallocated_advance(db, cust.id, as_of=target_date)
        net_cust_out = gross_out - adv

        total_b0 += b0
        total_b31 += b31
        total_b61 += b61
        total_b90 += b90
        total_adv += adv
        total_out += net_cust_out

        salesman_name = cust.assigned_salesman.full_name if cust.assigned_salesman else None

        rows.append(
            AgeingCustomerRow(
                customer_id=cust.id,
                customer_name=cust.name,
                assigned_salesman_id=cust.assigned_salesman_id,
                assigned_salesman_name=salesman_name,
                bucket_0_30_paise=b0,
                bucket_31_60_paise=b31,
                bucket_61_90_paise=b61,
                bucket_90_plus_paise=b90,
                gross_outstanding_paise=gross_out,
                unallocated_advance_paise=adv,
                total_outstanding_paise=net_cust_out,
                oldest_invoice_date=oldest_date,
            )
        )

    return ReceivablesAgeingResponse(
        as_of=target_date,
        total_bucket_0_30_paise=total_b0,
        total_bucket_31_60_paise=total_b31,
        total_bucket_61_90_paise=total_b61,
        total_bucket_90_plus_paise=total_b90,
        total_unallocated_advance_paise=total_adv,
        grand_total_outstanding_paise=total_out,
        customers=rows,
    )


def get_customer_statement(
    db: Session,
    customer_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> CustomerStatementResponse:
    """
    Generates a formal Customer Statement of Account with running balance:
    - Opening balance prior to from_date.
    - Invoices (debit: increases balance).
    - Credit notes (credit: decreases balance).
    - Payments (credit: decreases balance).
    - Closing balance matches customer_outstanding(to_date).
    """
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    end_dt = ensure_utc(to_date) or datetime.now(timezone.utc)
    start_dt = ensure_utc(from_date) or (end_dt - timedelta(days=90))

    # 1. Opening Balance prior to start_dt
    inv_prior = int(
        db.scalar(
            select(func.coalesce(func.sum(Invoice.grand_total_paise), 0)).where(
                Invoice.customer_id == customer.id,
                Invoice.status == InvoiceStatus.POSTED,
                Invoice.invoice_date < start_dt,
            )
        )
        or 0
    )
    cn_prior = int(
        db.scalar(
            select(func.coalesce(func.sum(CreditNote.grand_total_paise), 0)).where(
                CreditNote.customer_id == customer.id,
                CreditNote.status == CreditNoteStatus.POSTED,
                CreditNote.credit_note_date < start_dt,
            )
        )
        or 0
    )
    pay_prior = int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
                Payment.customer_id == customer.id,
                Payment.status == PaymentStatus.POSTED,
                Payment.payment_date < start_dt,
            )
        )
        or 0
    )
    opening_bal = inv_prior - cn_prior - pay_prior

    # 2. Period Transactions
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.customer_id == customer.id,
            Invoice.status == InvoiceStatus.POSTED,
            Invoice.invoice_date >= start_dt,
            Invoice.invoice_date <= end_dt,
        )
    ).all()

    credit_notes = db.scalars(
        select(CreditNote).where(
            CreditNote.customer_id == customer.id,
            CreditNote.status == CreditNoteStatus.POSTED,
            CreditNote.credit_note_date >= start_dt,
            CreditNote.credit_note_date <= end_dt,
        )
    ).all()

    payments = db.scalars(
        select(Payment).where(
            Payment.customer_id == customer.id,
            Payment.status == PaymentStatus.POSTED,
            Payment.payment_date >= start_dt,
            Payment.payment_date <= end_dt,
        )
    ).all()

    raw_items = []
    for inv in invoices:
        raw_items.append({
            "date": ensure_utc(inv.invoice_date),
            "type": "INVOICE",
            "ref": inv.invoice_no,
            "desc": f"Tax Invoice {inv.invoice_no}",
            "debit": inv.grand_total_paise,
            "credit": 0,
        })
    for cn in credit_notes:
        raw_items.append({
            "date": ensure_utc(cn.credit_note_date),
            "type": "CREDIT_NOTE",
            "ref": cn.credit_note_no,
            "desc": f"Credit Note {cn.credit_note_no} ({cn.reason})",
            "debit": 0,
            "credit": cn.grand_total_paise,
        })
    for p in payments:
        raw_items.append({
            "date": ensure_utc(p.payment_date),
            "type": "PAYMENT",
            "ref": p.receipt_no,
            "desc": f"Payment Receipt {p.receipt_no} via {p.mode.value}"
            + (f" [Ref: {p.reference_no}]" if p.reference_no else ""),
            "debit": 0,
            "credit": p.amount_paise,
        })

    # Sort chronological
    raw_items.sort(key=lambda x: x["date"])

    running_bal = opening_bal
    transactions = []
    total_debits = 0
    total_credits = 0

    for item in raw_items:
        running_bal += item["debit"] - item["credit"]
        total_debits += item["debit"]
        total_credits += item["credit"]
        transactions.append(
            StatementTransaction(
                date=item["date"],
                type=item["type"],
                reference_no=item["ref"],
                description=item["desc"],
                debit_paise=item["debit"],
                credit_paise=item["credit"],
                running_balance_paise=running_bal,
            )
        )

    return CustomerStatementResponse(
        customer_id=customer.id,
        customer_name=customer.name,
        from_date=start_dt,
        to_date=end_dt,
        opening_balance_paise=opening_bal,
        total_debits_paise=total_debits,
        total_credits_paise=total_credits,
        closing_balance_paise=running_bal,
        transactions=transactions,
    )


def get_collections_summary(
    db: Session,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> CollectionsSummaryResponse:
    """
    Returns collections summary grouped by mode and by date.
    """
    end_dt = ensure_utc(to_date) or datetime.now(timezone.utc)
    start_dt = ensure_utc(from_date) or (end_dt - timedelta(days=30))

    payments = db.scalars(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.POSTED,
            Payment.payment_date >= start_dt,
            Payment.payment_date <= end_dt,
        )
        .order_by(Payment.payment_date.asc())
    ).all()

    total_cash = 0
    total_upi = 0
    total_bank = 0
    total_cheque = 0
    grand_total = 0

    by_date_dict: dict[str, dict[str, int]] = {}

    for p in payments:
        grand_total += p.amount_paise
        d_str = p.payment_date.strftime("%Y-%m-%d")
        if d_str not in by_date_dict:
            by_date_dict[d_str] = {
                "cash": 0,
                "upi": 0,
                "bank": 0,
                "cheque": 0,
                "total": 0,
                "count": 0,
            }

        by_date_dict[d_str]["total"] += p.amount_paise
        by_date_dict[d_str]["count"] += 1

        if p.mode == PaymentMode.CASH:
            total_cash += p.amount_paise
            by_date_dict[d_str]["cash"] += p.amount_paise
        elif p.mode == PaymentMode.UPI:
            total_upi += p.amount_paise
            by_date_dict[d_str]["upi"] += p.amount_paise
        elif p.mode == PaymentMode.BANK:
            total_bank += p.amount_paise
            by_date_dict[d_str]["bank"] += p.amount_paise
        elif p.mode == PaymentMode.CHEQUE:
            total_cheque += p.amount_paise
            by_date_dict[d_str]["cheque"] += p.amount_paise

    daily_list = [
        DailyCollectionItem(
            date=d,
            cash_paise=data["cash"],
            upi_paise=data["upi"],
            bank_paise=data["bank"],
            cheque_paise=data["cheque"],
            total_paise=data["total"],
            count=data["count"],
        )
        for d, data in sorted(by_date_dict.items())
    ]

    return CollectionsSummaryResponse(
        from_date=start_dt,
        to_date=end_dt,
        total_cash_paise=total_cash,
        total_upi_paise=total_upi,
        total_bank_paise=total_bank,
        total_cheque_paise=total_cheque,
        grand_total_collected_paise=grand_total,
        payment_count=len(payments),
        daily_breakdown=daily_list,
    )
