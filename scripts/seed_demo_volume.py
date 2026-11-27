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
from app.models.customer import Customer, CustomerType
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus, Dispatch, DispatchStatus
from app.models.item import Item
from app.models.order import Order, OrderLine, OrderStatus
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.user import User, UserRole
from scripts.seed import run_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_volume")


def seed_demo_volume(db: Session) -> None:
    # 1. Ensure benchmark seed exists first
    run_seed(db)

    salesman_a = db.scalar(select(User).where(User.email == "salesman.a@foodmfr.local"))
    salesman_b = db.scalar(select(User).where(User.email == "salesman.b@foodmfr.local"))
    admin = db.scalar(select(User).where(User.email == "admin@foodmfr.local"))
    product = db.scalar(select(Product).join(Item).where(Item.name == "Murukku 200 g"))

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
    order_idx = 100
    for day_offset in range(0, 28, 2):
        inv_dt = base_date + timedelta(days=day_offset, hours=10)
        cust = cust_objs[day_offset % len(cust_objs)]
        pkts = 40 + (day_offset * 5) % 80
        taxable_paise = pkts * 5000
        is_interstate = (cust.state_code != "33")
        gst_rate = 500
        gst_paise = (taxable_paise * gst_rate) // 10000
        grand_total = taxable_paise + gst_paise

        inv_no = f"INV-VOL-{order_idx:04d}"
        existing_inv = db.scalar(select(Invoice).where(Invoice.invoice_no == inv_no))
        if not existing_inv:
            order_idx += 1
            ord_obj = Order(
                order_no=f"ORD-VOL-{order_idx:04d}",
                client_uuid=f"uuid-vol-{order_idx}",
                customer_id=cust.id,
                salesman_id=cust.assigned_salesman_id,
                order_date=inv_dt,
                status=OrderStatus.DISPATCHED,
                total_amount_paise=grand_total,
            )
            db.add(ord_obj)
            db.flush()

            cgst_paise = 0 if is_interstate else gst_paise // 2
            sgst_paise = 0 if is_interstate else gst_paise // 2
            igst_paise = gst_paise if is_interstate else 0

            inv_obj = Invoice(
                invoice_no=inv_no,
                order_id=ord_obj.id,
                customer_id=cust.id,
                financial_year="2026-2027",
                invoice_date=inv_dt,
                status=InvoiceStatus.POSTED,
                taxable_total_paise=taxable_paise,
                cgst_rate_bp=0 if is_interstate else 250,
                cgst_paise=cgst_paise,
                sgst_rate_bp=0 if is_interstate else 250,
                sgst_paise=sgst_paise,
                igst_rate_bp=500 if is_interstate else 0,
                igst_paise=igst_paise,
                grand_total_paise=grand_total,
                amount_paid_paise=grand_total // 2,
                balance_due_paise=grand_total - (grand_total // 2),
            )
            db.add(inv_obj)
            db.flush()

    db.commit()
    logger.info("Successfully seeded high-volume demo records for multi-week dashboard analysis.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_demo_volume(db)
    finally:
        db.close()
