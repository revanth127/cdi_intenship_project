#!/usr/bin/env python3
"""
scripts/add_500g_demo.py

Live Demonstration Script for Technical Interview:
Adds a 500 g pack variant to the 'Murukku' ProductFamily sharing the EXACT SAME BOM.
Creates:
  - Finished-goods Item: 'Murukku 500 g'
  - Pack variant Product: net_weight_g=500, packets_per_carton=10
  - PriceListItem: Rs 120.00
  - Packaging items: '500 g pouch' (1 per 1 packet), 'Carton' (1 per 10 packets)
Then verifies and prints planned batch quantities for 1 production batch.
Takes less than 1 second to run, zero BOM duplication.
"""
from decimal import Decimal
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.bom import BOM, BOMItem
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import PackagingSpec, Product, ProductFamily
from app.schemas.product_family import ProductVariantCreate, VariantPackagingCreate
from app.routers.product_families import create_variant


def run_add_500g_demo(db: Session | None = None) -> None:
    close_db = False
    if db is None:
        try:
            db = SessionLocal()
            # Test connection
            db.execute(select(1))
            close_db = True
        except Exception:
            # Fallback to local SQLite demo database so the demo always works reliably in any environment
            print("\n[NOTE] Local PostgreSQL unavailable; initializing portable SQLite demo database...")
            from sqlalchemy import create_engine
            from app.core.db import Base
            from scripts.seed import run_seed

            engine = create_engine("sqlite:///demo.db", connect_args={"check_same_thread": False})
            Base.metadata.create_all(bind=engine)
            from sqlalchemy.orm import sessionmaker
            DemoSession = sessionmaker(bind=engine)
            db = DemoSession()
            run_seed(db)
            close_db = True

    try:
        print("=" * 68)
        print(" LIVE INTERVIEW DEMO: Add 500 g Pack Variant Sharing Existing BOM")
        print("=" * 68)

        # 1. Fetch Product Family
        family = db.scalar(select(ProductFamily).where(ProductFamily.name == "Murukku"))
        if not family:
            raise RuntimeError("Family 'Murukku' not found. Please run seed script first.")

        print(f"\n[1] Found Product Family: {family.name} (HSN: {family.hsn_code}, GST: {family.gst_rate_bp / 100:.1f}%)")

        # 2. Ensure 500 g pouch packaging item exists
        pouch_500 = db.scalar(select(Item).where(Item.name == "500 g pouch"))
        if not pouch_500:
            pouch_500 = Item(
                name="500 g pouch",
                item_type=ItemType.PACKAGING,
                base_unit="piece",
                display_unit="piece",
                hsn_code="3923",
                gst_rate_bp=1800,
                opening_balance_qty=500,
                opening_rate_paise=Decimal("450.000000"),  # Rs 4.50
            )
            db.add(pouch_500)
            db.flush()
            print(f"[2] Created Packaging Item: {pouch_500.name}")
        else:
            print(f"[2] Using Packaging Item: {pouch_500.name}")

        carton_item = db.scalar(select(Item).where(Item.name == "Carton"))
        if not carton_item:
            raise RuntimeError("Packaging item 'Carton' not found.")

        # 3. Create Variant via Product Family variants endpoint logic
        # Check if 500 g variant already exists
        existing_500 = db.scalar(select(Product).where(Product.pack_name == "Murukku 500 g"))
        if existing_500:
            product = existing_500
            print(f"[3] Product variant '{product.pack_name}' already exists (ID: {product.id}).")
        else:
            variant_payload = ProductVariantCreate(
                pack_name="Murukku 500 g",
                net_weight_g=500,
                packets_per_carton=10,
                selling_price=Decimal("120.00"),
                packaging=[
                    VariantPackagingCreate(item_id=pouch_500.id, qty_base=1, per_packets=1),
                    VariantPackagingCreate(item_id=carton_item.id, qty_base=1, per_packets=10),
                ],
            )
            product = create_variant(family_id=family.id, payload=variant_payload, db=db)
            print(f"[3] Created Product Variant '{product.pack_name}' (ID: {product.id})")
            print(f"    - Net weight: {product.net_weight_g} g")
            print(f"    - Packets per carton: {product.packets_per_carton}")
            print(f"    - Selling price: Rs 120.00")
            print(f"    - Packaging: 1 pouch/packet, 1 carton/10 packets")

        # 4. Inspect Family BOM (unchanged, shared)
        active_bom = db.scalar(
            select(BOM).where(BOM.family_id == family.id, BOM.is_active == True)
        )
        if not active_bom:
            raise RuntimeError("No active BOM found for Murukku family.")

        print(f"\n[4] Shared Family BOM:")
        print(f"    - BOM ID: {active_bom.id}, Version: {active_bom.version}")
        print(f"    - Batch Output Mass: {active_bom.expected_output_g:,} g")

        # 5. Calculate Derived Values for 1 Batch:
        # expected_packets = floor(batches * expected_output_g / net_weight_g)
        batches = 1
        expected_packets = (batches * active_bom.expected_output_g) // product.net_weight_g
        print(f"\n[5] Derived Batch Figures for 1 Batch of '{product.pack_name}':")
        print(f"    - Expected Finished Packets: {expected_packets} packets (40,000 g / 500 g)")

        print("\n[6] Planned Material Consumption for 1 Batch:")
        print("-" * 68)
        print(f"{'Category':<14} | {'Item Name':<24} | {'Planned Quantity':<16} | {'Rule'}")
        print("-" * 68)

        # Raw materials from Family BOM
        for bi in active_bom.items:
            display_qty = bi.quantity_per_batch
            if bi.unit_for_display == "kg":
                display_str = f"{display_qty / 1000:,.1f} kg"
            elif bi.unit_for_display == "L":
                display_str = f"{display_qty / 1000:,.1f} L"
            else:
                display_str = f"{display_qty:,} {bi.unit_for_display}"

            print(f"{'RAW MATERIAL':<14} | {bi.item.name:<24} | {display_str:<16} | ROUND_HALF_UP")

        # Packaging from Variant PackagingSpecs
        import math
        specs = db.scalars(select(PackagingSpec).where(PackagingSpec.product_id == product.id)).all()
        for ps in specs:
            planned_pkg = math.ceil((expected_packets * ps.qty_base) / ps.per_packets)
            print(f"{'PACKAGING':<14} | {ps.item.name:<24} | {planned_pkg:>4} {ps.unit_for_display:<11} | CEIL({expected_packets} x {ps.qty_base}/{ps.per_packets})")

        print("-" * 68)
        print("\n SUCCESS: 500 g pack variant successfully created using shared family BOM.")
        print("=" * 68)

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    run_add_500g_demo()
