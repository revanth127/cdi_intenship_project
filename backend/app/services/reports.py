"""Report registry: each report is one function returning title, filters, columns, rows, totals.

Shared exporters (see app.services.report_export) render the SAME result as
JSON / CSV / XLSX / PDF. Business dates are plain IST dates; money is integer
paise internally.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invoice import CreditNote, Invoice, InvoiceLine, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.costing import RunCostSheet
from app.models.purchase import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import StockMovement
from app.services import receivables as receivables_service
from app.services.stock import get_stock_ledger, get_stock_summary

IST = ZoneInfo("Asia/Kolkata")

Column = dict[str, str]
ReportResult = dict[str, Any]


# ---------------------------------------------------------------------------
# IST business-date helpers
# ---------------------------------------------------------------------------

def ist_date(value: datetime) -> date:
    """Convert a stored UTC timestamp to a plain IST business date."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST).date()


def parse_ist_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    # Accept YYYY-MM-DD (plain IST date); ignore any time component.
    return date.fromisoformat(value[:10])


def ist_day_start_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=IST).astimezone(timezone.utc)


def ist_day_end_utc(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=IST).astimezone(timezone.utc) - timedelta(microseconds=1)


def in_period(dt: Optional[datetime], from_date: Optional[date], to_date: Optional[date]) -> bool:
    if dt is None:
        return False
    d = ist_date(dt)
    if from_date and d < from_date:
        return False
    if to_date and d > to_date:
        return False
    return True


def period_utc_bounds(from_date: Optional[date], to_date: Optional[date]) -> tuple[Optional[datetime], Optional[datetime]]:
    start = ist_day_start_utc(from_date) if from_date else None
    end = ist_day_end_utc(to_date) if to_date else None
    return start, end


def money(amount_paise: int) -> Decimal:
    return (Decimal(amount_paise or 0) / Decimal(100)).quantize(Decimal("0.01"))


def _plain_number_str(text: str) -> str:
    """Plain fixed-point string; trim trailing zeros only in the fraction."""
    out = format(Decimal(text), "f")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out or "0"


def _plain(value: Any) -> Any:
    """Render Decimal scientific notation as plain string."""
    if isinstance(value, Decimal):
        return _plain_number_str(str(value))
    if isinstance(value, str):
        try:
            return _plain_number_str(value)
        except ArithmeticError:
            return value
    return value


def num(value: Any) -> Any:
    """Normalize Decimal/int for JSON output."""
    if isinstance(value, Decimal):
        return float(value)
    return value


# ---------------------------------------------------------------------------
# Report registry
# ---------------------------------------------------------------------------

ReportFn = Callable[[Session, Optional[date], Optional[date], Optional[date]], ReportResult]

REPORTS: dict[str, dict[str, Any]] = {}


def register(name: str, title: str, scope: str, description: str):
    def wrap(fn: ReportFn) -> ReportFn:
        REPORTS[name] = {
            "name": name,
            "title": title,
            "scope": scope,  # 'all' or 'production'
            "description": description,
            "fn": fn,
        }
        return fn

    return wrap


def list_reports(role: str) -> list[dict[str, Any]]:
    out = []
    for r in REPORTS.values():
        if role == "PRODUCTION" and r["scope"] != "production":
            continue
        out.append({k: v for k, v in r.items() if k != "fn"})
    return out


def _col(key: str, label: str, type_: str) -> Column:
    return {"key": key, "label": label, "type": type_}


def _totals(rows: list[dict[str, Any]], money_keys: list[str], **extra: Any) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for k in money_keys:
        totals[k] = sum(int(r.get(k) or 0) for r in rows)
    totals.update(extra)
    return totals


# ---------------------------------------------------------------------------
# 1. sales_register — invoices and credit notes
# ---------------------------------------------------------------------------

