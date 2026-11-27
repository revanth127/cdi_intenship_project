#!/usr/bin/env python3
"""
Section 5 Production & Financial Benchmark Verification Script.
Validates all Section 5 expected vs actual metrics against the database.
Outputs a clean ASCII verification table with PASS / FAIL status.
"""
from decimal import Decimal
import os
import sys

# Ensure backend root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine
from app.models.company import CompanySettings
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.item import Item, ItemType
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.production import ProductionRun
from app.services.costing import product_cost_summary
from app.services.orders import available_to_promise
from app.services.receivables import invoice_outstanding
from app.services.stock import get_balance, get_current_unit_cost
from scripts.seed import run_seed


def format_currency_paise(paise: int) -> str:
    rupees = paise / 100.0
    return f"Rs {rupees:,.2f}"


def run_benchmark() -> bool:
    print("=" * 88)
    print(" ORDER-TO-AUDIT: SECTION 5 PRODUCTION & FINANCIAL BENCHMARK VERIFICATION")
    print("=" * 88)

    db: Session = SessionLocal()
    try:
        # Ensure database is seeded with benchmark data
        run_seed(db)

        # 1. Fetch benchmark items
        flour = db.scalar(select(Item).where(Item.name == "Flour"))
        oil = db.scalar(select(Item).where(Item.name == "Cooking oil"))
        spice = db.scalar(select(Item).where(Item.name == "Salt and spice mix"))
        pouch = db.scalar(select(Item).where(Item.name == "200 g pouch"))
        carton = db.scalar(select(Item).where(Item.name == "Carton"))
        murukku_item = db.scalar(select(Item).where(Item.name == "Murukku 200 g"))

        product = db.scalar(select(Product).where(Product.item_id == murukku_item.id))
        run = db.scalar(select(ProductionRun).where(ProductionRun.run_no == "PR-2026-0001"))
        retailer_a = db.scalar(select(Customer).where(Customer.gstin == "33AAAAA0000A1Z5"))
        distributor_b = db.scalar(select(Customer).where(Customer.gstin == "29BBBBB1111B1Z2"))

        # Balances
        flour_bal_kg = get_balance(db, flour.id) / 1000.0
        oil_bal_L = get_balance(db, oil.id) / 1000.0
        spice_bal_kg = get_balance(db, spice.id) / 1000.0
        pouch_bal = get_balance(db, pouch.id)
        carton_bal = get_balance(db, carton.id)
        murukku_fg_bal = get_balance(db, murukku_item.id)

        # Unit costs & variances
        flour_wac = get_current_unit_cost(db, flour.id)

        lines_by_item = {l.item_id: l for l in run.lines} if run else {}
        oil_line = lines_by_item.get(oil.id)
        pouch_line = lines_by_item.get(pouch.id)
        carton_line = lines_by_item.get(carton.id)

        oil_var = float(oil_line.variance_pct) if oil_line and oil_line.variance_pct is not None else 0.0
        oil_flagged = oil_line.is_flagged if oil_line else False

        pouch_var = float(pouch_line.variance_pct) if pouch_line and pouch_line.variance_pct is not None else 0.0
        pouch_flagged = pouch_line.is_flagged if pouch_line else False

        carton_var = float(carton_line.variance_pct) if carton_line and carton_line.variance_pct is not None else 0.0
        carton_flagged = carton_line.is_flagged if carton_line else False

        yield_var = float(run.yield_variance_pct) if run and run.yield_variance_pct is not None else 0.0
        yield_flagged = run.is_yield_flagged if run else False

        cost_summary = product_cost_summary(db, product.id)
        cost_per_pkt = float(cost_summary.cost_per_packet)
        margin_pct = float(cost_summary.margin_pct)

        # Receivables Retailer A
        ret_a_inv = db.scalar(
            select(Invoice).where(
                Invoice.customer_id == retailer_a.id,
                Invoice.status == InvoiceStatus.POSTED,
            )
        )
        ret_a_outstanding_paise = invoice_outstanding(db, ret_a_inv) if ret_a_inv else 0

        # ATP Distributor B
        atp_b = available_to_promise(db, product.id)
        dist_b_order = db.scalar(
            select(Order).where(
                Order.customer_id == distributor_b.id,
                Order.status == OrderStatus.SUBMITTED,
            )
        )
        dist_b_req = dist_b_order.lines[0].quantity_packets if dist_b_order and dist_b_order.lines else 120
        dist_b_shortage = max(0, dist_b_req - atp_b["available"])

        checks = [
            ("Flour post-purchase WAC", "4.312500 paise/g", f"{flour_wac:.6f} paise/g", flour_wac == Decimal("4.312500")),
            ("Flour post-run inventory", "120.0 kg", f"{flour_bal_kg:.1f} kg", flour_bal_kg == 120.0),
            ("Cooking oil post-run inventory", "19.5 L", f"{oil_bal_L:.1f} L", oil_bal_L == 19.5),
            ("Spice mix post-run inventory", "3.8 kg", f"{spice_bal_kg:.1f} kg", spice_bal_kg == 3.8),
            ("200 g pouch post-run inventory", "306 pieces", f"{pouch_bal} pieces", pouch_bal == 306),
            ("Carton post-run inventory", "21 pieces", f"{carton_bal} pieces", carton_bal == 21),
            ("Murukku 200 g FG stock (after dispatch)", "88 packets", f"{murukku_fg_bal} packets", murukku_fg_bal == 88),
            ("Production good packets output", "188 packets", f"{run.actual_good_packets} packets", run.actual_good_packets == 188),
            ("Oil variance (flagged > 3%)", "+5.00% (Flagged)", f"{oil_var:+.2f}% ({'Flagged' if oil_flagged else 'Not flagged'})", oil_var == 5.0 and oil_flagged),
            ("Carton variance (flagged > 3%)", "-10.00% (Flagged)", f"{carton_var:+.2f}% ({'Flagged' if carton_flagged else 'Not flagged'})", carton_var == -10.0 and carton_flagged),
            ("Pouch variance (strict > 3% rule)", "-3.00% (Not flagged)", f"{pouch_var:+.2f}% ({'Flagged' if pouch_flagged else 'Not flagged'})", pouch_var == -3.0 and not pouch_flagged),
            ("Yield variance (flagged > 3%)", "-6.00% (Flagged)", f"{yield_var:+.2f}% ({'Flagged' if yield_flagged else 'Not flagged'})", yield_var == -6.0 and yield_flagged),
            ("Run material cost", "Rs 4,055.00", format_currency_paise(run.total_material_cost_paise or 0), run.total_material_cost_paise == 405500),
            ("Direct overheads (Labour + Gas)", "Rs 1,800.00", format_currency_paise(cost_summary.total_overheads_paise), cost_summary.total_overheads_paise == 180000),
            ("Total run cost", "Rs 5,855.00", format_currency_paise(cost_summary.total_cost_paise), cost_summary.total_cost_paise == 585500),
            ("Cost per packet (Weighted Average)", "Rs 31.14", f"Rs {cost_per_pkt:.2f}", cost_per_pkt == 31.14),
            ("Selling price per packet", "Rs 50.00", f"Rs {cost_summary.selling_price:.2f}", float(cost_summary.selling_price) == 50.00),
            ("Gross commercial margin %", "37.7%", f"{margin_pct:.1f}%", margin_pct == 37.7),
            ("Retailer A invoice total (150 pkts + 5% GST)", "Rs 7,875.00", format_currency_paise(ret_a_inv.grand_total_paise if ret_a_inv else 0), ret_a_inv and ret_a_inv.grand_total_paise == 787500),
            ("Retailer A outstanding balance (after Rs 4k pay)", "Rs 3,875.00", format_currency_paise(ret_a_outstanding_paise), ret_a_outstanding_paise == 387500),
            ("Distributor B order shortage", "Short by 32 packets", f"Short by {dist_b_shortage} packets", dist_b_shortage == 32),
        ]

        print(f"\n{'CHECK METRIC':<46} | {'EXPECTED':<20} | {'ACTUAL':<22} | {'STATUS'}")
        print("-" * 102)
        all_passed = True
        for name, exp, act, passed in checks:
            status_str = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"{name:<46} | {exp:<20} | {act:<22} | {status_str}")

        print("=" * 102)

        # Costing & FIFO Comparison
        fifo_flour_cost = 40 * 42.0  # Rs 1,680.00
        fifo_mat_cost = fifo_flour_cost + 1470.0 + 240.0 + 485.0 + 135.0  # Rs 4,010.00
        fifo_total_cost = fifo_mat_cost + 1800.0  # Rs 5,810.00
        fifo_unit_cost = fifo_total_cost / 188.0  # Rs 30.9042... -> Rs 30.90

        print("\nVALUATION METHOD & COSTING ANALYSIS:")
        print(f"  1. Moving Weighted Average Cost per Packet: Rs {cost_per_pkt:.2f}")
        print(f"     Method: All material issues recorded at moving weighted average cost at time of issue.")
        print(f"  2. Overhead Rule: All shift overheads (Labour Rs 1,200 + Gas Rs 600 = Rs 1,800)")
        print(f"     are divided strictly across good finished packets produced ({run.actual_good_packets} pkts),")
        print(f"     so good output absorbs all production costs and scrap/damaged packets carry zero inventory value.")
        print(f"  3. FIFO Alternative Comparison: Rs {fifo_unit_cost:.2f} per packet")
        print(f"     Difference: FIFO consumes earlier Rs 42/kg flour lot (Rs 1,680 vs Rs 1,725),")
        print(f"     yielding Rs {cost_per_pkt - fifo_unit_cost:.2f}/packet lower recorded cost.")
        print(f"     Moving Weighted Average was chosen because bulk flour and oil are co-mingled in storage,")
        print(f"     and weighted average prevents artificial batch margin volatility.")
        print("=" * 102)

        if all_passed:
            print("\nALL SECTION 5 BENCHMARK CHECKS PASSED!\n")
        else:
            print("\nSOME BENCHMARK CHECKS FAILED!\n")

        return all_passed
    finally:
        db.close()


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
