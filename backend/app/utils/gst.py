from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable


def is_intra_state(company_state_code: str, customer_state_code: str) -> bool:
    """
    Determines whether a transaction is intra-state (within the same state)
    or inter-state (between different states).
    Compares 2-digit GST state codes (e.g. '33' for Tamil Nadu).
    """
    if not company_state_code or not customer_state_code:
        return False
    return str(company_state_code).strip() == str(customer_state_code).strip()


def compute_line_tax(taxable_paise: int, gst_rate_bp: int, intra_state: bool) -> tuple[int, int, int]:
    """
    Pure function computing CGST, SGST, and IGST for a line item in integer paise.

    Rules:
      - Intra-state splits the rate in half for CGST and SGST.
        Each component is computed and rounded on its own half-rate using ROUND_HALF_UP.
      - Inter-state applies the full rate to IGST (ROUND_HALF_UP).
      - Rates are in basis points (1 bp = 0.01%, 500 bp = 5.00%).

    Returns:
      (cgst_paise, sgst_paise, igst_paise) as integers.
    """
    if taxable_paise < 0:
        raise ValueError("taxable_paise cannot be negative")
    if gst_rate_bp < 0:
        raise ValueError("gst_rate_bp cannot be negative")

    if taxable_paise == 0 or gst_rate_bp == 0:
        return 0, 0, 0

    taxable_dec = Decimal(taxable_paise)

    if intra_state:
        # Half rate for CGST and SGST: (gst_rate_bp / 2) / 10000 = gst_rate_bp / 20000
        half_rate = Decimal(gst_rate_bp) / Decimal("20000")
        cgst = int((taxable_dec * half_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        sgst = int((taxable_dec * half_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        igst = 0
        return cgst, sgst, igst
    else:
        # Full rate for IGST: gst_rate_bp / 10000
        full_rate = Decimal(gst_rate_bp) / Decimal("10000")
        igst = int((taxable_dec * full_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return 0, 0, igst


def compute_order_tax_summary(
    lines: Iterable[Any],
    company_state_code: str,
    customer_state_code: str,
) -> dict[str, int | bool]:
    """
    Computes aggregated taxable value, tax components, and grand total for an order.
    Each line item specifies taxable_paise and gst_rate_bp.
    """
    intra = is_intra_state(company_state_code, customer_state_code)
    taxable_total = 0
    total_cgst = 0
    total_sgst = 0
    total_igst = 0

    for line in lines:
        if isinstance(line, dict):
            amt = line.get("line_total_paise", 0)
            rate_bp = line.get("gst_rate_bp", 0)
        else:
            amt = getattr(line, "line_total_paise", 0)
            # gst_rate_bp might be on line or via product/item
            rate_bp = getattr(line, "gst_rate_bp", None)
            if rate_bp is None and hasattr(line, "product") and line.product and line.product.item:
                rate_bp = line.product.item.gst_rate_bp
            elif rate_bp is None:
                rate_bp = 0

        taxable_total += amt
        cgst, sgst, igst = compute_line_tax(amt, rate_bp, intra)
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst

    grand_total = taxable_total + total_cgst + total_sgst + total_igst

    return {
        "is_intra_state": intra,
        "taxable_amount_paise": taxable_total,
        "cgst_paise": total_cgst,
        "sgst_paise": total_sgst,
        "igst_paise": total_igst,
        "total_tax_paise": total_cgst + total_sgst + total_igst,
        "grand_total_paise": grand_total,
    }