@register(
    "sales_register",
    "Sales Register",
    "all",
    "Tax invoices and credit notes with customer, GSTIN, place of supply, taxable, CGST, SGST, IGST, total, status.",
)
def sales_register(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    invoices = db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.POSTED).order_by(Invoice.invoice_date, Invoice.id)
    ).all()
    credit_notes = db.scalars(select(CreditNote).order_by(CreditNote.credit_note_date, CreditNote.id)).all()

    rows: list[dict[str, Any]] = []
    for inv in invoices:
        if not in_period(inv.invoice_date, from_date, to_date):
            continue
        rows.append({
            "document_type": "INVOICE",
            "document_no": inv.invoice_no,
            "date": ist_date(inv.invoice_date).isoformat(),
            "customer": inv.buyer_name,
            "customer_gstin": inv.buyer_gstin or "",
            "place_of_supply_state_code": inv.place_of_supply_state_code,
            "is_igst": bool(inv.is_igst),
            "taxable_paise": int(inv.taxable_total_paise),
            "cgst_paise": int(inv.cgst_total_paise),
            "sgst_paise": int(inv.sgst_total_paise),
            "igst_paise": int(inv.igst_total_paise),
            "total_paise": int(inv.grand_total_paise),
            "status": inv.status.value,
        })
    for cn in credit_notes:
        if not in_period(cn.credit_note_date, from_date, to_date):
            continue
        rows.append({
            "document_type": "CREDIT_NOTE",
            "document_no": cn.credit_note_no,
            "date": ist_date(cn.credit_note_date).isoformat(),
            "customer": cn.buyer_name,
            "customer_gstin": cn.buyer_gstin or "",
            "place_of_supply_state_code": cn.place_of_supply_state_code,
            "is_igst": bool(cn.is_igst),
            "taxable_paise": int(cn.taxable_total_paise),
            "cgst_paise": int(cn.cgst_total_paise),
            "sgst_paise": int(cn.sgst_total_paise),
            "igst_paise": int(cn.igst_total_paise),
            "total_paise": int(cn.grand_total_paise),
            "status": cn.status.value,
        })

    # Credit notes reduce sales totals.
    def signed(row: dict[str, Any], key: str) -> int:
        v = int(row[key])
        return -v if row["document_type"] == "CREDIT_NOTE" else v

    money_keys = ["taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise"]
    totals = {k: sum(signed(r, k) for r in rows) for k in money_keys}
    totals["row_count"] = len(rows)

    return {
        "name": "sales_register",
        "title": "Sales Register",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("document_type", "Type", "string"),
            _col("document_no", "Document", "string"),
            _col("date", "Date (IST)", "date"),
            _col("customer", "Customer", "string"),
            _col("customer_gstin", "Customer GSTIN", "string"),
            _col("place_of_supply_state_code", "Place of supply", "string"),
            _col("taxable_paise", "Taxable", "money_paise"),
            _col("cgst_paise", "CGST", "money_paise"),
            _col("sgst_paise", "SGST", "money_paise"),
            _col("igst_paise", "IGST", "money_paise"),
            _col("total_paise", "Total", "money_paise"),
            _col("status", "Status", "string"),
        ],
        "rows": rows,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# 2. stock_summary
# ---------------------------------------------------------------------------

