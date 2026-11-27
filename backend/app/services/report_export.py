"""Shared exporters rendering the SAME report result as JSON, CSV, XLSX, PDF.

Money is integer paise internally. CSV uses plain decimals (rupees for money
columns, no symbols/thousands separators). XLSX writes numeric cells with a
number format, a header row with freeze panes, autofilter, and a totals row.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any

from app.services.reports import money

# Column types
MONEY = "money_paise"
NUMBER = "number"
PERCENT = "percent"
BOOL = "bool"

MONEY_FMT = "0.00"
NUM_FMT = "#,##0.####"
PCT_FMT = "0.00"


def _scalar(column_type: str, value: Any) -> Any:
    """Render a single cell as a plain scalar for CSV/XLSX/PDF."""
    if value is None:
        return "" if column_type not in (MONEY, NUMBER, PERCENT) else 0
    if column_type == MONEY:
        try:
            return float(money(int(Decimal(str(value)))))
        except (ValueError, TypeError, ArithmeticError):
            return 0.0
    if column_type in (NUMBER, PERCENT):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bool):
            return int(value)
        try:
            return float(value) if isinstance(value, float) or "." in str(value) else int(value)
        except (ValueError, TypeError):
            return 0
    if column_type == BOOL:
        return "true" if value else "false"
    return value


def _numeric(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def totals_row(columns: list[dict], totals: dict) -> list[Any]:
    """Build a rendered totals row aligned to columns."""
    out: list[Any] = []
    first = True
    for col in columns:
        key = col["key"]
        if key in totals:
            out.append(_scalar(col["type"], totals[key]))
        elif first:
            out.append("TOTAL")
        else:
            out.append("")
        first = False
    return out


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(report: dict) -> dict:
    return {
        "name": report["name"],
        "title": report["title"],
        "filters": report.get("filters", {}),
        "columns": report["columns"],
        "rows": report["rows"],
        "totals": {k: _numeric(v) for k, v in report["totals"].items()},
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def to_csv(report: dict) -> str:
    columns = report["columns"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([c["label"] for c in columns])
    for row in report["rows"]:
        writer.writerow([_csv_cell(c["type"], row.get(c["key"])) for c in columns])
    writer.writerow(_csv_totals_row(columns, report["totals"]))
    return buf.getvalue()


def _csv_cell(column_type: str, value: Any) -> Any:
    """CSV rendering: plain decimals for money (2dp), no symbols/thousands."""
    rendered = _scalar(column_type, value)
    if column_type == MONEY:
        try:
            return f"{Decimal(str(rendered)):.2f}"
        except Exception:
            return rendered
    if isinstance(rendered, float) and rendered.is_integer():
        return int(rendered)
    return rendered


def _csv_totals_row(columns: list[dict], totals: dict) -> list[Any]:
    """Totals row for CSV; money values are already rendered to decimal by totals_row."""
    out = totals_row(columns, totals)
    rendered: list[Any] = []
    for j, value in enumerate(out):
        col_type = columns[j]["type"] if j < len(columns) else "string"
        if col_type == MONEY and isinstance(value, (int, float)) and not isinstance(value, bool):
            rendered.append(f"{Decimal(str(value)):.2f}")
        elif isinstance(value, float) and value.is_integer():
            rendered.append(int(value))
        else:
            rendered.append(value)
    return rendered


# ---------------------------------------------------------------------------
# XLSX (openpyxl)
# ---------------------------------------------------------------------------

def to_xlsx(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    columns = report["columns"]
    wb = Workbook()
    ws = wb.active
    ws.title = (report["title"] or report["name"])[:31]

    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9D9D9")
    total_font = Font(bold=True)

    # Header row
    for j, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=j, value=col["label"])
        cell.font = header_font
        cell.fill = header_fill

    def write_cell(row_idx: int, col_idx: int, column_type: str, value: Any) -> None:
        rendered = _scalar(column_type, value)
        cell = ws.cell(row=row_idx, column=col_idx)
        if column_type in (MONEY, NUMBER, PERCENT) and rendered != "":
            try:
                cell.value = float(rendered)
                cell.number_format = MONEY_FMT if column_type == MONEY else (PCT_FMT if column_type == PERCENT else NUM_FMT)
            except (ValueError, TypeError):
                cell.value = rendered
        else:
            cell.value = rendered

    r = 2
    for row in report["rows"]:
        for j, col in enumerate(columns, start=1):
            write_cell(r, j, col["type"], row.get(col["key"]))
        r += 1

    # Totals row
    totals_rendered = totals_row(columns, report["totals"])
    total_row_idx = r
    for j, value in enumerate(totals_rendered, start=1):
        col_type = columns[j - 1]["type"]
        cell = ws.cell(row=total_row_idx, column=j)
        cell.font = total_font
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cell.value = value
            cell.number_format = MONEY_FMT if col_type == MONEY else NUM_FMT
        else:
            cell.value = value

    # Freeze header pane, autofilter over data range
    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(columns))
    last_data_row = total_row_idx - 1
    ws.auto_filter.ref = f"A1:{last_col}{max(last_data_row, 1)}"

    # Reasonable column widths
    for j, col in enumerate(columns, start=1):
        width = max(len(col["label"]) + 2, 12)
        for row in report["rows"][:200]:
            v = row.get(col["key"])
            if v is not None:
                width = max(width, min(len(str(v)) + 2, 48))
        ws.column_dimensions[get_column_letter(j)].width = width

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# PDF (reportlab)
# ---------------------------------------------------------------------------

def to_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    columns = report["columns"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()

    data = [[c["label"] for c in columns]]
    for row in report["rows"]:
        data.append([_pdf_text(_scalar(c["type"], row.get(c["key"]))) for c in columns])
    data.append([_pdf_text(v) for v in totals_row(columns, report["totals"])])

    n = len(columns)
    col_width = (doc.width) / n if n else doc.width
    table = Table(data, colWidths=[col_width] * n, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F0F0")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    # right-align numeric columns
    for j, col in enumerate(columns):
        if col["type"] in (MONEY, NUMBER, PERCENT):
            style.append(("ALIGN", (j, 1), (j, -1), "RIGHT"))
    table.setStyle(TableStyle(style))

    filters = report.get("filters", {})
    filter_txt = ", ".join(f"{k}={v}" for k, v in filters.items() if v) or "no period filter"
    story = [
        Paragraph(report["title"], styles["Title"]),
        Paragraph(f"Report: {report['name']} · {filter_txt}", styles["Normal"]),
        Spacer(1, 8),
        table,
    ]
    doc.build(story)
    return buf.getvalue()


def _pdf_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    s = str(value)
    # reportlab Helvetica cannot render all unicode; replace risky glyphs
    return s.replace("₹", "Rs ").replace("–", "-").replace("—", "-").replace("×", "x")


CONTENT_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
