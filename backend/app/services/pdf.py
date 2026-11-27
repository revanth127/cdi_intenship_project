from datetime import datetime
from decimal import Decimal
import io
from typing import Any, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.invoice import CreditNote, Invoice
from app.utils.indian_numbers import amount_in_words


def paise_to_rs_str(paise: int) -> str:
    """Formats integer paise as Indian Rupee string e.g. 750000 -> 7,500.00."""
    rs = Decimal(paise) / Decimal(100)
    return f"{rs:,.2f}"


def generate_invoice_pdf(doc: Union[Invoice, CreditNote]) -> bytes:
    """
    Generates a professional GST Tax Invoice or Credit Note PDF using ReportLab.
    Features:
      - Clean corporate layout compliant with Indian GST invoice format rules
      - Seller and Buyer snapshot details including GSTIN, state codes, and address
      - Intra-state (CGST + SGST) vs Inter-state (IGST) column layout
      - Summary breakdown with round-off and integer paise conversion
      - Grand total in Indian words ('Rupees ... Only')
      - Computer-generated document compliance disclaimer
    """
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
        pageCompression=0,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        alignment=1,  # Center
        textColor=colors.HexColor("#1A365D"),
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#4A5568"),
    )
    bold_style = ParagraphStyle(
        "BoldText",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2D3748"),
    )
    normal_style = ParagraphStyle(
        "RegularText",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2D3748"),
    )
    small_style = ParagraphStyle(
        "SmallText",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#718096"),
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        alignment=1,
        textColor=colors.whitesmoke,
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#2D3748"),
    )
    table_cell_right = ParagraphStyle(
        "TableCellRight",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=2,  # Right
        textColor=colors.HexColor("#2D3748"),
    )

    story = []

    # 1. Document Title
    is_credit_note = isinstance(doc, CreditNote)
    title_text = "TAX CREDIT NOTE" if is_credit_note else "TAX INVOICE"
    story.append(Paragraph(title_text, title_style))
    story.append(Paragraph("(Issued under Section 31 of CGST Act, 2017)", subtitle_style))
    story.append(Spacer(1, 10))

    # 2. Header Information (Document Number & Date)
    doc_no = doc.credit_note_no if is_credit_note else doc.invoice_no
    doc_date = (doc.credit_note_date if is_credit_note else doc.invoice_date).strftime("%d-%b-%Y")
    fy = doc.financial_year

    meta_data = [
        [
            Paragraph(f"<b>{'Credit Note No' if is_credit_note else 'Invoice No'}:</b> {doc_no}", normal_style),
            Paragraph(f"<b>Date:</b> {doc_date}", normal_style),
            Paragraph(f"<b>Financial Year:</b> {fy}", normal_style),
        ]
    ]
    if is_credit_note and getattr(doc, "invoice", None):
        orig_inv = doc.invoice
        meta_data.append([
            Paragraph(f"<b>Original Inv No:</b> {orig_inv.invoice_no}", normal_style),
            Paragraph(f"<b>Original Inv Date:</b> {orig_inv.invoice_date.strftime('%d-%b-%Y')}", normal_style),
            Paragraph(f"<b>Reason:</b> {doc.reason}", normal_style),
        ])
    meta_table = Table(meta_data, colWidths=[200, 150, 185])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDF2F7")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Seller and Buyer Snapshot Block
    seller_buyer_data = [
        [
            Paragraph("<b>DETAILS OF SELLER / SUPPLIER</b>", bold_style),
            Paragraph("<b>DETAILS OF BUYER / RECIPIENT</b>", bold_style),
        ],
        [
            Paragraph(
                f"<b>{doc.seller_name}</b><br/>"
                f"{doc.seller_address}<br/>"
                f"<b>GSTIN:</b> {doc.seller_gstin}<br/>"
                f"<b>State:</b> Code {doc.seller_state_code}",
                normal_style,
            ),
            Paragraph(
                f"<b>{doc.buyer_name}</b><br/>"
                f"{doc.buyer_address}<br/>"
                f"<b>GSTIN:</b> {doc.buyer_gstin or 'URP (Unregistered)'}<br/>"
                f"<b>State:</b> Code {doc.buyer_state_code}<br/>"
                f"<b>Place of Supply:</b> State Code {doc.place_of_supply_state_code}",
                normal_style,
            ),
        ],
    ]
    parties_table = Table(seller_buyer_data, colWidths=[267, 268])
    parties_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 12))

    # 4. Itemized Lines Table
    is_intra = not doc.is_igst

    if is_intra:
        headers = [
            Paragraph("#", table_header_style),
            Paragraph("Item Description", table_header_style),
            Paragraph("HSN", table_header_style),
            Paragraph("Qty", table_header_style),
            Paragraph("Rate (₹)", table_header_style),
            Paragraph("Taxable (₹)", table_header_style),
            Paragraph("CGST (₹)", table_header_style),
            Paragraph("SGST (₹)", table_header_style),
            Paragraph("Total (₹)", table_header_style),
        ]
        col_widths = [20, 130, 45, 35, 55, 65, 60, 60, 65]
    else:
        headers = [
            Paragraph("#", table_header_style),
            Paragraph("Item Description", table_header_style),
            Paragraph("HSN", table_header_style),
            Paragraph("Qty", table_header_style),
            Paragraph("Rate (₹)", table_header_style),
            Paragraph("Taxable (₹)", table_header_style),
            Paragraph("IGST (₹)", table_header_style),
            Paragraph("Total (₹)", table_header_style),
        ]
        col_widths = [25, 170, 50, 40, 60, 65, 65, 60]

    table_data = [headers]

    for idx, line in enumerate(doc.lines, start=1):
        if is_intra:
            half_pct = f"{(line.gst_rate_bp / 200):g}%"
            cgst_desc = f"{paise_to_rs_str(line.cgst_paise)}<br/><font size=6 color='#718096'>({half_pct})</font>"
            sgst_desc = f"{paise_to_rs_str(line.sgst_paise)}<br/><font size=6 color='#718096'>({half_pct})</font>"
            row = [
                Paragraph(str(idx), table_cell_style),
                Paragraph(line.description, table_cell_style),
                Paragraph(line.hsn_code, table_cell_style),
                Paragraph(str(line.quantity_packets), table_cell_right),
                Paragraph(paise_to_rs_str(line.unit_price_paise), table_cell_right),
                Paragraph(paise_to_rs_str(line.taxable_paise), table_cell_right),
                Paragraph(cgst_desc, table_cell_right),
                Paragraph(sgst_desc, table_cell_right),
                Paragraph(paise_to_rs_str(line.line_total_paise), table_cell_right),
            ]
        else:
            full_pct = f"{(line.gst_rate_bp / 100):g}%"
            igst_desc = f"{paise_to_rs_str(line.igst_paise)}<br/><font size=6 color='#718096'>({full_pct})</font>"
            row = [
                Paragraph(str(idx), table_cell_style),
                Paragraph(line.description, table_cell_style),
                Paragraph(line.hsn_code, table_cell_style),
                Paragraph(str(line.quantity_packets), table_cell_right),
                Paragraph(paise_to_rs_str(line.unit_price_paise), table_cell_right),
                Paragraph(paise_to_rs_str(line.taxable_paise), table_cell_right),
                Paragraph(igst_desc, table_cell_right),
                Paragraph(paise_to_rs_str(line.line_total_paise), table_cell_right),
            ]
        table_data.append(row)

    lines_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    lines_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    story.append(lines_table)
    story.append(Spacer(1, 10))

    # 5. Financial Totals & Summary Block
    summary_data = [
        [Paragraph("<b>Taxable Value:</b>", normal_style), Paragraph(f"₹ {paise_to_rs_str(doc.taxable_total_paise)}", table_cell_right)],
    ]
    if is_intra:
        summary_data.append([
            Paragraph("<b>Central GST (CGST):</b>", normal_style),
            Paragraph(f"₹ {paise_to_rs_str(doc.cgst_total_paise)}", table_cell_right),
        ])
        summary_data.append([
            Paragraph("<b>State GST (SGST):</b>", normal_style),
            Paragraph(f"₹ {paise_to_rs_str(doc.sgst_total_paise)}", table_cell_right),
        ])
    else:
        summary_data.append([
            Paragraph("<b>Integrated GST (IGST):</b>", normal_style),
            Paragraph(f"₹ {paise_to_rs_str(doc.igst_total_paise)}", table_cell_right),
        ])

    if doc.round_off_paise != 0:
        summary_data.append([
            Paragraph("<b>Round Off:</b>", normal_style),
            Paragraph(f"₹ {paise_to_rs_str(doc.round_off_paise)}", table_cell_right),
        ])

    summary_data.append([
        Paragraph("<b>Grand Total:</b>", bold_style),
        Paragraph(f"<b>₹ {paise_to_rs_str(doc.grand_total_paise)}</b>", table_cell_right),
    ])

    summary_table = Table(summary_data, colWidths=[135, 115])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EDF2F7")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # Amount in words paragraph
    words_text = amount_in_words(doc.grand_total_paise, paise_input=True)
    words_para = Paragraph(f"<b>Amount in Words:</b><br/>{words_text}", normal_style)

    totals_layout = Table(
        [[words_para, summary_table]],
        colWidths=[285, 250],
    )
    totals_layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_layout)
    story.append(Spacer(1, 20))

    # 6. Legal Footer & Computer Generated Disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#A0AEC0"), spaceAfter=8))
    story.append(Paragraph(
        "<b>Terms & Conditions:</b> Goods once sold will not be taken back without valid credit authorization. "
        "Subject to local jurisdiction.",
        small_style,
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>This is a computer generated invoice</b> and does not require a physical signature.",
        ParagraphStyle("Disclaimer", parent=small_style, alignment=1, textColor=colors.HexColor("#4A5568")),
    ))

    pdf.build(story)
    return buffer.getvalue()