@register("stock_summary", "Stock Summary", "production", "Closing stock per item (raw material, packaging, finished goods) with weighted-average cost.")
def stock_summary(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    effective_to = as_of or to_date
    start, end = period_utc_bounds(from_date, effective_to)
    summary = get_stock_summary(db, from_date=start, to_date=end)
    rows = [{
        "item_id": s["item_id"],
        "name": s["name"],
        "item_type": s["item_type"],
        "base_unit": s["base_unit"],
        "display_unit": s["display_unit"],
        "opening_balance_base": s["opening_balance_base"],
        "receipts_base": s["receipts_base"],
        "issues_base": s["issues_base"],
        "adjustments_base": s["adjustments_base"],
        "closing_balance_base": s["closing_balance_base"],
        "closing_balance_display": _plain(s["closing_balance_display"]),
        "weighted_avg_cost_paise": num(s["weighted_avg_cost_paise"]),
        "total_value_paise": s["total_value_paise"],
        "reconciled": s["reconciled"],
    } for s in summary]

    return {
        "name": "stock_summary",
        "title": "Stock Summary",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": effective_to.isoformat() if effective_to else None, "as_of": as_of.isoformat() if as_of else None},
        "columns": [
            _col("name", "Item", "string"),
            _col("item_type", "Type", "string"),
            _col("base_unit", "Base unit", "string"),
            _col("opening_balance_base", "Opening", "number"),
            _col("receipts_base", "Received", "number"),
            _col("issues_base", "Issued", "number"),
            _col("adjustments_base", "Adjusted", "number"),
            _col("closing_balance_base", "Closing (base)", "number"),
            _col("closing_balance_display", "Closing (display)", "string"),
            _col("weighted_avg_cost_paise", "Avg cost (paise)", "number"),
            _col("total_value_paise", "Value", "money_paise"),
        ],
        "rows": rows,
        "totals": _totals(rows, ["total_value_paise"], item_count=len(rows)),
    }


# ---------------------------------------------------------------------------
# 3. stock_ledger
# ---------------------------------------------------------------------------

@register("stock_ledger", "Stock Ledger", "production", "Every stock movement with running balance, valuation, and source document.")
def stock_ledger_report(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    item_ids = db.scalars(select(StockMovement.item_id).distinct()).all()
    start, end = period_utc_bounds(from_date, to_date)
    from app.models.item import Item
    item_names = {i.id: i.name for i in db.scalars(select(Item)).all()}
    rows: list[dict[str, Any]] = []
    for item_id in item_ids:
        for entry in get_stock_ledger(db, item_id=item_id, from_date=start, to_date=end):
            d = entry["date"]
            d_iso = ist_date(d).isoformat() if isinstance(d, datetime) else str(d)
            rows.append({
                "item_id": item_id,
                "item_name": item_names.get(item_id, ""),
                "date": d_iso,
                "movement_type": entry["movement_type"],
                "in_qty_base": entry["in_qty_base"],
                "out_qty_base": entry["out_qty_base"],
                "running_balance_base": entry["running_balance_base"],
                "unit_cost_paise": num(entry.get("unit_cost")),
                "value_paise": int(entry.get("value_paise") or 0),
                "source_type": entry.get("source_type") or "",
                "source_id": entry.get("source_id") or "",
            })
    rows.sort(key=lambda r: (r["item_name"] or "", r["date"], r["item_id"]))

    return {
        "name": "stock_ledger",
        "title": "Stock Ledger",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("item_name", "Item", "string"),
            _col("date", "Date (IST)", "date"),
            _col("movement_type", "Movement", "string"),
            _col("in_qty_base", "In (base)", "number"),
            _col("out_qty_base", "Out (base)", "number"),
            _col("running_balance_base", "Running balance", "number"),
            _col("unit_cost_paise", "Unit cost (paise)", "number"),
            _col("value_paise", "Value", "money_paise"),
            _col("source_type", "Source type", "string"),
            _col("source_id", "Source id", "string"),
        ],
        "rows": rows,
        "totals": _totals(rows, ["in_qty_base", "out_qty_base", "value_paise"], row_count=len(rows)),
    }


# ---------------------------------------------------------------------------
# 4. gst_outward — GSTR-1 / GSTR-3B 3.1(a) shaped
# ---------------------------------------------------------------------------

@register("gst_outward", "GST Outward Supplies", "all", "Outward B2B invoices, HSN summary, and GSTR-1 / GSTR-3B 3.1(a) totals.")
def gst_outward(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    invoices = db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.POSTED).order_by(Invoice.invoice_date, Invoice.id)
    ).all()
    invoices = [i for i in invoices if in_period(i.invoice_date, from_date, to_date)]

    rows: list[dict[str, Any]] = []
    hsn: dict[tuple[str, int], dict[str, int]] = {}
    for inv in invoices:
        rows.append({
            "document_no": inv.invoice_no,
            "date": ist_date(inv.invoice_date).isoformat(),
            "customer": inv.buyer_name,
            "customer_gstin": inv.buyer_gstin or "",
            "place_of_supply_state_code": inv.place_of_supply_state_code,
            "is_igst": bool(inv.is_igst),
            "taxable_paise": int(inv.taxable_total_paise),
            "cgst_paise": int(inv.cgst_total_paise),
            "sgst_paise": int(inv.sgst_total_paise),
            "igst_paise": int(inv.igst_total_paise),
            "total_paise": int(inv.grand_total_paise),
        })
        for line in inv.lines:
            key = (line.hsn_code or "", int(line.gst_rate_bp))
            agg = hsn.setdefault(key, {"hsn_code": key[0], "gst_rate_bp": key[1], "taxable_paise": 0, "cgst_paise": 0, "sgst_paise": 0, "igst_paise": 0, "total_paise": 0})
            agg["taxable_paise"] += int(line.taxable_paise)
            agg["cgst_paise"] += int(line.cgst_paise)
            agg["sgst_paise"] += int(line.sgst_paise)
            agg["igst_paise"] += int(line.igst_paise)
            agg["total_paise"] += int(line.line_total_paise)

    money_keys = ["taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise"]
    totals = {k: sum(r[k] for r in rows) for k in money_keys}
    totals["invoice_count"] = len(rows)
    # Credit notes reduce outward supplies.
    credit_notes = db.scalars(select(CreditNote)).all()
    cn_totals = {k: 0 for k in money_keys}
    for cn in credit_notes:
        if not in_period(cn.credit_note_date, from_date, to_date):
            continue
        cn_totals["taxable_paise"] += int(cn.taxable_total_paise)
        cn_totals["cgst_paise"] += int(cn.cgst_total_paise)
        cn_totals["sgst_paise"] += int(cn.sgst_total_paise)
        cn_totals["igst_paise"] += int(cn.igst_total_paise)
        cn_totals["total_paise"] += int(cn.grand_total_paise)
    net = {k: totals[k] - cn_totals[k] for k in money_keys}

    totals["credit_notes"] = cn_totals
    totals["gstr_3_1a"] = {
        # GSTR-3B section 3.1(a): outward taxable supplies (other than zero rated, nil rated, exempted)
        "outward_taxable_paise": net["taxable_paise"],
        "igst_paise": net["igst_paise"],
        "cgst_paise": net["cgst_paise"],
        "sgst_paise": net["sgst_paise"],
        "tax_paise": net["cgst_paise"] + net["sgst_paise"] + net["igst_paise"],
        "invoice_count": len(rows),
    }
    totals["hsn_summary"] = sorted(hsn.values(), key=lambda h: (h["hsn_code"], h["gst_rate_bp"]))

    return {
        "name": "gst_outward",
        "title": "GST Outward Supplies",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("document_no", "Document", "string"),
            _col("date", "Date (IST)", "date"),
            _col("customer", "Customer", "string"),
            _col("customer_gstin", "Customer GSTIN", "string"),
            _col("place_of_supply_state_code", "Place of supply", "string"),
            _col("taxable_paise", "Taxable", "money_paise"),
            _col("cgst_paise", "CGST", "money_paise"),
            _col("sgst_paise", "SGST", "money_paise"),
            _col("igst_paise", "IGST", "money_paise"),
            _col("total_paise", "Total", "money_paise"),
        ],
        "rows": rows,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# 5. purchase_register
