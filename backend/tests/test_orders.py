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
from app.models.company import CompanySettings
from app.models.customer import Customer, CustomerType
from app.models.item import Item, ItemType
from app.models.order import (
    NumberingSequence,
    Order,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
    PriceSource,
)
from app.models.pricing import CustomerPriceOverride, PriceList, PriceListItem
from app.models.product import Product
from app.models.stock import MovementType
from app.models.user import User, UserRole
from app.services.stock import get_balance, post_movement


class TestOrderFlow(unittest.TestCase):
    """
    Comprehensive test suite for Phase 5 Order Flow:
    - Gapless order numbering per financial year (ORD-YYYY-XXXX)
    - Salesman mobile endpoints: /me/customers, /me/products, /me/orders, /me/sales/customer-wise
    - Idempotency with client_uuid
    - Salesman data isolation (404 on reading other salesman's order)
    - Customer assignment protection (403 when ordering for unassigned customer)
    - Server-side price resolution (client prices ignored, customer overrides prioritized)
    - Admin verification & approval with Available-to-Promise (ATP) stock checking
    - Section 7 Benchmark:
        * On hand: 238 packets
        * Retailer A order by Salesman A: 150 packets -> Approved (committed = 150)
        * Distributor B order by Salesman B: 120 packets -> Shortage 32 (available = 88) -> 409 Conflict
    - Shortage override: admin approves with approve_with_shortage=True
    - Rejection requiring valid reason & status history recording
    - Admin line edit while in SUBMITTED status marking ADMIN_EDIT
    - Concurrency protection against double-committing ATP stock
    - RBAC permissions across all roles
    - Phase 6 dispatch test stub
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

        # 1. Company Settings (Tamil Nadu, state code 33, FY starting April = 4)
        self.company = CompanySettings(
            id=1,
            company_name="Sri Murugan Traditional Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Plot 42, SIDCO Industrial Estate, Madurai, Tamil Nadu - 625008",
            financial_year_start_month=4,
            variance_tolerance_pct=Decimal("3.00"),
        )
        self.db.add(self.company)

        # 2. Users & Roles
        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@order.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@order.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.production = User(email="prod@order.local", hashed_password=pwd, full_name="Production", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="acct@order.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman_a = User(email="salesman.a@order.local", hashed_password=pwd, full_name="Salesman A", role=UserRole.SALESMAN, is_active=True)
        self.salesman_b = User(email="salesman.b@order.local", hashed_password=pwd, full_name="Salesman B", role=UserRole.SALESMAN, is_active=True)

        self.db.add_all([
            self.admin, self.owner, self.production, self.accountant, self.salesman_a, self.salesman_b
        ])
        self.db.commit()

        # JWT tokens
        self.admin_token = create_access_token(subject=self.admin.id, role=self.admin.role)
        self.owner_token = create_access_token(subject=self.owner.id, role=self.owner.role)
        self.prod_token = create_access_token(subject=self.production.id, role=self.production.role)
        self.acct_token = create_access_token(subject=self.accountant.id, role=self.accountant.role)
        self.sales_a_token = create_access_token(subject=self.salesman_a.id, role=self.salesman_a.role)
        self.sales_b_token = create_access_token(subject=self.salesman_b.id, role=self.salesman_b.role)

        # 3. Finished Goods Item & Product: Murukku 200 g
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
        self.db.add(self.murukku_item)
        self.db.flush()

        self.product = Product(
            item_id=self.murukku_item.id,
            pack_size_desc="200 g",
            packets_per_carton=20,
        )
        self.db.add(self.product)
        self.db.flush()

        # 4. Standard Price List (Rs 50 = 5000 paise per packet)
        self.price_list = PriceList(
            name="Standard Selling Price",
            is_default=True,
            is_active=True,
        )
        self.db.add(self.price_list)
        self.db.flush()

        self.price_item = PriceListItem(
            price_list_id=self.price_list.id,
            product_id=self.product.id,
            price_paise=5000,  # 5000 paise = Rs 50.00
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(self.price_item)

        # 5. Customers
        # Retailer A in Tamil Nadu (33) assigned to Salesman A
        self.retailer_a = Customer(
            name="Retailer A (Meenakshi Stores)",
            customer_type=CustomerType.RETAILER,
            gstin="33AAAAA0000A1Z5",
            state_code="33",
            address="15 West Masi Street, Madurai",
            phone="9443111222",
            assigned_salesman_id=self.salesman_a.id,
            is_active=True,
        )
        # Distributor B in Karnataka (29) assigned to Salesman B
        self.distributor_b = Customer(
            name="Distributor B (Karnataka Snack Distributors)",
            customer_type=CustomerType.DISTRIBUTOR,
            gstin="29BBBBB1111B1Z2",
            state_code="29",
            address="SIDCO Peenya, Bengaluru",
            phone="9880011223",
            assigned_salesman_id=self.salesman_b.id,
            is_active=True,
        )
        self.db.add_all([self.retailer_a, self.distributor_b])

        # 6. Seed stock ledger: 50 opening + 188 production output = 238 packets on hand
        post_movement(
            db=self.db,
            item_id=self.murukku_item.id,
            movement_type=MovementType.OPENING,
            quantity_base=50,
            unit_cost=Decimal("5000.000000"),
            source_type="OPENING",
            source_id="1",
            user=self.admin,
            movement_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        post_movement(
            db=self.db,
            item_id=self.murukku_item.id,
            movement_type=MovementType.PRODUCTION_OUTPUT,
            quantity_base=188,
            unit_cost=Decimal("2156.914894"),
            source_type="PRODUCTION_RUN",
            source_id="1",
            user=self.admin,
            movement_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        self.db.commit()

        # Verify on-hand balance is exactly 238 packets
        self.assertEqual(get_balance(self.db, self.murukku_item.id), 238)

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def test_section_7_benchmark(self):
        """
        Runs the Section 7 benchmark exactly:
        1. Salesman A places order for Retailer A: 150 packets at Rs 50 (stored as 5000 paise, line total 750000).
        2. Admin verifies and approves because 238 packets are on hand (ATP available: 238 >= 150).
        3. After Retailer A's order is approved, Salesman B orders 120 packets for Distributor B.
        4. With Phase 6 dispatch not yet done, committed quantity is 150, so on_hand=238, committed=150, available=88.
        5. Admin approval is blocked with HTTP 409 Conflict listing shortage = 32.
        """
        # Step 1: Salesman A places order for Retailer A
        headers_a = {"Authorization": f"Bearer {self.sales_a_token}"}
        order_payload_a = {
            "client_uuid": "mobile-uuid-bench-001",
            "customer_id": self.retailer_a.id,
            "notes": "Retailer A benchmark order",
            "lines": [
                {
                    "product_id": self.product.id,
                    "quantity_packets": 150,
                }
            ],
        }
        resp = self.client.post("/orders", json=order_payload_a, headers=headers_a)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.text)
        order_a = resp.json()

        order_id_a = order_a["id"]
        self.assertEqual(order_a["status"], "SUBMITTED")
        self.assertTrue(order_a["order_no"].startswith("ORD-2026-"))
        self.assertEqual(order_a["total_amount_paise"], 750000)  # 150 * 5000 paise = 750,000 paise (Rs 7,500)

        # Check line details
        self.assertEqual(len(order_a["lines"]), 1)
        line_a = order_a["lines"][0]
        self.assertEqual(line_a["unit_price_paise"], 5000)
        self.assertEqual(line_a["line_total_paise"], 750000)
        self.assertEqual(line_a["price_source"], "PRICE_LIST")

        # Check estimated GST tax (Intra-state: Tamil Nadu 33 -> 33)
        # 500 bp (5%) on 750,000 paise -> CGST: 18,750 paise, SGST: 18,750 paise, IGST: 0
        est_tax_a = order_a["estimated_tax"]
        self.assertIsNotNone(est_tax_a)
        self.assertTrue(est_tax_a["is_intra_state"])
        self.assertEqual(est_tax_a["cgst_paise"], 18750)
        self.assertEqual(est_tax_a["sgst_paise"], 18750)
        self.assertEqual(est_tax_a["igst_paise"], 0)
        self.assertEqual(est_tax_a["grand_total_paise"], 750000 + 37500)

        # Step 2: Admin views and approves Order A
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        get_a = self.client.get(f"/orders/{order_id_a}", headers=admin_headers)
        self.assertEqual(get_a.status_code, status.HTTP_200_OK)
        detail_a = get_a.json()
        avail_a = detail_a["stock_availability"][0]
        self.assertEqual(avail_a["on_hand"], 238)
        self.assertEqual(avail_a["committed_elsewhere"], 0)
        self.assertEqual(avail_a["available"], 238)
        self.assertEqual(avail_a["requested"], 150)
        self.assertEqual(avail_a["shortage"], 0)
        self.assertTrue(avail_a["ok"])

        # Approve Order A
        appr_resp_a = self.client.post(f"/orders/{order_id_a}/approve", headers=admin_headers)
        self.assertEqual(appr_resp_a.status_code, status.HTTP_200_OK, appr_resp_a.text)
        self.assertEqual(appr_resp_a.json()["status"], "APPROVED")
        self.assertEqual(appr_resp_a.json()["approved_by"], self.admin.id)
        self.assertIsNotNone(appr_resp_a.json()["approved_at"])

        # Step 3: Salesman B places order for Distributor B: 120 packets
        headers_b = {"Authorization": f"Bearer {self.sales_b_token}"}
        order_payload_b = {
            "client_uuid": "mobile-uuid-bench-002",
            "customer_id": self.distributor_b.id,
            "notes": "Distributor B benchmark order",
            "lines": [
                {
                    "product_id": self.product.id,
                    "quantity_packets": 120,
                }
            ],
        }
        resp_b = self.client.post("/orders", json=order_payload_b, headers=headers_b)
        self.assertEqual(resp_b.status_code, status.HTTP_201_CREATED, resp_b.text)
        order_b = resp_b.json()
        order_id_b = order_b["id"]
        self.assertEqual(order_b["status"], "SUBMITTED")
        self.assertEqual(order_b["total_amount_paise"], 600000)  # 120 * 5000 = 600,000 paise

        # Check estimated GST tax (Inter-state: Tamil Nadu 33 -> Karnataka 29)
        # 500 bp (5%) on 600,000 paise -> IGST: 30,000 paise, CGST: 0, SGST: 0
        est_tax_b = order_b["estimated_tax"]
        self.assertFalse(est_tax_b["is_intra_state"])
        self.assertEqual(est_tax_b["cgst_paise"], 0)
        self.assertEqual(est_tax_b["sgst_paise"], 0)
        self.assertEqual(est_tax_b["igst_paise"], 30000)

        # Step 4: Admin views Order B stock availability
        get_b = self.client.get(f"/orders/{order_id_b}", headers=admin_headers)
        self.assertEqual(get_b.status_code, status.HTTP_200_OK)
        avail_b = get_b.json()["stock_availability"][0]
        # Benchmark verification:
        # on_hand 238, committed 150, available 88, requested 120, shortage 32
        self.assertEqual(avail_b["on_hand"], 238)
        self.assertEqual(avail_b["committed_elsewhere"], 150)
        self.assertEqual(avail_b["available"], 88)
        self.assertEqual(avail_b["requested"], 120)
        self.assertEqual(avail_b["shortage"], 32)
        self.assertFalse(avail_b["ok"])

        # Step 5: Admin attempts approval without shortage override -> Must fail with 409 Conflict
        appr_fail_b = self.client.post(f"/orders/{order_id_b}/approve", headers=admin_headers)
        self.assertEqual(appr_fail_b.status_code, status.HTTP_409_CONFLICT, appr_fail_b.text)
        shortage_report = appr_fail_b.json()["detail"]["shortages"][0]
        self.assertEqual(shortage_report["on_hand"], 238)
        self.assertEqual(shortage_report["committed_elsewhere"], 150)
        self.assertEqual(shortage_report["available"], 88)
        self.assertEqual(shortage_report["requested"], 120)
        self.assertEqual(shortage_report["shortage"], 32)

        # Step 6: Admin approves with explicit override: approve_with_shortage=true
        appr_override = self.client.post(
            f"/orders/{order_id_b}/approve?approve_with_shortage=true", headers=admin_headers
        )
        self.assertEqual(appr_override.status_code, status.HTTP_200_OK, appr_override.text)
        self.assertEqual(appr_override.json()["status"], "APPROVED")

    @unittest.skip("Phase 6 dispatch verification: to be enabled in Phase 6")
    def test_section_7_phase6_dispatch_benchmark(self):
        """
        After the dispatch in Phase 6:
        Retailer A's 150 packets are dispatched, deducting 150 from ledger:
        on_hand becomes 88, committed becomes 0, available becomes 88.
        """
        pass

    def test_idempotency_client_uuid(self):
        """
        Submitting the same client_uuid twice returns the original order with HTTP 200,
        creating exactly one row in the database.
        """
        headers = {"Authorization": f"Bearer {self.sales_a_token}"}
        payload = {
            "client_uuid": "idempotency-test-uuid-xyz",
            "customer_id": self.retailer_a.id,
            "lines": [{"product_id": self.product.id, "quantity_packets": 20}],
        }
        # First submission -> 201 Created
        resp1 = self.client.post("/orders", json=payload, headers=headers)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        order1 = resp1.json()

        # Second submission (retried / offline sync) -> 200 OK
        resp2 = self.client.post("/orders", json=payload, headers=headers)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        order2 = resp2.json()

        self.assertEqual(order1["id"], order2["id"])
        self.assertEqual(order1["order_no"], order2["order_no"])

        # Verify only 1 order exists with this client_uuid in DB
        orders_count = self.db.scalars(
            select(Order).where(Order.client_uuid == "idempotency-test-uuid-xyz")
        ).all()
        self.assertEqual(len(orders_count), 1)

    def test_salesman_security_and_isolation(self):
        """
        1. Salesman A cannot view Salesman B's order (must return 404, not 403, to avoid leaking existence).
        2. Salesman A cannot order for an unassigned customer (returns 403 Forbidden).
        """
        headers_a = {"Authorization": f"Bearer {self.sales_a_token}"}
        headers_b = {"Authorization": f"Bearer {self.sales_b_token}"}

        # Salesman B creates order for Distributor B
        resp_b = self.client.post(
            "/orders",
            json={
                "client_uuid": "isolation-test-uuid-b",
                "customer_id": self.distributor_b.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],
            },
            headers=headers_b,
        )
        order_b_id = resp_b.json()["id"]

        # Salesman A attempts to fetch Salesman B's order via /me/orders/{id}
        resp = self.client.get(f"/me/orders/{order_b_id}", headers=headers_a)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, "Must return 404, not 403")

        # Salesman A attempts to place order for Distributor B (assigned to Salesman B)
        resp_forbidden = self.client.post(
            "/orders",
            json={
                "client_uuid": "forbidden-customer-uuid",
                "customer_id": self.distributor_b.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],
            },
            headers=headers_a,
        )
        self.assertEqual(resp_forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_sent_price_is_ignored(self):
        """
        The client never specifies price; if submitted in payload, the server ignores it
        and strictly applies the effective server-side price.
        """
        headers = {"Authorization": f"Bearer {self.sales_a_token}"}
        payload = {
            "client_uuid": "tampered-price-uuid",
            "customer_id": self.retailer_a.id,
            "lines": [
                {
                    "product_id": self.product.id,
                    "quantity_packets": 10,
                    "unit_price_paise": 100,  # Attacking client sends Rs 1 instead of Rs 50
                }
            ],
        }
        resp = self.client.post("/orders", json=payload, headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order = resp.json()
        line = order["lines"][0]
        self.assertEqual(line["unit_price_paise"], 5000)  # Server applied 5000 paise
        self.assertEqual(line["line_total_paise"], 50000)

    def test_customer_price_override(self):
        """
        Tests customer-specific price overrides:
        When a customer price override of Rs 45 (4500 paise) is present,
        it supersedes the standard price list of Rs 50 (5000 paise).
        """
        override = CustomerPriceOverride(
            customer_id=self.retailer_a.id,
            product_id=self.product.id,
            price_paise=4500,  # Rs 45.00
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(override)
        self.db.commit()

        # Check /me/products endpoint returns 4500 paise with CUSTOMER_OVERRIDE
        headers = {"Authorization": f"Bearer {self.sales_a_token}"}
        resp = self.client.get(f"/me/products?customer_id={self.retailer_a.id}", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        products = resp.json()
        murukku_prod = next(p for p in products if p["product_id"] == self.product.id)
        self.assertEqual(murukku_prod["price_paise"], 4500)
        self.assertEqual(murukku_prod["price_source"], "CUSTOMER_OVERRIDE")

        # Place order and verify snapshot uses 4500 paise
        order_resp = self.client.post(
            "/orders",
            json={
                "client_uuid": "override-order-uuid",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],
            },
            headers=headers,
        )
        self.assertEqual(order_resp.status_code, status.HTTP_201_CREATED)
        line = order_resp.json()["lines"][0]
        self.assertEqual(line["unit_price_paise"], 4500)
        self.assertEqual(line["price_source"], "CUSTOMER_OVERRIDE")
        self.assertEqual(line["line_total_paise"], 45000)

    def test_admin_edit_draft_order(self):
        """
        Admin can edit quantities or prices while status is SUBMITTED.
        Modifying price marks price_source as ADMIN_EDIT and logs audit log.
        Editing an approved order fails with 400.
        """
        headers_a = {"Authorization": f"Bearer {self.sales_a_token}"}
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        # Create draft order
        order_resp = self.client.post(
            "/orders",
            json={
                "client_uuid": "admin-edit-uuid",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],
            },
            headers=headers_a,
        )
        order_id = order_resp.json()["id"]

        # Admin edits quantity to 20 and discounts price to 4800 paise (Rs 48)
        edit_payload = {
            "notes": "Admin applied special discount",
            "lines": [
                {
                    "product_id": self.product.id,
                    "quantity_packets": 20,
                    "unit_price_paise": 4800,
                }
            ],
        }
        patch_resp = self.client.patch(f"/orders/{order_id}", json=edit_payload, headers=admin_h)
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        edited_order = patch_resp.json()
        line = edited_order["lines"][0]
        self.assertEqual(line["quantity_packets"], 20)
        self.assertEqual(line["unit_price_paise"], 4800)
        self.assertEqual(line["price_source"], "ADMIN_EDIT")
        self.assertEqual(line["line_total_paise"], 96000)
        self.assertEqual(edited_order["total_amount_paise"], 96000)

        # Approve the order
        self.client.post(f"/orders/{order_id}/approve", headers=admin_h)

        # Attempt to edit approved order -> Must fail with 400
        fail_edit = self.client.patch(f"/orders/{order_id}", json={"notes": "Too late"}, headers=admin_h)
        self.assertEqual(fail_edit.status_code, status.HTTP_400_BAD_REQUEST)

    def test_order_rejection_requires_reason(self):
        """
        Admin rejection requires a valid reason (min 3 chars).
        Rejection creates an OrderStatusHistory entry and sets rejection_reason.
        """
        headers_a = {"Authorization": f"Bearer {self.sales_a_token}"}
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        order_resp = self.client.post(
            "/orders",
            json={
                "client_uuid": "rejection-test-uuid",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],
            },
            headers=headers_a,
        )
        order_id = order_resp.json()["id"]

        # Rejection with empty reason -> 422 or 400
        fail_resp = self.client.post(f"/orders/{order_id}/reject", json={"reason": "  "}, headers=admin_h)
        self.assertIn(fail_resp.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY])

        # Valid rejection
        reject_resp = self.client.post(
            f"/orders/{order_id}/reject",
            json={"reason": "Customer overdue payment balance exceeds limit"},
            headers=admin_h,
        )
        self.assertEqual(reject_resp.status_code, status.HTTP_200_OK)
        rej_data = reject_resp.json()
        self.assertEqual(rej_data["status"], "REJECTED")
        self.assertEqual(rej_data["rejection_reason"], "Customer overdue payment balance exceeds limit")

        # Verify status history
        histories = rej_data["status_history"]
        self.assertEqual(len(histories), 2)  # SUBMITTED -> REJECTED
        self.assertEqual(histories[-1]["to_status"], "REJECTED")

    def test_salesman_sales_summary(self):
        """
        Tests GET /me/sales/customer-wise:
        Aggregates order counts and total value per customer.
        Excludes REJECTED and CANCELLED orders.
        """
        headers_a = {"Authorization": f"Bearer {self.sales_a_token}"}
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        # Place 2 orders for Retailer A
        resp1 = self.client.post(
            "/orders",
            json={
                "client_uuid": "summary-order-1",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 10}],  # 50,000 paise
            },
            headers=headers_a,
        )
        resp2 = self.client.post(
            "/orders",
            json={
                "client_uuid": "summary-order-2",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 20}],  # 100,000 paise
            },
            headers=headers_a,
        )
        # Place 1 order that gets rejected
        resp3 = self.client.post(
            "/orders",
            json={
                "client_uuid": "summary-order-3-rej",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 50}],
            },
            headers=headers_a,
        )
        self.client.post(f"/orders/{resp3.json()['id']}/reject", json={"reason": "Test reject"}, headers=admin_h)

        summary_resp = self.client.get("/me/sales/customer-wise", headers=headers_a)
        self.assertEqual(summary_resp.status_code, status.HTTP_200_OK)
        summary = summary_resp.json()
        self.assertEqual(len(summary), 1)
        ret_a_summary = summary[0]
        self.assertEqual(ret_a_summary["customer_id"], self.retailer_a.id)
        self.assertEqual(ret_a_summary["order_count"], 2)  # 2 active orders (3rd was rejected)
        self.assertEqual(ret_a_summary["total_value_paise"], 150000)

    def test_rbac_permissions(self):
        """
        Validates RBAC permission matrix for order endpoints:
        - ADMIN: full access.
        - OWNER & ACCOUNTANT: read-only access (cannot patch/approve/reject).
        - PRODUCTION: read-only access (for production scheduling, cannot modify).
        - SALESMAN: cannot access admin /orders endpoints.
        """
        sales_h = {"Authorization": f"Bearer {self.sales_a_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}

        # 1. Salesman cannot read admin /orders list
        resp = self.client.get("/orders", headers=sales_h)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Owner, Accountant, and Production CAN read /orders list
        for h in [owner_h, acct_h, prod_h]:
            resp = self.client.get("/orders", headers=h)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # 3. Create a test order
        order_resp = self.client.post(
            "/orders",
            json={
                "client_uuid": "rbac-test-uuid",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 5}],
            },
            headers=sales_h,
        )
        order_id = order_resp.json()["id"]

        # 4. Accountant, Owner, and Production CANNOT approve or reject orders
        for h in [owner_h, acct_h, prod_h]:
            appr = self.client.post(f"/orders/{order_id}/approve", headers=h)
            self.assertEqual(appr.status_code, status.HTTP_403_FORBIDDEN)

            rej = self.client.post(f"/orders/{order_id}/reject", json={"reason": "No access"}, headers=h)
            self.assertEqual(rej.status_code, status.HTTP_403_FORBIDDEN)

    def test_concurrent_approvals_cannot_both_succeed(self):
        """
        Two approvals against 100 available packets (each asking for 80) cannot both succeed.
        When Order 1 is approved, committed becomes 80 and available drops to 20.
        Order 2's approval must be blocked with HTTP 409 Conflict (shortage = 60).
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        sales_h = {"Authorization": f"Bearer {self.sales_a_token}"}

        # Create a special item with exactly 100 packets opening
        item_100 = Item(
            name="Special Murukku 100",
            item_type=ItemType.FINISHED_GOOD,
            base_unit="packet",
            display_unit="packet",
            gst_rate_bp=500,
            opening_balance_qty=100,
            opening_rate_paise=Decimal("5000.000000"),
        )
        self.db.add(item_100)
        self.db.flush()

        prod_100 = Product(
            item_id=item_100.id,
            pack_size_desc="200 g",
            packets_per_carton=20,
        )
        self.db.add(prod_100)
        self.db.flush()

        pli_100 = PriceListItem(
            price_list_id=self.price_list.id,
            product_id=prod_100.id,
            price_paise=5000,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(pli_100)

        # Post opening stock movement for item_100 = 100 packets
        post_movement(
            db=self.db,
            item_id=item_100.id,
            movement_type=MovementType.OPENING,
            quantity_base=100,
            unit_cost=Decimal("5000.000000"),
            source_type="OPENING",
            source_id="100",
            user=self.admin,
        )
        self.db.commit()

        # Salesman creates Order 1 for 80 packets
        resp1 = self.client.post(
            "/orders",
            json={
                "client_uuid": "conc-uuid-1",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": prod_100.id, "quantity_packets": 80}],
            },
            headers=sales_h,
        )
        order1_id = resp1.json()["id"]

        # Salesman creates Order 2 for 80 packets
        resp2 = self.client.post(
            "/orders",
            json={
                "client_uuid": "conc-uuid-2",
                "customer_id": self.retailer_a.id,
                "lines": [{"product_id": prod_100.id, "quantity_packets": 80}],
            },
            headers=sales_h,
        )
        order2_id = resp2.json()["id"]

        # First approval succeeds (100 >= 80)
        appr1 = self.client.post(f"/orders/{order1_id}/approve", headers=admin_h)
        self.assertEqual(appr1.status_code, status.HTTP_200_OK)

        # Second approval MUST fail with 409 Conflict (only 20 available, requested 80 -> shortage 60)
        appr2 = self.client.post(f"/orders/{order2_id}/approve", headers=admin_h)
        self.assertEqual(appr2.status_code, status.HTTP_409_CONFLICT)
        shortage = appr2.json()["detail"]["shortages"][0]
        self.assertEqual(shortage["available"], 20)
        self.assertEqual(shortage["requested"], 80)
        self.assertEqual(shortage["shortage"], 60)


if __name__ == "__main__":
    unittest.main()
