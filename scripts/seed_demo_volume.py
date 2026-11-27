#!/usr/bin/env python3
"""
Optional High-Volume Demo Seeding Script.
Does NOT run by default. Use this command when demonstrating full dashboard volume
with multi-week sales charts, multiple active debtors, and larger customer networks.

Usage:
  python3 scripts/seed_demo_volume.py
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.company import CompanySettings
from app.models.customer import Customer, CustomerType
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.item import Item
from app.models.order import Order, OrderLine, OrderStatus
from app.models.product import Product
from app.models.user import User
from app.services.invoicing import get_next_invoice_number
from app.services.orders import get_next_order_number
from scripts.seed import run_seed
from app.utils.gst import compute_line_tax, is_intra_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_volume")


def seed_demo_volume(db: Session) -> None:
    # 1. Ensure benchmark seed exists first
    run_seed(db)

    salesman_a = db.scalar(select(User).where(User.email == "salesman.a@foodmfr.local"))
    salesman_b = db.scalar(select(User).where(User.email == "salesman.b@foodmfr.local"))
    admin = db.scalar(select(User).where(User.email == "admin@foodmfr.local"))
    product = db.scalar(select(Product).join(Item).where(Item.name == "Murukku 200 g"))
    company = db.scalar(select(CompanySettings).where(CompanySettings.id == 1))
    if not company or not product or not salesman_a or not salesman_b or not admin:
        raise RuntimeError("The benchmark seed did not create the required company, product, or demo users.")
    item = product.item

    # 2. Add extra customers
    extra_customers = [
        {"name": "Annapoorna Sweets & Snacks", "gstin": "33AACCA2222A1Z3", "state_code": "33", "type": CustomerType.RETAILER, "salesman": salesman_a},
        {"name": "Murugan Supermarket", "gstin": "33AABBM3333M1Z9", "state_code": "33", "type": CustomerType.RETAILER, "salesman": salesman_a},
        {"name": "Krishna Department Stores", "gstin": "33AAKKK4444K1Z4", "state_code": "33", "type": CustomerType.RETAILER, "salesman": salesman_a},
        {"name": "Saravana Wholesale Agencies", "gstin": "29AABBS5555S1Z1", "state_code": "29", "type": CustomerType.DISTRIBUTOR, "salesman": salesman_b},
    ]

    cust_objs = []
    for c_data in extra_customers:
        cust = db.scalar(select(Customer).where(Customer.gstin == c_data["gstin"]))
        if not cust:
            cust = Customer(
                name=c_data["name"],
                gstin=c_data["gstin"],
                customer_type=c_data["type"],
                state_code=c_data["state_code"],
                address="Commercial Street, South India",
                phone="+91 98400 55667",
                assigned_salesman_id=c_data["salesman"].id,
                is_active=True,
            )
            db.add(cust)
            db.flush()
        cust_objs.append(cust)

    now = datetime.now(timezone.utc)
    base_date = now - timedelta(days=28)

    # 3. Create historical daily sales across 28 days for rich sales trend
    for day_offset in range(0, 28, 2):
        inv_dt = base_date + timedelta(days=day_offset, hours=10)
        cust = cust_objs[day_offset % len(cust_objs)]
        pkts = 40 + (day_offset * 5) % 80
        taxable_paise = pkts * 5000
        client_uuid = f"demo-volume-{day_offset:02d}"
        if db.scalar(select(Order).where(Order.client_uuid == client_uuid)):
            continue

        intra_state = is_intra_state(company.state_code, cust.state_code)
        cgst_paise, sgst_paise, igst_paise = compute_line_tax(
            taxable_paise, item.gst_rate_bp, intra_state
        )
        grand_total = taxable_paise + cgst_paise + sgst_paise + igst_paise
        order_no = get_next_order_number(db, inv_dt)
        order = Order(
            order_no=order_no,
            client_uuid=client_uuid,
            customer_id=cust.id,
            salesman_id=cust.assigned_salesman_id,
            order_date=inv_dt,
            status=OrderStatus.INVOICED,
            total_amount_paise=grand_total,
        )
        order.lines.append(
            OrderLine(
                product_id=product.id,
                quantity_packets=pkts,
                unit_price_paise=5000,
                line_total_paise=taxable_paise,
            )
        )
        db.add(order)
        db.flush()

        invoice_no, financial_year = get_next_invoice_number(db, inv_dt)
        invoice = Invoice(
            invoice_no=invoice_no,
            financial_year=financial_year,
            invoice_date=inv_dt,
            order_id=order.id,
            customer_id=cust.id,
            status=InvoiceStatus.POSTED,
            seller_name=company.company_name,
            seller_gstin=company.gstin,
            seller_address=company.address,
            seller_state_code=company.state_code,
            buyer_name=cust.name,
            buyer_gstin=cust.gstin,
            buyer_address=cust.address,
            buyer_state_code=cust.state_code,
            place_of_supply_state_code=cust.state_code,
            is_igst=not intra_state,
            taxable_total_paise=taxable_paise,
            cgst_total_paise=cgst_paise,
            sgst_total_paise=sgst_paise,
            igst_total_paise=igst_paise,
            round_off_paise=0,
            grand_total_paise=grand_total,
            created_by=admin.id,
        )
        invoice.lines.append(
            InvoiceLine(
                product_id=product.id,
                description=item.name,
                hsn_code=item.hsn_code or "1905",
                quantity_packets=pkts,
                unit_price_paise=5000,
                taxable_paise=taxable_paise,
                gst_rate_bp=item.gst_rate_bp,
                cgst_paise=cgst_paise,
                sgst_paise=sgst_paise,
                igst_paise=igst_paise,
                line_total_paise=grand_total,
            )
        )
        db.add(invoice)

    db.commit()
    logger.info("Successfully seeded high-volume demo records for multi-week dashboard analysis.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_demo_volume(db)
    finally:
        db.close()