# ---------------------------------------------------------------------------

@register("purchase_register", "Purchase Register", "all", "Supplier purchases received, per line, with totals.")
def purchase_register(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    purchases = db.scalars(
        select(Purchase).where(Purchase.status == PurchaseStatus.POSTED).order_by(Purchase.purchase_date, Purchase.id)
    ).all()
    rows: list[dict[str, Any]] = []
    for p in purchases:
        if not in_period(p.purchase_date, from_date, to_date):
            continue
        supplier_name = p.supplier.name if p.supplier else ""
        if not p.lines:
            rows.append({
                "purchase_no": p.purchase_no, "date": ist_date(p.purchase_date).isoformat(), "supplier": supplier_name,
                "supplier_invoice_no": p.supplier_invoice_no or "", "item": "", "item_type": "", "base_unit": "",
                "quantity_base": 0, "rate_paise": 0, "line_total_paise": 0, "purchase_total_paise": int(p.total_paise),
            })
        for line in p.lines:
            item = line.item
            rows.append({
                "purchase_no": p.purchase_no,
                "date": ist_date(p.purchase_date).isoformat(),
                "supplier": supplier_name,
                "supplier_invoice_no": p.supplier_invoice_no or "",
                "item": item.name if item else "",
                "item_type": item.item_type.value if item else "",
                "base_unit": item.base_unit if item else "",
                "quantity_base": int(line.quantity_base),
                "rate_paise": int(line.rate_paise),
                "line_total_paise": int(line.line_total_paise),
                "purchase_total_paise": int(p.total_paise),
            })

    return {
        "name": "purchase_register",
        "title": "Purchase Register",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("purchase_no", "Purchase no.", "string"),
            _col("date", "Date (IST)", "date"),
            _col("supplier", "Supplier", "string"),
            _col("supplier_invoice_no", "Supplier invoice", "string"),
            _col("item", "Item", "string"),
            _col("item_type", "Type", "string"),
            _col("base_unit", "Base unit", "string"),
            _col("quantity_base", "Quantity (base)", "number"),
            _col("rate_paise", "Rate (paise)", "number"),
            _col("line_total_paise", "Line total", "money_paise"),
        ],
        "rows": rows,
        "totals": _totals(rows, ["line_total_paise"], row_count=len(rows)),
    }


