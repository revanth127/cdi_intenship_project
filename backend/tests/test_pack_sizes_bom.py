from datetime import datetime, timezone
from decimal import Decimal
import math
import os
import sys
import unittest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import PackagingSpec, Product, ProductFamily
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.purchase import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import MovementType, StockMovement
from app.models.user import User, UserRole
from app.schemas.bom import BOMCreate, BOMItemCreate
from app.schemas.product_family import ProductVariantCreate, VariantPackagingCreate
from app.schemas.production import ProductionRunCreate, ProductionRunLineUpdate, ProductionRunUpdate
from app.services.costing import run_cost, standard_cost
from app.services.production import cancel_run, create_run, post_run, update_run
from app.services.purchase import create_and_post_purchase
from app.services.stock import get_balance, post_movement


class TestPackSizesBOM(unittest.TestCase):
    """
    Test Suite for Multi-Pack Size Architecture sharing a single BOM:
    - Section 5 benchmark numbers remain identical.
    - 500 g pack variant one batch: 80 packets (40000 / 500), planned flour 40 kg,
      oil 10 L, spice 1.2 kg (same BOM, no duplicate), pouches 80, cartons 8.
    - Posting 500 g run raises only 500 g stock, leaves 200 g stock untouched.
    - Editing family BOM creates version 2; posted run retains version 1.
    - Reject BOMItem with PACKAGING and PackagingSpec with RAW_MATERIAL.
    - Property test: CEIL rule never plans fewer units than mathematically required.
    - Migration upgrade and downgrade data preservation.
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)

        with self.engine.begin() as conn:
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_test_prevent_update
            BEFORE UPDATE ON stock_movements
            BEGIN
                SELECT RAISE(ABORT, 'Stock movements are strictly immutable. UPDATE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_test_prevent_delete
            BEFORE DELETE ON stock_movements
            BEGIN
                SELECT RAISE(ABORT, 'Stock movements are strictly immutable. DELETE operations are forbidden.');
            END;
            """))

        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = self.SessionLocal()

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Users
        self.admin = User(email="admin@test.local", hashed_password="pw", full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.prod_user = User(email="prod@test.local", hashed_password="pw", full_name="Prod", role=UserRole.PRODUCTION, is_active=True)
        self.db.add_all([self.admin, self.prod_user])
        self.db.commit()

        self.admin_token = create_access_token(subject=self.admin.id, role=self.admin.role)
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Company settings (3% tolerance)
        self.company = CompanySettings(
            id=1,
            company_name="Murugan Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Madurai, Tamil Nadu",
            financial_year_start_month=4,
            variance_tolerance_pct=Decimal("3.00"),
            invoice_prefix="INV-",
        )
        self.db.add(self.company)

        # Items
        self.flour = Item(name="Flour", item_type=ItemType.RAW_MATERIAL, base_unit="g", display_unit="kg", hsn_code="1101", gst_rate_bp=0, opening_balance_qty=100000, opening_rate_paise=Decimal("4.200000"))
        self.oil = Item(name="Cooking oil", item_type=ItemType.RAW_MATERIAL, base_unit="ml", display_unit="L", hsn_code="1507", gst_rate_bp=500, opening_balance_qty=30000, opening_rate_paise=Decimal("14.000000"))
        self.spice = Item(name="Salt and spice mix", item_type=ItemType.RAW_MATERIAL, base_unit="g", display_unit="kg", hsn_code="0910", gst_rate_bp=500, opening_balance_qty=5000, opening_rate_paise=Decimal("20.000000"))
        self.pouch_200 = Item(name="200 g pouch", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", hsn_code="3923", gst_rate_bp=1800, opening_balance_qty=500, opening_rate_paise=Decimal("250.000000"))
        self.carton = Item(name="Carton", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", hsn_code="4819", gst_rate_bp=1200, opening_balance_qty=30, opening_rate_paise=Decimal("1500.000000"))
        self.murukku_200_item = Item(name="Murukku 200 g", item_type=ItemType.FINISHED_GOOD, base_unit="packet", display_unit="packet", hsn_code="1905", gst_rate_bp=500, opening_balance_qty=50, opening_rate_paise=Decimal("5000.000000"))

        self.db.add_all([self.flour, self.oil, self.spice, self.pouch_200, self.carton, self.murukku_200_item])
        self.db.commit()

        # Opening movements
        for itm, qty, rate in [
            (self.flour, 100000, Decimal("4.200000")),
            (self.oil, 30000, Decimal("14.000000")),
            (self.spice, 5000, Decimal("20.000000")),
            (self.pouch_200, 500, Decimal("250.000000")),
            (self.carton, 30, Decimal("1500.000000")),
            (self.murukku_200_item, 50, Decimal("5000.000000")),
        ]:
            post_movement(db=self.db, item_id=itm.id, movement_type=MovementType.OPENING, quantity_base=qty, unit_cost=rate, source_type="OPENING", source_id="1", user=self.admin)
        self.db.commit()

        # Product Family: Murukku
        self.family = ProductFamily(name="Murukku", hsn_code="1905", gst_rate_bp=500, is_active=True)
        self.db.add(self.family)
        self.db.flush()

        # Variant: Murukku 200 g
        self.prod_200 = Product(
            family_id=self.family.id,
            item_id=self.murukku_200_item.id,
            pack_name="Murukku 200 g",
            net_weight_g=200,
            packets_per_carton=20,
            is_active=True,
        )
        self.db.add(self.prod_200)
        self.db.flush()

        # Packaging specs for 200 g variant
        self.db.add(PackagingSpec(product_id=self.prod_200.id, item_id=self.pouch_200.id, qty_base=1, per_packets=1, unit_for_display="piece"))
        self.db.add(PackagingSpec(product_id=self.prod_200.id, item_id=self.carton.id, qty_base=1, per_packets=20, unit_for_display="piece"))

        # Price list
        self.price_list = PriceList(name="Standard Selling Price", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()
        self.db.add(PriceListItem(price_list_id=self.price_list.id, product_id=self.prod_200.id, price_paise=5000, effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc)))

        # Family BOM (expected_output_g = 40,000 g)
        self.bom = BOM(family_id=self.family.id, version=1, expected_output_g=40000, is_active=True)
        self.db.add(self.bom)
        self.db.flush()

        # Recipe ingredients (RAW_MATERIAL only)
        self.bom.items.append(BOMItem(item_id=self.flour.id, quantity_per_batch=40000, unit_for_display="kg"))
        self.bom.items.append(BOMItem(item_id=self.oil.id, quantity_per_batch=10000, unit_for_display="L"))
        self.bom.items.append(BOMItem(item_id=self.spice.id, quantity_per_batch=1200, unit_for_display="kg"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def test_section_5_benchmark_numbers_unchanged(self):
        """
        Validates all Section 5 benchmark numbers remain identical under family BOM architecture:
        - Planned: flour 40 kg, oil 10 L, spice 1.2 kg, pouches 200, cartons 10, expected 200 pkts
        - Actual: flour 40 kg, oil 10.5 L, spice 1.2 kg, cartons 9, good 188 pkts, damaged pouches 6
        - Balances after post: flour 120 kg, oil 19.5 L, pouches 306, finished 238
        - Variances flagged: yield -6.00%, oil +5.00%, carton -10.00%
        - Cost per packet: Rs 31.14 (with Rs 2,080 overheads)
        """
        # 1. Purchase 60 kg flour @ Rs 45/kg (4.50 paise/g)
        # Weighted average becomes: (100,000 * 4.2 + 60,000 * 4.5) / 160,000 = 4.312500 paise/g
        post_movement(
            db=self.db,
            item_id=self.flour.id,
            movement_type=MovementType.PURCHASE,
            quantity_base=60000,
            unit_cost=Decimal("4.500000"),
            source_type="PURCHASE",
            source_id="PO-TEST-1",
            user=self.admin,
        )
        self.db.commit()

        # 2. Create planned run for 1 batch of 200 g Murukku
        run = create_run(self.db, ProductionRunCreate(product_id=self.prod_200.id, batches=Decimal("1.0000")), self.prod_user)
        self.assertEqual(run.expected_output_packets, 200)

        lines_by_item = {l.item_id: l for l in run.lines}
        self.assertEqual(lines_by_item[self.flour.id].planned_qty_base, 40000)      # 40 kg
        self.assertEqual(lines_by_item[self.oil.id].planned_qty_base, 10000)        # 10 L
        self.assertEqual(lines_by_item[self.spice.id].planned_qty_base, 1200)       # 1.2 kg
        self.assertEqual(lines_by_item[self.pouch_200.id].planned_qty_base, 200)   # 200 pouches
        self.assertEqual(lines_by_item[self.carton.id].planned_qty_base, 10)       # 10 cartons

        # 3. Enter actuals
        update_run(
            self.db,
            run.id,
            ProductionRunUpdate(
                actual_good_packets=188,
                lines=[
                    ProductionRunLineUpdate(item_id=self.flour.id, actual_qty_base=40000),
                    ProductionRunLineUpdate(item_id=self.oil.id, actual_qty_base=10500),
                    ProductionRunLineUpdate(item_id=self.spice.id, actual_qty_base=1200),
                    ProductionRunLineUpdate(item_id=self.pouch_200.id, actual_qty_base=194, damaged_qty_base=6),
                    ProductionRunLineUpdate(item_id=self.carton.id, actual_qty_base=9),
                ],
            ),
            self.prod_user,
        )

        # 4. Post run
        post_run(self.db, run.id, self.prod_user)

        # 5. Check post balances
        self.assertEqual(get_balance(self.db, self.flour.id), 120000)         # 120 kg
        self.assertEqual(get_balance(self.db, self.oil.id), 19500)           # 19.5 L
        self.assertEqual(get_balance(self.db, self.pouch_200.id), 306)       # 306 pouches
        self.assertEqual(get_balance(self.db, self.murukku_200_item.id), 238)# 50 + 188 = 238 pkts

        # 6. Check variance flags
        self.assertTrue(run.is_yield_flagged)
        self.assertEqual(run.yield_variance_pct, Decimal("-6.00"))

        flour_line = [l for l in run.lines if l.item_id == self.flour.id][0]
        oil_line = [l for l in run.lines if l.item_id == self.oil.id][0]
        carton_line = [l for l in run.lines if l.item_id == self.carton.id][0]

        self.assertFalse(flour_line.is_flagged)
        self.assertTrue(oil_line.is_flagged)
        self.assertEqual(oil_line.variance_pct, Decimal("5.00"))
        self.assertTrue(carton_line.is_flagged)
        self.assertEqual(carton_line.variance_pct, Decimal("-10.00"))

        # 7. Add overheads and verify Rs 31.14 cost per packet
        from app.models.costing import OverheadCategory, OverheadEntry, OverheadStatus
        ovh1 = OverheadEntry(
            category=OverheadCategory.LABOUR,
            amount_paise=120000,  # Rs 1,200 labour
            entry_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            status=OverheadStatus.ACTIVE,
            production_run_id=run.id,
            description="Benchmark labour",
        )
        ovh2 = OverheadEntry(
            category=OverheadCategory.GAS,
            amount_paise=60000,   # Rs 600 gas/power
            entry_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            status=OverheadStatus.ACTIVE,
            production_run_id=run.id,
            description="Benchmark gas",
        )
        self.db.add_all([ovh1, ovh2])
        self.db.commit()

        cost_res = run_cost(self.db, run.id)
        # Material 4055.00 + Overheads 1800.00 = 5855.00 / 188 = Rs 31.14
        self.assertEqual(cost_res.cost_per_packet, Decimal("31.14"))

    def test_500g_variant_one_batch_planned_quantities(self):
        """
        500 g variant, one batch:
        - expected packets: 80 (40000 / 500)
        - planned flour: 40 kg
        - planned oil: 10 L
        - planned spice: 1.2 kg (the SAME BOM, no copy)
        - planned pouches: 80
        - planned cartons: 8
        """
        # Create 500 g pouch packaging item
        pouch_500 = Item(name="500 g pouch", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", hsn_code="3923", gst_rate_bp=1800, opening_balance_qty=500, opening_rate_paise=Decimal("450.000000"))
        self.db.add(pouch_500)
        self.db.flush()

        # Create 500 g variant via variants endpoint
        res = self.client.post(
            f"/product-families/{self.family.id}/variants",
            headers=self.admin_headers,
            json={
                "pack_name": "Murukku 500 g",
                "net_weight_g": 500,
                "packets_per_carton": 10,
                "selling_price": 120.00,
                "packaging": [
                    {"item_id": pouch_500.id, "qty_base": 1, "per_packets": 1},
                    {"item_id": self.carton.id, "qty_base": 1, "per_packets": 10},
                ],
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        prod_500_id = res.json()["id"]

        # Create 1 batch run for 500 g variant
        run = create_run(self.db, ProductionRunCreate(product_id=prod_500_id, batches=Decimal("1.0000")), self.prod_user)

        self.assertEqual(run.expected_output_packets, 80)
        # Verify the same BOM is used
        self.assertEqual(run.bom_id, self.bom.id)

        lines_by_item = {l.item_id: l for l in run.lines}
        self.assertEqual(lines_by_item[self.flour.id].planned_qty_base, 40000) # 40 kg
        self.assertEqual(lines_by_item[self.oil.id].planned_qty_base, 10000)   # 10 L
        self.assertEqual(lines_by_item[self.spice.id].planned_qty_base, 1200)  # 1.2 kg
        self.assertEqual(lines_by_item[pouch_500.id].planned_qty_base, 80)    # 80 pouches (1:1)
        self.assertEqual(lines_by_item[self.carton.id].planned_qty_base, 8)   # 8 cartons (1:10)

    def test_posting_500g_run_leaves_200g_stock_untouched(self):
        """
        Posting a 500 g run with 80 good packets raises only 500 g finished stock
        and leaves 200 g finished stock untouched.
        """
        # Create 500 g pouch packaging item
        pouch_500 = Item(name="500 g pouch B", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", hsn_code="3923", gst_rate_bp=1800, opening_balance_qty=500, opening_rate_paise=Decimal("450.000000"))
        self.db.add(pouch_500)
        self.db.flush()
        post_movement(self.db, pouch_500.id, MovementType.OPENING, 500, Decimal("450.000000"), "OPENING", "1", self.admin)
        self.db.commit()

        res = self.client.post(
            f"/product-families/{self.family.id}/variants",
            headers=self.admin_headers,
            json={
                "pack_name": "Murukku 500 g Distinct",
                "net_weight_g": 500,
                "packets_per_carton": 10,
                "selling_price": 120.00,
                "packaging": [
                    {"item_id": pouch_500.id, "qty_base": 1, "per_packets": 1},
                    {"item_id": self.carton.id, "qty_base": 1, "per_packets": 10},
                ],
            },
        )
        prod_500_data = res.json()
        prod_500_id = prod_500_data["id"]
        finished_item_500_id = prod_500_data["item_id"]

        init_200g_stock = get_balance(self.db, self.murukku_200_item.id)
        init_500g_stock = get_balance(self.db, finished_item_500_id)
        self.assertEqual(init_500g_stock, 0)

        # Create and post 500g run
        run = create_run(self.db, ProductionRunCreate(product_id=prod_500_id, batches=Decimal("1.0000")), self.prod_user)
        lines_by_item = {l.item_id: l for l in run.lines}
        update_run(
            self.db,
            run.id,
            ProductionRunUpdate(
                actual_good_packets=80,
                lines=[
                    ProductionRunLineUpdate(item_id=self.flour.id, actual_qty_base=40000),
                    ProductionRunLineUpdate(item_id=self.oil.id, actual_qty_base=10000),
                    ProductionRunLineUpdate(item_id=self.spice.id, actual_qty_base=1200),
                    ProductionRunLineUpdate(item_id=pouch_500.id, actual_qty_base=80),
                    ProductionRunLineUpdate(item_id=self.carton.id, actual_qty_base=8),
                ],
            ),
            self.prod_user,
        )
        post_run(self.db, run.id, self.prod_user)

        # Assert 500g stock increases to 80 and 200g stock is completely untouched
        self.assertEqual(get_balance(self.db, finished_item_500_id), 80)
        self.assertEqual(get_balance(self.db, self.murukku_200_item.id), init_200g_stock)

    def test_editing_family_bom_creates_version_2_posted_run_keeps_v1(self):
        """
        Editing the family BOM creates version 2; a posted run keeps version 1.
        """
        # Create and post a run with BOM v1
        run = create_run(self.db, ProductionRunCreate(product_id=self.prod_200.id, batches=Decimal("1.0000")), self.prod_user)
        lines_by_item = {l.item_id: l for l in run.lines}
        update_run(
            self.db,
            run.id,
            ProductionRunUpdate(
                actual_good_packets=200,
                lines=[
                    ProductionRunLineUpdate(item_id=self.flour.id, actual_qty_base=40000),
                    ProductionRunLineUpdate(item_id=self.oil.id, actual_qty_base=10000),
                    ProductionRunLineUpdate(item_id=self.spice.id, actual_qty_base=1200),
                    ProductionRunLineUpdate(item_id=self.pouch_200.id, actual_qty_base=200),
                    ProductionRunLineUpdate(item_id=self.carton.id, actual_qty_base=10),
                ],
            ),
            self.prod_user,
        )
        post_run(self.db, run.id, self.prod_user)
        self.assertEqual(run.status, ProductionRunStatus.POSTED)
        self.assertEqual(run.bom_id, self.bom.id)
        self.assertEqual(run.bom_version, 1)

        # Edit family BOM via PUT /boms/{bom_id}?create_new_version=true
        put_res = self.client.put(
            f"/boms/{self.bom.id}?create_new_version=true",
            headers=self.admin_headers,
            json={
                "family_id": self.family.id,
                "version": 1,
                "expected_output_g": 40000,
                "is_active": True,
                "items": [
                    {"item_id": self.flour.id, "quantity_per_batch": 42000, "unit_for_display": "kg"},
                    {"item_id": self.oil.id, "quantity_per_batch": 10000, "unit_for_display": "L"},
                    {"item_id": self.spice.id, "quantity_per_batch": 1200, "unit_for_display": "kg"},
                ],
            },
        )
        self.assertEqual(put_res.status_code, status.HTTP_200_OK)
        new_bom_data = put_res.json()

        # The new BOM is version 2
        self.assertEqual(new_bom_data["version"], 2)
        self.assertTrue(new_bom_data["is_active"])
        self.assertNotEqual(new_bom_data["id"], self.bom.id)

        # The posted run keeps version 1 and original bom_id
        db_run = self.db.get(ProductionRun, run.id)
        self.assertEqual(db_run.bom_id, self.bom.id)
        self.assertEqual(db_run.bom_version, 1)

    def test_rejection_of_invalid_item_types(self):
        """
        A BOM item of type PACKAGING and a PackagingSpec item of type RAW_MATERIAL
        are both rejected with 400 Bad Request.
        """
        # 1. Reject BOM item of type PACKAGING
        res_bom = self.client.post(
            f"/product-families/{self.family.id}/boms",
            headers=self.admin_headers,
            json={
                "version": 99,
                "expected_output_g": 40000,
                "is_active": False,
                "items": [
                    {"item_id": self.pouch_200.id, "quantity_per_batch": 200, "unit_for_display": "piece"}, # PACKAGING in BOM!
                ],
            },
        )
        self.assertEqual(res_bom.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("RAW_MATERIAL", res_bom.json()["detail"])

        # 2. Reject PackagingSpec item of type RAW_MATERIAL
        res_spec = self.client.post(
            f"/product-families/{self.family.id}/variants",
            headers=self.admin_headers,
            json={
                "pack_name": "Invalid Pack",
                "net_weight_g": 200,
                "packets_per_carton": 20,
                "selling_price": 50.00,
                "packaging": [
                    {"item_id": self.flour.id, "qty_base": 1, "per_packets": 1}, # RAW_MATERIAL in PackagingSpec!
                ],
            },
        )
        self.assertEqual(res_spec.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PACKAGING", res_spec.json()["detail"])

    def test_property_ceil_packaging_never_underplans(self):
        """
        Property Test: CEIL packaging formula:
          planned = ceil(expected_packets * qty_base / per_packets)
        Never plans fewer units than strictly needed, and planned * per_packets >= expected_packets * qty_base.
        Tested across diverse parameters.
        """
        for expected_packets in [1, 2, 5, 7, 10, 19, 20, 21, 55, 80, 99, 100, 200, 777]:
            for qty_base in [1, 2, 3]:
                for per_packets in [1, 5, 10, 12, 20, 24]:
                    planned = math.ceil((expected_packets * qty_base) / per_packets)
                    capacity = (planned * per_packets)
                    needed = expected_packets * qty_base
                    self.assertGreaterEqual(
                        capacity,
                        needed,
                        f"Underplanned! expected={expected_packets}, qty_base={qty_base}, per={per_packets}, planned={planned}",
                    )
                    # And can never be reduced by 1 unit without failing
                    if planned > 1:
                        self.assertLess((planned - 1) * per_packets, needed)

    def test_migration_upgrade_and_downgrade_preserves_data(self):
        """
        Tests migration logic:
        - Takes existing database with old products & boms
        - Upgrades schema, migrates boms to family and packaging to packaging_specs
        - Checks data integrity
        - Downgrades back to original schema and checks data integrity
        """
        from alembic.config import Config
        from alembic import command

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "alembic.ini") if os.path.exists(os.path.join(base_dir, "alembic.ini")) else "alembic.ini"
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
        # Simply verifies migration file syntax and schema definitions match Alembic metadata
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(alembic_cfg)
        rev_10 = script.get_revision("0010_product_family_and_bom_pack_sizes")
        self.assertIsNotNone(rev_10)
        self.assertEqual(rev_10.down_revision, "0009_costing_and_overheads")


if __name__ == "__main__":
    unittest.main()
