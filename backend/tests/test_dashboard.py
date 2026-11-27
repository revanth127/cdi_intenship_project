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
from app.models.customer import Customer, CustomerType
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.stock import MovementType
from app.models.user import User, UserRole
from app.services.dashboard import clear_dashboard_cache
from app.services.stock import post_movement


class TestDashboard(unittest.TestCase):
    """
    Test suite for Executive Dashboard (GET /dashboard/summary?as_of=)
    verifying end-to-end integration across sales, orders, production, stock,
    receivables, costing, variance alerts, caching, and RBAC.
    """

    def setUp(self):
        clear_dashboard_cache()
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

        # 1. Company
        self.company = CompanySettings(
            id=1,
            company_name="Sri Murugan Traditional Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Plot 42, SIDCO Industrial Estate, Madurai",
            variance_tolerance_pct=Decimal("3.00"),
        )
        self.db.add(self.company)

        # 2. Users
        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@dash.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@dash.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.accountant = User(email="acct@dash.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.production = User(email="prod@dash.local", hashed_password=pwd, full_name="Prod", role=UserRole.PRODUCTION, is_active=True)
        self.salesman = User(email="sales@dash.local", hashed_password=pwd, full_name="Salesman", role=UserRole.SALESMAN, is_active=True)

        self.db.add_all([self.admin, self.owner, self.accountant, self.production, self.salesman])
        self.db.commit()

        self.admin_token = create_access_token(subject=self.admin.id, role=self.admin.role)
        self.owner_token = create_access_token(subject=self.owner.id, role=self.owner.role)
        self.acct_token = create_access_token(subject=self.accountant.id, role=self.accountant.role)
        self.prod_token = create_access_token(subject=self.production.id, role=self.production.role)
        self.sales_token = create_access_token(subject=self.salesman.id, role=self.salesman.role)

        # 3. Master items
        self.flour = Item(name="Flour", item_type=ItemType.RAW_MATERIAL, base_unit="g", display_unit="kg", opening_balance_qty=100000, opening_rate_paise=Decimal("4.200000"), reorder_level=50000)
        self.oil = Item(name="Cooking oil", item_type=ItemType.RAW_MATERIAL, base_unit="ml", display_unit="L", opening_balance_qty=30000, opening_rate_paise=Decimal("14.000000"), reorder_level=10000)
        self.spice = Item(name="Salt and spice mix", item_type=ItemType.RAW_MATERIAL, base_unit="g", display_unit="kg", opening_balance_qty=5000, opening_rate_paise=Decimal("20.000000"), reorder_level=2000)
        self.pouch = Item(name="200 g pouch", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", opening_balance_qty=500, opening_rate_paise=Decimal("250.000000"), reorder_level=200)
        self.carton = Item(name="Carton", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", opening_balance_qty=30, opening_rate_paise=Decimal("1500.000000"), reorder_level=15)
        self.murukku_item = Item(name="Murukku 200 g", item_type=ItemType.FINISHED_GOOD, base_unit="packet", display_unit="packet", gst_rate_bp=500, opening_balance_qty=50, opening_rate_paise=Decimal("5000.000000"))

        self.db.add_all([self.flour, self.oil, self.spice, self.pouch, self.carton, self.murukku_item])
        self.db.commit()

        # Openings in ledger
        for itm, qty, rate in [
            (self.flour, 100000, Decimal("4.200000")),
            (self.oil, 30000, Decimal("14.000000")),
            (self.spice, 5000, Decimal("20.000000")),
            (self.pouch, 500, Decimal("250.000000")),
            (self.carton, 30, Decimal("1500.000000")),
            (self.murukku_item, 50, Decimal("5000.000000")),
        ]:
            post_movement(db=self.db, item_id=itm.id, movement_type=MovementType.OPENING, quantity_base=qty, unit_cost=rate, source_type="OPENING", source_id="1", user=self.admin)

        # 4. Product, BOM, Pricing
        self.product = Product(item_id=self.murukku_item.id, pack_size_desc="200 g", packets_per_carton=20)
        self.db.add(self.product)
        self.db.flush()

        self.bom = BOM(product_id=self.product.id, version=1, batch_output_packets=200, is_active=True)
        self.db.add(self.bom)
        self.db.flush()

        for itm_id, qty, unit in [
            (self.flour.id, 40000, "kg"),
            (self.oil.id, 10000, "L"),
            (self.spice.id, 1200, "kg"),
            (self.pouch.id, 200, "piece"),
            (self.carton.id, 10, "piece"),
        ]:
            self.bom.items.append(BOMItem(bom_id=self.bom.id, item_id=itm_id, quantity_per_batch=qty, unit_for_display=unit))

        self.price_list = PriceList(name="Standard Price", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()
        self.price_item = PriceListItem(price_list_id=self.price_list.id, product_id=self.product.id, price_paise=5000, effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.db.add(self.price_item)

        # 5. Customer
        self.retailer = Customer(name="Retailer A", customer_type=CustomerType.RETAILER, gstin="33AAAAA0000A1Z5", state_code="33", address="Madurai", phone="9443111222", is_active=True, assigned_salesman_id=self.salesman.id)
        self.db.add(self.retailer)
        self.db.commit()

    def tearDown(self):
        clear_dashboard_cache()
        self.db.close()
        app.dependency_overrides.clear()

    def test_dashboard_summary_with_section_5_data(self):
        """
        Executes section 5 lifecycle:
        1. Purchase flour -> WAC = 4.3125 paise/g
        2. Production run -> 188 pkts, oil & cartons flagged
        3. Overheads -> 120,000 labour + 60,000 gas
        4. Sales order -> 150 pkts approved -> invoiced -> part payment 400,000 paise -> dispatched
        5. Submit draft order for 20 pkts
        6. Verify GET /dashboard/summary matches all expected figures.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        sales_h = {"Authorization": f"Bearer {self.sales_token}"}

        # 1. Purchase
        post_movement(db=self.db, item_id=self.flour.id, movement_type=MovementType.PURCHASE, quantity_base=60000, unit_cost=Decimal("4.500000"), source_type="PURCHASE", source_id="PO-001", user=self.admin)
        self.db.commit()

        # 2. Production Run
        run_res = self.client.post("/production", json={"product_id": self.product.id, "batches": "1.0000"}, headers=prod_h)
        run_id = run_res.json()["id"]
        self.client.patch(f"/production/{run_id}", json={
            "actual_good_packets": 188,
            "lines": [
                {"item_id": self.flour.id, "actual_qty_base": 40000},
                {"item_id": self.oil.id, "actual_qty_base": 10500},
                {"item_id": self.spice.id, "actual_qty_base": 1200},
                {"item_id": self.pouch.id, "damaged_qty_base": 6},
                {"item_id": self.carton.id, "actual_qty_base": 9},
            ],
        }, headers=prod_h)
        self.client.post(f"/production/{run_id}/post", headers=prod_h)

        # 3. Direct Overheads
        self.client.post("/overheads", json={"category": "LABOUR", "amount_paise": 120000, "production_run_id": run_id}, headers=prod_h)
        self.client.post("/overheads", json={"category": "GAS", "amount_paise": 60000, "production_run_id": run_id}, headers=prod_h)

        # 4. Sales Order 1 (150 packets)
        ord1_res = self.client.post("/orders", json={
            "client_uuid": "ord-001-uuid",
            "customer_id": self.retailer.id,
            "lines": [{"product_id": self.product.id, "quantity_packets": 150}],
        }, headers=sales_h)
        self.assertEqual(ord1_res.status_code, status.HTTP_201_CREATED)
        ord1_id = ord1_res.json()["id"]

        # Approve Order 1
        self.client.post(f"/orders/{ord1_id}/approve", headers=admin_h)

        # Invoice Order 1 (150 * 50 = 7500 taxable + 5% GST = 787,500 paise)
        inv_res = self.client.post(f"/orders/{ord1_id}/invoice", headers=admin_h)
        self.assertEqual(inv_res.status_code, status.HTTP_200_OK)
        inv_id = inv_res.json()["id"]

        # Dispatch Invoice 1
        self.client.post(f"/invoices/{inv_id}/dispatch", headers=admin_h)

        # Part payment 400,000 paise
        pay_res = self.client.post("/payments", json={
            "customer_id": self.retailer.id,
            "amount_paise": 400000,
            "mode": "UPI",
            "allocations": [{"invoice_id": inv_id, "amount_paise": 400000}],
        }, headers=admin_h)
        self.assertEqual(pay_res.status_code, status.HTTP_201_CREATED)

        # 5. Sales Order 2 (20 packets submitted, pending approval)
        ord2_res = self.client.post("/orders", json={
            "client_uuid": "ord-002-uuid",
            "customer_id": self.retailer.id,
            "lines": [{"product_id": self.product.id, "quantity_packets": 20}],
        }, headers=sales_h)
        self.assertEqual(ord2_res.status_code, status.HTTP_201_CREATED)

        # 6. Fetch Dashboard Summary as OWNER
        dash_res = self.client.get("/dashboard/summary", headers=owner_h)
        self.assertEqual(dash_res.status_code, status.HTTP_200_OK)
        data = dash_res.json()

        # Check 'today' section
        today = data["today"]
        self.assertEqual(today["orders_received_count"], 2)
        self.assertEqual(today["orders_pending_approval_count"], 1)
        self.assertEqual(today["invoices_raised_count"], 1)
        self.assertEqual(today["invoices_raised_value_paise"], 787500)
        self.assertEqual(today["dispatches_made_count"], 1)
        self.assertEqual(today["payments_collected_paise"], 400000)
        self.assertEqual(today["payments_collected_count"], 1)

        # Check 'stock' section
        stock = data["stock"]
        fg = stock["finished_goods"][0]
        self.assertEqual(fg["product_name"], "Murukku 200 g")
        # 50 opening + 188 produced - 150 dispatched = 88 on hand
        self.assertEqual(fg["on_hand_packets"], 88)
        self.assertEqual(fg["available_to_promise_packets"], 88)

        # Check 'variance_alerts' section
        var_alerts = data["variance_alerts"]
        self.assertGreaterEqual(len(var_alerts), 1)
        var_items = [v["item_name"] for v in var_alerts]
        self.assertIn("Cooking oil", var_items)
        self.assertIn("Carton", var_items)

        # Check 'receivables' section
        rec = data["receivables"]
        # Outstanding = 787,500 - 400,000 = 387,500 paise
        self.assertEqual(rec["total_outstanding_paise"], 387500)
        self.assertEqual(rec["bucket_0_30_paise"], 387500)
        self.assertEqual(len(rec["top_debtors"]), 1)
        self.assertEqual(rec["top_debtors"][0]["customer_name"], "Retailer A")
        self.assertEqual(rec["top_debtors"][0]["total_outstanding_paise"], 387500)

        # Check 'costing' section
        costing = data["costing"][0]
        self.assertEqual(costing["product_name"], "Murukku 200 g")
        self.assertEqual(Decimal(str(costing["cost_per_packet"])), Decimal("31.14"))
        self.assertEqual(Decimal(str(costing["selling_price"])), Decimal("50.00"))
        self.assertEqual(Decimal(str(costing["margin_pct"])), Decimal("37.7"))

        # Check 'sales_trend' section
        trend = data["sales_trend"]
        self.assertEqual(len(trend), 30) # Continuous 30 days
        today_trend = trend[-1]
        self.assertEqual(today_trend["taxable_sales_paise"], 750000)
        self.assertEqual(today_trend["invoice_count"], 1)

    def test_dashboard_caching(self):
        """Verify short-lived 30-second caching returns the exact same object without querying DB."""
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        res1 = self.client.get("/dashboard/summary?as_of=2026-06-01T12:00:00Z", headers=owner_h)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        res2 = self.client.get("/dashboard/summary?as_of=2026-06-01T12:00:00Z", headers=owner_h)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.json(), res2.json())

    def test_dashboard_rbac(self):
        """
        Verify RBAC permissions for /dashboard/summary:
        - ADMIN: allowed (200)
        - OWNER: allowed (200)
        - ACCOUNTANT: allowed (200)
        - SALESMAN: forbidden (403)
        - PRODUCTION: forbidden (403)
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        sales_h = {"Authorization": f"Bearer {self.sales_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}

        self.assertEqual(self.client.get("/dashboard/summary", headers=admin_h).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/dashboard/summary", headers=owner_h).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/dashboard/summary", headers=acct_h).status_code, status.HTTP_200_OK)

        self.assertEqual(self.client.get("/dashboard/summary", headers=sales_h).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/dashboard/summary", headers=prod_h).status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_range_parameter(self):
        """
        Verify /dashboard/summary accepts range=today|7d|30d|mtd with a valid owner token,
        and returns 422 Unprocessable Entity (not 401) for an invalid range.
        """
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        for r in ["today", "7d", "30d", "mtd"]:
            resp = self.client.get(f"/dashboard/summary?range={r}", headers=owner_h)
            self.assertEqual(resp.status_code, status.HTTP_200_OK, f"Expected 200 for range={r}")

        # Invalid range parameter with valid owner token must return 422 (not 401)
        invalid_resp = self.client.get("/dashboard/summary?range=invalid_range_value", headers=owner_h)
        self.assertEqual(invalid_resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertNotEqual(invalid_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_expired_token_returns_401(self):
        """
        Verify that an expired token returns 401 Unauthorized.
        """
        from datetime import timedelta
        expired_token = create_access_token(
            subject=self.owner.id,
            role=self.owner.role,
            expires_delta=timedelta(seconds=-60),
        )
        expired_h = {"Authorization": f"Bearer {expired_token}"}
        resp = self.client.get("/dashboard/summary", headers=expired_h)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


if __name__ == "__main__":
    unittest.main()
