from datetime import datetime, timezone
from decimal import Decimal
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
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.item import Item, ItemType
from app.models.product import Product
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.purchase import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import MovementType, StockMovement
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.schemas.production import ProductionRunCreate, ProductionRunLineUpdate, ProductionRunUpdate
from app.services.purchase import create_and_post_purchase
from app.services.stock import get_balance, get_current_unit_cost, post_movement


class TestProductionBenchmark(unittest.TestCase):
    """
    Comprehensive test suite for Section 5 benchmark & production lifecycle:
    1. Setup master items with opening balances matching seed:
       - Flour: 100 kg (100,000 g) @ Rs 42/kg (4.2 paise/g)
       - Cooking oil: 30 L (30,000 ml) @ Rs 140/L (14 paise/ml)
       - Salt and spice mix: 5 kg (5,000 g) @ Rs 200/kg (20 paise/g)
       - 200 g pouch: 500 pieces @ Rs 2.50/pc (250 paise/pc)
       - Carton: 30 pieces @ Rs 15/pc (1500 paise/pc)
       - Murukku 200 g: 50 packets opening
    2. Purchase 60 kg flour @ Rs 45/kg (4.5 paise/g):
       - Total flour becomes 160 kg, new weighted-average cost = 4.312500 paise/g
    3. Planned 1-batch Murukku production run from BOM:
       - Flour 40 kg, Oil 10 L, Spice 1.2 kg, Pouches 200, Cartons 10, Output 200 pkts
    4. Actual entered:
       - Flour 40 kg, Oil 10.5 L, Spice 1.2 kg, Cartons 9, Good pkts 188, Damaged pouches 6 (pouches used = 194)
    5. Post run:
       - Balances after posting:
         Flour 120 kg, Oil 19.5 L, Spice 3.8 kg, Pouches 306, Cartons 21, Murukku 238 pkts
    6. Variances verified:
       - Oil: +5.00% (flagged, > 3.00%)
       - Yield: -6.00% (flagged, abs(-6.00) > 3.00%)
       - Cartons: -10.00% (flagged, abs(-10.00) > 3.00%)
       - Pouches: -3.00% (borderline, NOT flagged because strict > 3.00%)
       - Flour: 0.00%, Spice: 0.00%
    7. Insufficient stock rollback: no partial movements
    8. Cancellation: restores all ledger balances to pre-run values
    9. Unit conversion: kg/L converted to g/ml accurately
    10. Immutability & double posting prevention
    11. RBAC permissions across all 5 roles
    12. BOM versioning and immutability protection
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

        # Seed CompanySettings (variance tolerance 3.00%)
        self.company = CompanySettings(
            id=1,
            company_name="Sri Murugan Traditional Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Plot 42, SIDCO Industrial Estate, Kappalur, Madurai, Tamil Nadu - 625008",
            variance_tolerance_pct=Decimal("3.00"),
        )
        self.db.add(self.company)

        # Seed Users
        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@test.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@test.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.production = User(email="production@test.local", hashed_password=pwd, full_name="Production", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="accountant@test.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman = User(email="salesman@test.local", hashed_password=pwd, full_name="Salesman", role=UserRole.SALESMAN, is_active=True)

        self.db.add_all([self.admin, self.owner, self.production, self.accountant, self.salesman])
        self.db.commit()

        self.admin_token = create_access_token(subject=self.admin.id, role=self.admin.role)
        self.owner_token = create_access_token(subject=self.owner.id, role=self.owner.role)
        self.prod_token = create_access_token(subject=self.production.id, role=self.production.role)
        self.acct_token = create_access_token(subject=self.accountant.id, role=self.accountant.role)
        self.sales_token = create_access_token(subject=self.salesman.id, role=self.salesman.role)

        # Seed Supplier
        self.supplier = Supplier(
            name="Sri Lakshmi Agro Mills",
            gstin="33AAAAA1111A1Z1",
            state_code="33",
            phone="9876543210",
        )
        self.db.add(self.supplier)

        # Seed Items with Opening balances
        self.flour = Item(
            name="Flour",
            item_type=ItemType.RAW_MATERIAL,
            base_unit="g",
            display_unit="kg",
            hsn_code="1101",
            opening_balance_qty=100000,
            opening_rate_paise=Decimal("4.200000"),
        )
        self.oil = Item(
            name="Cooking oil",
            item_type=ItemType.RAW_MATERIAL,
            base_unit="ml",
            display_unit="L",
            hsn_code="1507",
            opening_balance_qty=30000,
            opening_rate_paise=Decimal("14.000000"),
        )
        self.spice = Item(
            name="Salt and spice mix",
            item_type=ItemType.RAW_MATERIAL,
            base_unit="g",
            display_unit="kg",
            hsn_code="0910",
            opening_balance_qty=5000,
            opening_rate_paise=Decimal("20.000000"),
        )
        self.pouch = Item(
            name="200 g pouch",
            item_type=ItemType.PACKAGING,
            base_unit="piece",
            display_unit="piece",
            hsn_code="3923",
            opening_balance_qty=500,
            opening_rate_paise=Decimal("250.000000"),
        )
        self.carton = Item(
            name="Carton",
            item_type=ItemType.PACKAGING,
            base_unit="piece",
            display_unit="piece",
            hsn_code="4819",
            opening_balance_qty=30,
            opening_rate_paise=Decimal("1500.000000"),
        )
        self.murukku_item = Item(
            name="Murukku 200 g",
            item_type=ItemType.FINISHED_GOOD,
            base_unit="packet",
            display_unit="packet",
            hsn_code="1905",
            opening_balance_qty=50,
            opening_rate_paise=Decimal("5000.000000"),
        )

        self.db.add_all([self.flour, self.oil, self.spice, self.pouch, self.carton, self.murukku_item])
        self.db.commit()

        # Record opening stock movements in ledger
        items_and_openings = [
            (self.flour, 100000, Decimal("4.200000")),
            (self.oil, 30000, Decimal("14.000000")),
            (self.spice, 5000, Decimal("20.000000")),
            (self.pouch, 500, Decimal("250.000000")),
            (self.carton, 30, Decimal("1500.000000")),
            (self.murukku_item, 50, Decimal("5000.000000")),
        ]
        for item, qty, rate in items_and_openings:
            post_movement(
                db=self.db,
                item_id=item.id,
                movement_type=MovementType.OPENING,
                quantity_base=qty,
                unit_cost=rate,
                source_type="OPENING",
                source_id="1",
                user=self.admin,
                movement_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        self.db.commit()

        # Seed Product
        self.product = Product(
            item_id=self.murukku_item.id,
            pack_size_desc="200 g",
            packets_per_carton=20,
        )
        self.db.add(self.product)
        self.db.commit()

        # Seed BOM (1 batch = 200 packets)
        # Flour: 40 kg (40,000 g), Oil: 10 L (10,000 ml), Spice: 1.2 kg (1,200 g), Pouches: 200, Cartons: 10
        self.bom = BOM(
            product_id=self.product.id,
            version=1,
            batch_output_packets=200,
            is_active=True,
        )
        self.db.add(self.bom)
        self.db.flush()

        bom_items_data = [
            (self.flour.id, 40000, "kg", None),
            (self.oil.id, 10000, "L", None),
            (self.spice.id, 1200, "kg", None),
            (self.pouch.id, 200, "piece", None),
            (self.carton.id, 10, "piece", None),
        ]
        for item_id, qty, unit, tol in bom_items_data:
            bi = BOMItem(
                bom_id=self.bom.id,
                item_id=item_id,
                quantity_per_batch=qty,
                unit_for_display=unit,
                variance_tolerance_pct=tol,
            )
            self.bom.items.append(bi)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def test_section_5_production_benchmark(self):
        """
        Runs the Section 5 benchmark exactly:
        1. Purchase 60 kg flour @ Rs 45/kg -> Flour becomes 160 kg, WAC = 4.312500 paise/g
        2. Create 1-batch Murukku production run
        3. Enter actuals:
           Flour 40 kg, Oil 10.5 L, Spice 1.2 kg, Cartons 9, Good pkts 188, Damaged pouches 6 (used 194)
        4. Post run
        5. Verify final inventory balances:
           Flour: 120 kg, Oil: 19.5 L, Spice: 3.8 kg, Pouches: 306, Cartons: 21, Murukku: 238 pkts
        6. Verify variances:
           Oil +5.00% flagged, Yield -6.00% flagged, Cartons -10.00% flagged,
           Pouches -3.00% (borderline, strictly not flagged), Flour 0%, Spice 0%
        """
        # Step 1: Purchase 60 kg flour @ Rs 45/kg (4.50 paise/g)
        # 60,000 g @ 4.5 paise/g = 270,000 paise (Rs 2,700)
        post_movement(
            db=self.db,
            item_id=self.flour.id,
            movement_type=MovementType.PURCHASE,
            quantity_base=60000,
            unit_cost=Decimal("4.500000"),
            source_type="PURCHASE",
            source_id="PO-001",
            user=self.admin,
            movement_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        self.db.commit()

        # Verify flour balance and weighted average cost before run
        flour_bal = get_balance(self.db, self.flour.id)
        self.assertEqual(flour_bal, 160000)  # 160 kg
        flour_wac = get_current_unit_cost(self.db, self.flour.id)
        # Total cost = 100,000 * 4.2 + 60,000 * 4.5 = 420,000 + 270,000 = 690,000 paise
        # WAC = 690,000 / 160,000 = 4.312500 paise/g
        self.assertEqual(flour_wac, Decimal("4.312500"))

        # Step 2: Create DRAFT Production Run for 1 batch
        headers = {"Authorization": f"Bearer {self.prod_token}"}
        create_payload = {
            "product_id": self.product.id,
            "batches": "1.0000",
            "notes": "Section 5 Benchmark Run",
        }
        resp = self.client.post("/production", json=create_payload, headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.text)
        run_data = resp.json()
        run_id = run_data["id"]
        self.assertEqual(run_data["status"], "DRAFT")
        self.assertEqual(run_data["expected_output_packets"], 200)

        # Verify planned lines from BOM
        lines_by_item = {l["item_id"]: l for l in run_data["lines"]}
        self.assertEqual(lines_by_item[self.flour.id]["planned_qty_base"], 40000)   # 40 kg
        self.assertEqual(lines_by_item[self.oil.id]["planned_qty_base"], 10000)     # 10 L
        self.assertEqual(lines_by_item[self.spice.id]["planned_qty_base"], 1200)    # 1.2 kg
        self.assertEqual(lines_by_item[self.pouch.id]["planned_qty_base"], 200)     # 200 pouches
        self.assertEqual(lines_by_item[self.carton.id]["planned_qty_base"], 10)     # 10 cartons

        # Step 3: Enter actual quantities via PATCH
        # Flour: 40 kg (40,000 g), Oil: 10.5 L (10,500 ml), Spice: 1.2 kg (1,200 g), Cartons: 9,
        # Good packets: 188, Damaged pouches: 6 -> Total pouches consumed = 188 + 6 = 194
        update_payload = {
            "actual_good_packets": 188,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 40000},
                {"item_id": self.oil.id, "actual_qty_base": 10500},
                {"item_id": self.spice.id, "actual_qty_base": 1200},
                {"item_id": self.pouch.id, "damaged_qty_base": 6},  # auto-computed: 188 good + 6 damaged = 194
                {"item_id": self.carton.id, "actual_qty_base": 9},
            ],
        }
        patch_resp = self.client.patch(f"/production/{run_id}", json=update_payload, headers=headers)
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.text)
        patched_data = patch_resp.json()

        # Check pouch calculation: 188 good + 6 damaged = 194
        pouch_line = next(l for l in patched_data["lines"] if l["item_id"] == self.pouch.id)
        self.assertEqual(pouch_line["actual_qty_base"], 194)
        self.assertEqual(pouch_line["damaged_qty_base"], 6)

        # Step 4: Post the run
        post_resp = self.client.post(f"/production/{run_id}/post", headers=headers)
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.text)
        posted_data = post_resp.json()
        self.assertEqual(posted_data["status"], "POSTED")

        # Step 5: Verify post-run inventory balances in the stock ledger
        # Flour: 160 kg - 40 kg = 120 kg (120,000 g)
        self.assertEqual(get_balance(self.db, self.flour.id), 120000)
        # Oil: 30 L - 10.5 L = 19.5 L (19,500 ml)
        self.assertEqual(get_balance(self.db, self.oil.id), 19500)
        # Spice: 5 kg - 1.2 kg = 3.8 kg (3,800 g)
        self.assertEqual(get_balance(self.db, self.spice.id), 3800)
        # Pouches: 500 - 194 = 306 pieces
        self.assertEqual(get_balance(self.db, self.pouch.id), 306)
        # Cartons: 30 - 9 = 21 pieces
        self.assertEqual(get_balance(self.db, self.carton.id), 21)
        # Finished Murukku 200 g: 50 opening + 188 produced = 238 packets
        self.assertEqual(get_balance(self.db, self.murukku_item.id), 238)

        # Step 6: Verify Variances & Alert Flags
        # Fetch run details with variance report
        get_resp = self.client.get(f"/production/{run_id}", headers=headers)
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        detail = get_resp.json()

        # Yield variance: (188 - 200) / 200 * 100 = -6.00%
        # Wastage: 200 - 188 = 12 packets
        # abs(-6.00) = 6.00% > 3.00% -> Flagged True
        self.assertEqual(Decimal(str(detail["yield_variance_pct"])), Decimal("-6.00"))
        self.assertEqual(detail["wastage_packets"], 12)
        self.assertTrue(detail["is_yield_flagged"])

        report = detail["variance_report"]
        self.assertIsNotNone(report)
        lines_report = {l["item_id"]: l for l in report["lines"]}

        # Oil variance: (10,500 - 10,000) / 10,000 * 100 = +5.00%
        # abs(5.00%) = 5.00% > 3.00% -> Flagged True
        oil_rep = lines_report[self.oil.id]
        self.assertEqual(Decimal(str(oil_rep["variance_pct"])), Decimal("5.00"))
        self.assertTrue(oil_rep["is_flagged"])

        # Cartons variance: (9 - 10) / 10 * 100 = -10.00%
        # abs(-10.00%) = 10.00% > 3.00% -> Flagged True
        carton_rep = lines_report[self.carton.id]
        self.assertEqual(Decimal(str(carton_rep["variance_pct"])), Decimal("-10.00"))
        self.assertTrue(carton_rep["is_flagged"])

        # Pouches variance: (194 - 200) / 200 * 100 = -3.00%
        # Borderline check: abs(-3.00%) = 3.00%. Rule is strictly '>' 3.00%, so 3.00 > 3.00 is False!
        pouch_rep = lines_report[self.pouch.id]
        self.assertEqual(Decimal(str(pouch_rep["variance_pct"])), Decimal("-3.00"))
        self.assertFalse(pouch_rep["is_flagged"], "Pouches at -3.00% must NOT be flagged under strict '>' rule")

        # Flour variance: (40,000 - 40,000) / 40,000 = 0.00%
        flour_rep = lines_report[self.flour.id]
        self.assertEqual(Decimal(str(flour_rep["variance_pct"])), Decimal("0.00"))
        self.assertFalse(flour_rep["is_flagged"])

        # Spice variance: (1,200 - 1,200) / 1,200 = 0.00%
        spice_rep = lines_report[self.spice.id]
        self.assertEqual(Decimal(str(spice_rep["variance_pct"])), Decimal("0.00"))
        self.assertFalse(spice_rep["is_flagged"])

        # Verify variance alerts endpoint
        alerts_resp = self.client.get("/production/variance-alerts", headers=headers)
        self.assertEqual(alerts_resp.status_code, status.HTTP_200_OK)
        alerts = alerts_resp.json()
        self.assertGreaterEqual(len(alerts), 1)
        alert_item_names = [line["item_name"] for a in alerts for line in a["flagged_lines"]]
        self.assertIn("Cooking oil", alert_item_names)
        self.assertIn("Carton", alert_item_names)
        self.assertNotIn("200 g pouch", alert_item_names)

        # Step 7: Verify double posting fails (idempotent guard)
        double_post_resp = self.client.post(f"/production/{run_id}/post", headers=headers)
        self.assertEqual(double_post_resp.status_code, status.HTTP_409_CONFLICT)

        # Step 8: Verify editing a POSTED run fails
        edit_posted_resp = self.client.patch(f"/production/{run_id}", json={"notes": "Changed"}, headers=headers)
        self.assertEqual(edit_posted_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_insufficient_stock_rollback(self):
        """
        Verify that if stock for ANY item is insufficient when posting,
        the entire transaction is rolled back: no partial movements, no negative stock.
        """
        headers = {"Authorization": f"Bearer {self.prod_token}"}
        create_resp = self.client.post(
            "/production",
            json={"product_id": self.product.id, "batches": "1.0000"},
            headers=headers,
        )
        run_id = create_resp.json()["id"]

        # Request 40,000 ml of oil when only 30,000 ml is available in inventory
        update_payload = {
            "actual_good_packets": 200,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 40000},
                {"item_id": self.oil.id, "actual_qty_base": 40000},  # Shortage: 40,000 > 30,000 available
                {"item_id": self.spice.id, "actual_qty_base": 1200},
                {"item_id": self.pouch.id, "actual_qty_base": 200},
                {"item_id": self.carton.id, "actual_qty_base": 10},
            ],
        }
        self.client.patch(f"/production/{run_id}", json=update_payload, headers=headers)

        # Post should fail with HTTP 409 listing shortages
        post_resp = self.client.post(f"/production/{run_id}/post", headers=headers)
        self.assertEqual(post_resp.status_code, status.HTTP_409_CONFLICT, post_resp.text)
        err_detail = post_resp.json()["detail"]
        self.assertIn("shortages", err_detail)
        shortage = err_detail["shortages"][0]
        self.assertEqual(shortage["item_id"], self.oil.id)
        self.assertEqual(shortage["available_base"], 30000)
        self.assertEqual(shortage["required_base"], 40000)
        self.assertEqual(shortage["shortage_base"], 10000)

        # Verify NO movements were written (all balances remain at opening stock)
        self.assertEqual(get_balance(self.db, self.flour.id), 100000)
        self.assertEqual(get_balance(self.db, self.oil.id), 30000)
        self.assertEqual(get_balance(self.db, self.murukku_item.id), 50)

    def test_cancel_posted_run_reverses_balances(self):
        """
        Verify that cancelling a posted production run (ADMIN only):
        - Writes REVERSAL stock movements for every original movement.
        - Returns all inventory balances to exact pre-run values.
        - Sets run status to CANCELLED.
        """
        headers = {"Authorization": f"Bearer {self.prod_token}"}
        create_resp = self.client.post(
            "/production",
            json={"product_id": self.product.id, "batches": "1.0000"},
            headers=headers,
        )
        run_id = create_resp.json()["id"]

        update_payload = {
            "actual_good_packets": 200,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 40000},
                {"item_id": self.oil.id, "actual_qty_base": 10000},
                {"item_id": self.spice.id, "actual_qty_base": 1200},
                {"item_id": self.pouch.id, "actual_qty_base": 200},
                {"item_id": self.carton.id, "actual_qty_base": 10},
            ],
        }
        self.client.patch(f"/production/{run_id}", json=update_payload, headers=headers)
        self.client.post(f"/production/{run_id}/post", headers=headers)

        # Flour was 100 kg, after run: 60 kg
        self.assertEqual(get_balance(self.db, self.flour.id), 60000)
        # Murukku was 50 pkts, after run: 250 pkts
        self.assertEqual(get_balance(self.db, self.murukku_item.id), 250)

        # Cancel as ADMIN
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        cancel_resp = self.client.post(
            f"/production/{run_id}/cancel",
            json={"reason": "Contaminated batch during quality inspection"},
            headers=admin_headers,
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.text)
        self.assertEqual(cancel_resp.json()["status"], "CANCELLED")

        # Verify all balances restored to opening values
        self.assertEqual(get_balance(self.db, self.flour.id), 100000)
        self.assertEqual(get_balance(self.db, self.oil.id), 30000)
        self.assertEqual(get_balance(self.db, self.spice.id), 5000)
        self.assertEqual(get_balance(self.db, self.pouch.id), 500)
        self.assertEqual(get_balance(self.db, self.carton.id), 30)
        self.assertEqual(get_balance(self.db, self.murukku_item.id), 50)

    def test_unit_conversion_input(self):
        """
        Verify unit conversion when actual consumption is entered in kg / L / pieces:
        - 40 kg flour -> stored as 40,000 g
        - 10.5 L oil -> stored as 10,500 ml
        - 1.2 kg spice -> stored as 1,200 g
        """
        headers = {"Authorization": f"Bearer {self.prod_token}"}
        create_resp = self.client.post(
            "/production",
            json={"product_id": self.product.id, "batches": "1.0000"},
            headers=headers,
        )
        run_id = create_resp.json()["id"]

        update_payload = {
            "actual_good_packets": 188,
            "lines": [
                {"item_id": self.flour.id, "actual_qty": 40.0, "unit": "kg"},
                {"item_id": self.oil.id, "actual_qty": 10.5, "unit": "L"},
                {"item_id": self.spice.id, "actual_qty": 1.2, "unit": "kg"},
                {"item_id": self.pouch.id, "damaged_qty": 6, "unit": "piece"},
                {"item_id": self.carton.id, "actual_qty": 9, "unit": "piece"},
            ],
        }
        patch_resp = self.client.patch(f"/production/{run_id}", json=update_payload, headers=headers)
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.text)
        lines = {l["item_id"]: l for l in patch_resp.json()["lines"]}

        self.assertEqual(lines[self.flour.id]["actual_qty_base"], 40000)
        self.assertEqual(lines[self.oil.id]["actual_qty_base"], 10500)
        self.assertEqual(lines[self.spice.id]["actual_qty_base"], 1200)
        self.assertEqual(lines[self.pouch.id]["actual_qty_base"], 194)  # 188 + 6
        self.assertEqual(lines[self.carton.id]["actual_qty_base"], 9)

    def test_rbac_permissions(self):
        """
        Verify RBAC permissions for production module:
        - PRODUCTION: create, edit, post allowed; cancel forbidden.
        - ADMIN: everything allowed including cancel.
        - ACCOUNTANT & OWNER: read allowed; create/edit/post/cancel forbidden.
        - SALESMAN: no access (HTTP 403 Forbidden on all endpoints).
        """
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        sales_h = {"Authorization": f"Bearer {self.sales_token}"}

        # 1. Salesman is rejected on GET /production
        resp = self.client.get("/production", headers=sales_h)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Accountant can read but cannot create
        resp = self.client.get("/production", headers=acct_h)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post("/production", json={"product_id": self.product.id}, headers=acct_h)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Owner can read but cannot post
        resp = self.client.get("/production", headers=owner_h)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # 4. Production creates run
        resp = self.client.post("/production", json={"product_id": self.product.id}, headers=prod_h)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        run_id = resp.json()["id"]

        # 5. Production CANNOT cancel (ADMIN only)
        resp = self.client.post(f"/production/{run_id}/cancel", json={"reason": "Cancel"}, headers=prod_h)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 6. Admin can cancel
        resp = self.client.post(f"/production/{run_id}/cancel", json={"reason": "Admin cancel"}, headers=admin_h)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_bom_versioning_and_immutability(self):
        """
        Verify BOM management rules:
        - Can create and activate a new BOM version (only 1 active version per product).
        - Cannot edit a BOM version that has been used by a POSTED production run.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}

        # Create production run using BOM v1 and post it
        create_resp = self.client.post("/production", json={"product_id": self.product.id}, headers=prod_h)
        run_id = create_resp.json()["id"]
        self.client.patch(
            f"/production/{run_id}",
            json={"actual_good_packets": 200},
            headers=prod_h,
        )
        self.client.post(f"/production/{run_id}/post", headers=prod_h)

        # Attempt to PUT /boms/{bom_id} on BOM v1 -> Must fail with 409 Conflict
        put_payload = {
            "product_id": self.product.id,
            "version": 1,
            "batch_output_packets": 210,
            "is_active": True,
            "items": [
                {"item_id": self.flour.id, "quantity_per_batch": 40000, "unit_for_display": "kg"},
            ],
        }
        resp = self.client.put(f"/boms/{self.bom.id}", json=put_payload, headers=admin_h)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.text)
        self.assertIn("has been used in posted production run", resp.json()["detail"])

        # Create new BOM version 2
        v2_payload = {
            "product_id": self.product.id,
            "version": 2,
            "batch_output_packets": 200,
            "is_active": True,
            "items": [
                {"item_id": self.flour.id, "quantity_per_batch": 38000, "unit_for_display": "kg", "variance_tolerance_pct": "2.50"},
                {"item_id": self.oil.id, "quantity_per_batch": 10000, "unit_for_display": "L"},
            ],
        }
        v2_resp = self.client.post("/boms", json=v2_payload, headers=admin_h)
        self.assertEqual(v2_resp.status_code, status.HTTP_201_CREATED, v2_resp.text)
        bom2_id = v2_resp.json()["id"]
        self.assertTrue(v2_resp.json()["is_active"])

        # Verify old BOM v1 is automatically deactivated
        get_v1 = self.client.get(f"/boms/{self.bom.id}", headers=admin_h)
        self.assertFalse(get_v1.json()["is_active"])


if __name__ == "__main__":
    unittest.main()
