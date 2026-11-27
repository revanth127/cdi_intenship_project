#!/usr/bin/env python3
"""Apply the Section 5 transactions to the seeded master-data database."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.customer import Customer
from app.models.item import Item
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from scripts.seed import run_seed, seed_benchmark_transactions


def main() -> None:
    db = SessionLocal()
    try:
        run_seed(db)
        users = {
            user.email: user
            for user in db.scalars(select(User)).all()
        }
        items = {
            item.name: item
            for item in db.scalars(select(Item)).all()
        }
        product = db.scalar(select(Product).where(Product.pack_name == "Murukku 200 g"))
        customers = db.scalars(
            select(Customer).where(
                Customer.gstin.in_(["33AAAAA0000A1Z5", "29BBBBB1111B1Z2"])
            ).order_by(Customer.id)
        ).all()
        supplier = db.scalar(select(Supplier).where(Supplier.gstin == "33AAAAA1111A1Z1"))
        if product is None or len(customers) != 2 or supplier is None:
            raise RuntimeError("Seeded master data is incomplete; run the default seed first.")
        seed_benchmark_transactions(db, users, items, product, customers, supplier)
        db.commit()
        print("Section 5 demo transactions applied.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