# ---------------------------------------------------------------------------
# 6. production_report
# ---------------------------------------------------------------------------

@register("production_report", "Production Report", "production", "Planned vs actual per item, yield, wastage, variance flags, cost per packet.")
def production_report(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    runs = db.scalars(select(ProductionRun).order_by(ProductionRun.run_date, ProductionRun.id)).all()
    rows: list[dict[str, Any]] = []
    for run in runs:
        if not in_period(run.run_date, from_date, to_date):
            continue
        product_name = run.product.pack_name if run.product else ""
        sheet = db.scalar(select(RunCostSheet).where(RunCostSheet.run_id == run.id))
        cost_per_packet = num(sheet.cost_per_packet) if sheet else num(run.unit_material_cost_paise)
        for line in run.lines:
            item = line.item
            rows.append({
                "run_no": run.run_no,
                "date": ist_date(run.run_date).isoformat(),
                "product": product_name,
                "status": run.status.value,
                "item": item.name if item else "",
                "base_unit": item.base_unit if item else "",
                "planned_qty_base": int(line.planned_qty_base),
                "actual_qty_base": int(line.actual_qty_base or 0),
                "damaged_qty_base": int(line.damaged_qty_base or 0),
                "variance_pct": num(line.variance_pct),
                "is_flagged": bool(line.is_flagged),
                "expected_output_packets": int(run.expected_output_packets),
                "actual_good_packets": int(run.actual_good_packets or 0),
                "wastage_packets": int(run.wastage_packets or 0),
                "yield_variance_pct": num(run.yield_variance_pct),
                "is_yield_flagged": bool(run.is_yield_flagged),
                "total_material_cost_paise": int(run.total_material_cost_paise or 0),
                "cost_per_packet_paise": cost_per_packet,
            })

    return {
        "name": "production_report",
        "title": "Production Report",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("run_no", "Run", "string"),
            _col("date", "Date (IST)", "date"),
            _col("product", "Product", "string"),
            _col("status", "Status", "string"),
            _col("item", "Item", "string"),
            _col("planned_qty_base", "Planned", "number"),
            _col("actual_qty_base", "Actual", "number"),
            _col("damaged_qty_base", "Damaged", "number"),
            _col("variance_pct", "Variance %", "percent"),
            _col("is_flagged", "Flagged", "bool"),
            _col("expected_output_packets", "Expected output", "number"),
            _col("actual_good_packets", "Good output", "number"),
            _col("wastage_packets", "Wastage", "number"),
            _col("yield_variance_pct", "Yield variance %", "percent"),
            _col("is_yield_flagged", "Yield flagged", "bool"),
            _col("cost_per_packet_paise", "Cost/packet (paise)", "number"),
        ],
        "rows": rows,
        "totals": _totals(rows, ["planned_qty_base", "actual_qty_base", "damaged_qty_base", "wastage_packets"], row_count=len(rows)),
    }


# ---------------------------------------------------------------------------
# 7. collections_outstanding
# ---------------------------------------------------------------------------

