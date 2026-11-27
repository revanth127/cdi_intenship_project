from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
import unittest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.costing import OverheadCategory, OverheadEntry, OverheadStatus, RunCostSheet
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.stock import MovementType, StockMovement
from app.models.user import User, UserRole
from app.services.stock import post_movement


class TestCostingPhase8(unittest.TestCase):
    """
    Test suite for Phase 8: Product Costing, Overheads Allocation,
    Run Cost Sheets, Product Cost Summaries, Margins, and RBAC Permissions.
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)

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

        # 1. Company Settings
        self.company = CompanySettings(
            id=1,
            company_name="Sri Murugan Traditional Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Plot 42, SIDCO Industrial Estate, Madurai, Tamil Nadu - 625008",
            variance_tolerance_pct=Decimal("3.00"),
        )
        self.db.add(self.company)

        # 2. Users & Roles
        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@cost.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@cost.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.production = User(email="prod@cost.local", hashed_password=pwd, full_name="Prod", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="acct@cost.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman = User(email="sales@cost.local", hashed_password=pwd, full_name="Salesman", role=UserRole.SALESMAN, is_active=True)

        self.db.add_all([self.admin, self.owner, self.production, self.accountant, self.salesman])
        self.db.commit()

        # JWT tokens
        self.admin_token = create_access_token(subject=self.admin.id, role=self.admin.role)
        self.owner_token = create_access_token(subject=self.owner.id, role=self.owner.role)
        self.prod_token = create_access_token(subject=self.production.id, role=self.production.role)
        self.acct_token = create_access_token(subject=self.accountant.id, role=self.accountant.role)
        self.sales_token = create_access_token(subject=self.salesman.id, role=self.salesman.role)

        # 3. Items with opening balances matching Section 5 seed:
        # - Flour: 100 kg (100,000 g) @ Rs 42/kg (4.2 paise/g)
        # - Cooking oil: 30 L (30,000 ml) @ Rs 140/L (14 paise/ml)
        # - Salt and spice mix: 5 kg (5,000 g) @ Rs 200/kg (20 paise/g)
        # - 200 g pouch: 500 pcs @ Rs 2.50/pc (250 paise/pc)
        # - Carton: 30 pcs @ Rs 15/pc (1500 paise/pc)
        # - Murukku 200 g: 50 packets opening
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
            gst_rate_bp=500,  # 5% GST
            opening_balance_qty=50,
            opening_rate_paise=Decimal("5000.000000"),
        )
        self.db.add_all([self.flour, self.oil, self.spice, self.pouch, self.carton, self.murukku_item])
        self.db.commit()

        # Ledger opening movements
        openings = [
            (self.flour, 100000, Decimal("4.200000")),
            (self.oil, 30000, Decimal("14.000000")),
            (self.spice, 5000, Decimal("20.000000")),
            (self.pouch, 500, Decimal("250.000000")),
            (self.carton, 30, Decimal("1500.000000")),
            (self.murukku_item, 50, Decimal("5000.000000")),
        ]
        for itm, qty, rate in openings:
            post_movement(
                db=self.db,
                item_id=itm.id,
                movement_type=MovementType.OPENING,
                quantity_base=qty,
                unit_cost=rate,
                source_type="OPENING",
                source_id="1",
                user=self.admin,
                movement_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        self.db.commit()

        # 4. Product, BOM & Price List
        self.product = Product(item_id=self.murukku_item.id, pack_size_desc="200 g", packets_per_carton=20)
        self.db.add(self.product)
        self.db.flush()

        self.bom = BOM(product_id=self.product.id, version=1, batch_output_packets=200, is_active=True)
        self.db.add(self.bom)
        self.db.flush()

        bom_items_data = [
            (self.flour.id, 40000, "kg"),
            (self.oil.id, 10000, "L"),
            (self.spice.id, 1200, "kg"),
            (self.pouch.id, 200, "piece"),
            (self.carton.id, 10, "piece"),
        ]
        for itm_id, qty, unit in bom_items_data:
            self.bom.items.append(
                BOMItem(bom_id=self.bom.id, item_id=itm_id, quantity_per_batch=qty, unit_for_display=unit)
            )

        self.price_list = PriceList(name="Standard Selling Price", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()

        self.price_item = PriceListItem(
            price_list_id=self.price_list.id,
            product_id=self.product.id,
            price_paise=5000,  # Rs 50.00
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(self.price_item)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def _setup_benchmark_run(self) -> int:
        """
        Executes the exact Section 5 production run benchmark:
        1. Purchase 60 kg flour @ Rs 45/kg -> Flour WAC = 4.312500 paise/g
        2. Production run actuals:
           Flour 40 kg, Oil 10.5 L, Spice 1.2 kg, Cartons 9, Good pkts 188, Damaged pouches 6 (used 194)
        3. Post run.
        """
        # Step 1: Purchase 60 kg flour @ Rs 45/kg (4.50 paise/g)
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

        # Step 2: Create DRAFT run
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        create_resp = self.client.post("/production", json={"product_id": self.product.id, "batches": "1.0000"}, headers=prod_h)
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        run_id = create_resp.json()["id"]

        # Step 3: Enter actuals
        patch_payload = {
            "actual_good_packets": 188,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 40000},
                {"item_id": self.oil.id, "actual_qty_base": 10500},
                {"item_id": self.spice.id, "actual_qty_base": 1200},
                {"item_id": self.pouch.id, "damaged_qty_base": 6},
                {"item_id": self.carton.id, "actual_qty_base": 9},
            ],
        }
        patch_resp = self.client.patch(f"/production/{run_id}", json=patch_payload, headers=prod_h)
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        # Step 4: Post run
        post_resp = self.client.post(f"/production/{run_id}/post", headers=prod_h)
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK)
        return run_id

    def test_section_5_costing_benchmark(self):
        """
        Verifies Section 5 Costing Benchmark:
        - Material cost:
          flour 40 kg x 43.125 = Rs 1,725.00
          oil 10.5 L x 140 = Rs 1,470.00
          spice 1.2 kg x 200 = Rs 240.00
          pouches 194 x 2.50 = Rs 485.00
          cartons 9 x 15 = Rs 135.00
          total Rs 4,055.00 (405500 paise).
        - Overheads: labour Rs 1,200 + gas/power Rs 600 = Rs 1,800.00 (180000 paise).
        - Total run cost Rs 5,855.00; good packets 188; cost per packet = 5855 / 188 = Rs 31.14 (31.1436...).
        - Material-only cost per packet Rs 21.57 (4055/188 = 21.5691...).
        - Margin vs Rs 50 selling price: Rs 18.86 per packet, 37.7%.
        - Cost of loss is non-zero because yield was 188 vs 200 expected;
          verify standard cost per packet (based on 200 packets) is lower than actual.
        """
        run_id = self._setup_benchmark_run()

        # Enter direct overheads: Labour Rs 1,200 (120,000 paise) + Gas Rs 600 (60,000 paise)
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        res_labour = self.client.post(
            "/overheads",
            json={
                "category": "LABOUR",
                "amount_paise": 120000,
                "production_run_id": run_id,
                "description": "Direct shift labour for Murukku run",
            },
            headers=prod_h,
        )
        self.assertEqual(res_labour.status_code, status.HTTP_201_CREATED)

        res_gas = self.client.post(
            "/overheads",
            json={
                "category": "GAS",
                "amount_paise": 60000,
                "production_run_id": run_id,
                "description": "LPG fuel consumption for frying",
            },
            headers=prod_h,
        )
        self.assertEqual(res_gas.status_code, status.HTTP_201_CREATED)

        # Retrieve Cost Breakdown as Accountant
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        cost_res = self.client.get(f"/costing/runs/{run_id}", headers=acct_h)
        self.assertEqual(cost_res.status_code, status.HTTP_200_OK)
        data = cost_res.json()

        # 1. Material Cost: Rs 4,055.00 (405,500 paise)
        self.assertEqual(data["material_cost_paise"], 405500)
        self.assertEqual(Decimal(str(data["material_cost_per_packet"])), Decimal("21.57"))

        # Verify line-by-line material breakdown
        mat_by_name = {m["item_name"]: m["value_paise"] for m in data["material_breakdown"]}
        self.assertEqual(mat_by_name["Flour"], 172500)       # 40 kg @ 43.125 = Rs 1,725.00
        self.assertEqual(mat_by_name["Cooking oil"], 147000) # 10.5 L @ 140 = Rs 1,470.00
        self.assertEqual(mat_by_name["Salt and spice mix"], 24000) # 1.2 kg @ 200 = Rs 240.00
        self.assertEqual(mat_by_name["200 g pouch"], 48500)  # 194 pcs @ 2.50 = Rs 485.00
        self.assertEqual(mat_by_name["Carton"], 13500)       # 9 pcs @ 15 = Rs 135.00

        # 2. Overheads: Labour 120,000 + Gas/Power 60,000 = 180,000 paise
        self.assertEqual(data["labour_paise"], 120000)
        self.assertEqual(data["gas_power_paise"], 60000)
        self.assertEqual(data["total_overheads_paise"], 180000)

        # 3. Total Run Cost: Rs 5,855.00 (585,500 paise)
        self.assertEqual(data["total_cost_paise"], 585500)
        self.assertEqual(data["good_packets"], 188)

        # 4. Cost Per Packet: 5855 / 188 = Rs 31.14 (31.1436...)
        self.assertEqual(Decimal(str(data["cost_per_packet"])), Decimal("31.14"))
        self.assertEqual(Decimal(str(data["cost_per_packet_4dp"])), Decimal("31.1436"))

        # 5. Planned Standard Cost & Cost of Loss
        # BOM planned for 200 pkts = 401,500 paise -> 2007.5 paise/pkt = Rs 20.075
        self.assertEqual(Decimal(str(data["planned_cost_per_packet"])), Decimal("20.0750"))
        # Standard cost per packet is lower than actual material cost per packet (20.0750 < 21.57)
        self.assertLess(Decimal(str(data["planned_cost_per_packet"])), Decimal(str(data["material_cost_per_packet"])))

        # Cost of loss is strictly non-zero (405,500 - 188 * 2007.5 = 28,090 paise)
        self.assertGreater(data["cost_of_loss_paise"], 0)
        self.assertEqual(data["cost_of_loss_paise"], 28090)

        # 6. Commercial Margin vs Rs 50 selling price
        summary_res = self.client.get(f"/costing/products?product_id={self.product.id}", headers=acct_h)
        self.assertEqual(summary_res.status_code, status.HTTP_200_OK)
        prod_data = summary_res.json()[0]

        self.assertEqual(Decimal(str(prod_data["selling_price"])), Decimal("50.00"))
        self.assertEqual(Decimal(str(prod_data["margin_per_packet"])), Decimal("18.86"))
        self.assertEqual(Decimal(str(prod_data["margin_pct"])), Decimal("37.7"))

    def test_monthly_overhead_allocation_with_remainder(self):
        """
        Monthly overhead with no run is split across two runs proportionally to good packets
        (e.g. 188 and 94 packets -> 2/3 and 1/3), and the parts sum exactly to the total
        (distributing the rounding remainder to the largest share so no paise is lost).
        """
        # Run 1: 188 good packets
        run1_id = self._setup_benchmark_run()

        # Run 2: 94 good packets (0.5 batch)
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        create_resp = self.client.post("/production", json={"product_id": self.product.id, "batches": "0.5000"}, headers=prod_h)
        run2_id = create_resp.json()["id"]

        patch_payload = {
            "actual_good_packets": 94,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 20000},
                {"item_id": self.oil.id, "actual_qty_base": 5000},
                {"item_id": self.spice.id, "actual_qty_base": 600},
                {"item_id": self.pouch.id, "damaged_qty_base": 3},
                {"item_id": self.carton.id, "actual_qty_base": 5},
            ],
        }
        self.client.patch(f"/production/{run2_id}", json=patch_payload, headers=prod_h)
        self.client.post(f"/production/{run2_id}/post", headers=prod_h)

        # Total good packets across both runs = 188 + 94 = 282 packets.
        # Ratio: Run 1 has 188/282 (2/3), Run 2 has 94/282 (1/3).
        # Post monthly electricity overhead of 10,000 paise (Rs 100.00) for the run's month
        run1 = self.db.get(ProductionRun, run1_id)
        run_month = run1.run_date.strftime("%Y-%m")

        res_power = self.client.post(
            "/overheads",
            json={
                "category": "POWER",
                "amount_paise": 10000,
                "month": run_month,
                "description": f"{run_month} Factory Electricity Bill",
            },
            headers=prod_h,
        )
        self.assertEqual(res_power.status_code, status.HTTP_201_CREATED)

        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        cost1 = self.client.get(f"/costing/runs/{run1_id}", headers=acct_h).json()
        cost2 = self.client.get(f"/costing/runs/{run2_id}", headers=acct_h).json()

        share1 = cost1["gas_power_paise"]
        share2 = cost2["gas_power_paise"]

        self.assertEqual(share1, 6667)
        self.assertEqual(share2, 3333)
        # Sums exactly to the total: 6667 + 3333 = 10000 (no paise lost)
        self.assertEqual(share1 + share2, 10000)

    def test_voiding_overhead_changes_cost_per_packet(self):
        """
        Voiding an overhead entry immediately triggers recomputation of cost per packet
        and logs audit trail.
        """
        run_id = self._setup_benchmark_run()
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}

        # Add Labour overhead 120,000 paise
        ovh_resp = self.client.post(
            "/overheads",
            json={"category": "LABOUR", "amount_paise": 120000, "production_run_id": run_id},
            headers=prod_h,
        )
        ovh_id = ovh_resp.json()["id"]

        cost_before = self.client.get(f"/costing/runs/{run_id}", headers=acct_h).json()
        self.assertEqual(cost_before["labour_paise"], 120000)
        self.assertEqual(Decimal(str(cost_before["cost_per_packet"])), Decimal("27.95")) # (405500 + 120000)/188 = 27.952...

        # Void the overhead entry (Admin only)
        void_resp = self.client.post(
            f"/overheads/{ovh_id}/void",
            json={"reason": "Incorrect shift timesheet booked against this run"},
            headers=admin_h,
        )
        self.assertEqual(void_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(void_resp.json()["status"], "VOIDED")

        # Cost per packet is recomputed back to material-only rate
        cost_after = self.client.get(f"/costing/runs/{run_id}", headers=acct_h).json()
        self.assertEqual(cost_after["labour_paise"], 0)
        self.assertEqual(cost_after["total_overheads_paise"], 0)
        self.assertEqual(Decimal(str(cost_after["cost_per_packet"])), Decimal("21.57")) # 405500/188 = 21.569...

    def test_product_summary_is_weighted_not_average_of_averages(self):
        """
        Product summary over two runs is a weighted figure, not the average of the two per-run costs:
        Run 1: 100 pkts @ total cost Rs 2,000 -> Rs 20.00 / pkt
        Run 2: 300 pkts @ total cost Rs 9,000 -> Rs 30.00 / pkt
        Unweighted average of per-run averages: (20.00 + 30.00) / 2 = Rs 25.00
        Weighted average: (2,000 + 9,000) / (100 + 300) = 11,000 / 400 = Rs 27.50
        Verify product summary yields Rs 27.50, differing from Rs 25.00!
        """
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}

        # Create Run 1: 100 good packets
        r1 = self.client.post("/production", json={"product_id": self.product.id, "batches": "1.0000"}, headers=prod_h).json()["id"]
        self.client.patch(f"/production/{r1}", json={
            "actual_good_packets": 100,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 20000}, # 20 kg @ 4.2 = 84000
                {"item_id": self.oil.id, "actual_qty_base": 5000},     # 5 L @ 14 = 70000
                {"item_id": self.spice.id, "actual_qty_base": 600},    # 0.6 kg @ 20 = 12000
                {"item_id": self.pouch.id, "actual_qty_base": 100},   # 100 @ 2.5 = 25000
                {"item_id": self.carton.id, "actual_qty_base": 6},     # 6 @ 15 = 9000 -> Total mat = 200,000 paise (Rs 2,000)
            ],
        }, headers=prod_h)
        self.client.post(f"/production/{r1}/post", headers=prod_h)

        # Create Run 2: 300 good packets, Total mat = 900,000 paise (Rs 9,000)
        # Add stock first for run 2
        post_movement(
            db=self.db, item_id=self.flour.id, movement_type=MovementType.PURCHASE,
            quantity_base=200000, unit_cost=Decimal("4.200000"), source_type="PURCHASE", source_id="PO-002", user=self.admin
        )
        post_movement(
            db=self.db, item_id=self.oil.id, movement_type=MovementType.PURCHASE,
            quantity_base=50000, unit_cost=Decimal("14.000000"), source_type="PURCHASE", source_id="PO-002", user=self.admin
        )
        post_movement(
            db=self.db, item_id=self.pouch.id, movement_type=MovementType.PURCHASE,
            quantity_base=1000, unit_cost=Decimal("250.000000"), source_type="PURCHASE", source_id="PO-002", user=self.admin
        )
        self.db.commit()

        r2 = self.client.post("/production", json={"product_id": self.product.id, "batches": "2.0000"}, headers=prod_h).json()["id"]
        self.client.patch(f"/production/{r2}", json={
            "actual_good_packets": 300,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 100000}, # 100 kg @ 4.2 = 420000
                {"item_id": self.oil.id, "actual_qty_base": 25000},    # 25 L @ 14 = 350000
                {"item_id": self.spice.id, "actual_qty_base": 1500},   # 1.5 kg @ 20 = 30000
                {"item_id": self.pouch.id, "actual_qty_base": 304},    # 304 @ 2.5 = 76000
                {"item_id": self.carton.id, "actual_qty_base": 16},    # 16 @ 15 = 24000 -> Total mat = 900,000 paise (Rs 9,000)
            ],
        }, headers=prod_h)
        self.client.post(f"/production/{r2}/post", headers=prod_h)

        # Run 1 cost per packet: 200,000 / 100 = Rs 20.00
        cost1 = self.client.get(f"/costing/runs/{r1}", headers=acct_h).json()
        self.assertEqual(Decimal(str(cost1["cost_per_packet"])), Decimal("20.00"))

        # Run 2 cost per packet: 900,000 / 300 = Rs 30.00
        cost2 = self.client.get(f"/costing/runs/{r2}", headers=acct_h).json()
        self.assertEqual(Decimal(str(cost2["cost_per_packet"])), Decimal("30.00"))

        # Product Cost Summary
        sum_resp = self.client.get(f"/costing/products?product_id={self.product.id}", headers=acct_h)
        self.assertEqual(sum_resp.status_code, status.HTTP_200_OK)
        summary = sum_resp.json()[0]

        # Total good packets: 100 + 300 = 400
        self.assertEqual(summary["good_packets"], 400)
        # Total cost: 200,000 + 900,000 = 1,100,000 paise (Rs 11,000)
        self.assertEqual(summary["total_cost_paise"], 1100000)
        # Weighted cost per packet: 11,000 / 400 = Rs 27.50
        self.assertEqual(Decimal(str(summary["cost_per_packet"])), Decimal("27.50"))
        # Verify it differs from the unweighted average of per-run costs ((20 + 30)/2 = 25.00)
        self.assertNotEqual(Decimal(str(summary["cost_per_packet"])), Decimal("25.00"))

    def test_costing_rbac_permissions(self):
        """
        Verify RBAC permissions:
        - ADMIN & PRODUCTION may enter overheads.
        - ADMIN may void overheads; PRODUCTION cannot void (403).
        - ACCOUNTANT, OWNER, ADMIN read costing.
        - SALESMAN has NO access to overheads or costing (403 Forbidden).
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        sales_h = {"Authorization": f"Bearer {self.sales_token}"}

        # 1. Salesman is rejected everywhere
        res1 = self.client.get("/overheads", headers=sales_h)
        self.assertEqual(res1.status_code, status.HTTP_403_FORBIDDEN)
        res2 = self.client.post("/overheads", json={"category": "LABOUR", "amount_paise": 1000}, headers=sales_h)
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)
        res3 = self.client.get("/costing/runs", headers=sales_h)
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)
        res4 = self.client.get("/costing/products", headers=sales_h)
        self.assertEqual(res4.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Production enters overhead
        ovh_res = self.client.post(
            "/overheads",
            json={"category": "OTHER", "amount_paise": 5000, "description": "Machine grease"},
            headers=prod_h,
        )
        self.assertEqual(ovh_res.status_code, status.HTTP_201_CREATED)
        ovh_id = ovh_res.json()["id"]

        # 3. Production CANNOT void overhead (ADMIN only)
        void_fail = self.client.post(f"/overheads/{ovh_id}/void", json={"reason": "Test void"}, headers=prod_h)
        self.assertEqual(void_fail.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Admin voids overhead
        void_ok = self.client.post(f"/overheads/{ovh_id}/void", json={"reason": "Admin test void"}, headers=admin_h)
        self.assertEqual(void_ok.status_code, status.HTTP_200_OK)

        # 5. Owner and Accountant read costing
        self.assertEqual(self.client.get("/costing/runs", headers=owner_h).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/costing/products", headers=acct_h).status_code, status.HTTP_200_OK)


if __name__ == "__main__":
    unittest.main()