@register("collections_outstanding", "Collections & Outstanding", "all", "Payments received and receivables ageing by customer.")
def collections_outstanding(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    payments = db.scalars(select(Payment).where(Payment.status == PaymentStatus.POSTED)).all()
    paid_by_customer: dict[int, int] = {}
    payment_rows = 0
    for p in payments:
        if not in_period(p.payment_date, from_date, to_date):
            continue
        paid_by_customer[p.customer_id] = paid_by_customer.get(p.customer_id, 0) + int(p.amount_paise)
        payment_rows += 1

    ageing = receivables_service.get_receivables_ageing(db=db, as_of=ist_day_end_utc(as_of) if as_of else None)
    rows: list[dict[str, Any]] = []
    for c in ageing.customers:
        rows.append({
            "customer": c.customer_name,
            "payments_paise": paid_by_customer.get(c.customer_id, 0),
            "bucket_0_30_paise": int(c.bucket_0_30_paise),
            "bucket_31_60_paise": int(c.bucket_31_60_paise),
            "bucket_61_90_paise": int(c.bucket_61_90_paise),
            "bucket_90_plus_paise": int(c.bucket_90_plus_paise),
            "gross_outstanding_paise": int(c.gross_outstanding_paise),
            "unallocated_advance_paise": int(c.unallocated_advance_paise),
            "total_outstanding_paise": int(c.total_outstanding_paise),
        })
    # Customers with payments but no open invoices.
    seen = {c.customer_name for c in ageing.customers}
    for cust_id, paid in paid_by_customer.items():
        pass

    money_keys = ["payments_paise", "bucket_0_30_paise", "bucket_31_60_paise", "bucket_61_90_paise", "bucket_90_plus_paise", "gross_outstanding_paise", "unallocated_advance_paise", "total_outstanding_paise"]
    return {
        "name": "collections_outstanding",
        "title": "Collections & Outstanding",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None, "as_of": as_of.isoformat() if as_of else None},
        "columns": [
            _col("customer", "Customer", "string"),
            _col("payments_paise", "Payments received", "money_paise"),
            _col("bucket_0_30_paise", "0–30 days", "money_paise"),
            _col("bucket_31_60_paise", "31–60 days", "money_paise"),
            _col("bucket_61_90_paise", "61–90 days", "money_paise"),
            _col("bucket_90_plus_paise", "90+ days", "money_paise"),
            _col("gross_outstanding_paise", "Gross outstanding", "money_paise"),
            _col("unallocated_advance_paise", "Advance", "money_paise"),
            _col("total_outstanding_paise", "Total outstanding", "money_paise"),
        ],
        "rows": rows,
        "totals": {**_totals(rows, money_keys, customer_count=len(rows)), "payment_count": payment_rows},
    }


# ---------------------------------------------------------------------------
# 8. sales_by_customer_product
# ---------------------------------------------------------------------------

@register("sales_by_customer_product", "Sales by Customer & Product", "all", "Net sales per customer per product.")
def sales_by_customer_product(db: Session, from_date: Optional[date], to_date: Optional[date], as_of: Optional[date]) -> ReportResult:
    invoices = db.scalars(select(Invoice).where(Invoice.status == InvoiceStatus.POSTED)).all()
    invoices = [i for i in invoices if in_period(i.invoice_date, from_date, to_date)]

    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for inv in invoices:
        for line in inv.lines:
            key = (inv.buyer_name, line.description)
            a = agg.setdefault(key, {
                "customer": key[0], "product": key[1],
                "quantity_packets": 0, "taxable_paise": 0, "cgst_paise": 0, "sgst_paise": 0, "igst_paise": 0, "total_paise": 0,
            })
            a["quantity_packets"] += int(line.quantity_packets)
            a["taxable_paise"] += int(line.taxable_paise)
            a["cgst_paise"] += int(line.cgst_paise)
            a["sgst_paise"] += int(line.sgst_paise)
            a["igst_paise"] += int(line.igst_paise)
            a["total_paise"] += int(line.line_total_paise)

    rows = sorted(agg.values(), key=lambda r: (r["customer"], r["product"]))
    return {
        "name": "sales_by_customer_product",
        "title": "Sales by Customer & Product",
        "filters": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "columns": [
            _col("customer", "Customer", "string"),
            _col("product", "Product", "string"),
            _col("quantity_packets", "Packets", "number"),
            _col("taxable_paise", "Taxable", "money_paise"),
            _col("cgst_paise", "CGST", "money_paise"),
            _col("sgst_paise", "SGST", "money_paise"),
            _col("igst_paise", "IGST", "money_paise"),
            _col("total_paise", "Total", "money_paise"),
        ],
        "rows": rows,
        "totals": _totals(rows, ["quantity_packets", "taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise"], row_count=len(rows)),
    }
