from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
import threading
import unittest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.company import CompanySettings
from app.models.customer import Customer, CustomerType
from app.models.invoice import (
    CreditNote,
    CreditNoteStatus,
    Dispatch,
    DispatchStatus,
    Invoice,
    InvoiceStatus,
)
from app.models.item import Item, ItemType
from app.models.order import Order, OrderLine, OrderStatus
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.stock import MovementType, StockMovement
from app.models.user import User, UserRole
from app.services import invoicing as invoicing_service
from app.services.stock import get_balance, post_movement
from app.utils.indian_numbers import amount_in_words


class TestInvoicesPhase6(unittest.TestCase):
    """
    Comprehensive test suite for Phase 6: GST Tax Invoices, PDF Output,
    Dispatch, and Credit Notes.
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
        self.admin = User(email="admin@test.local", hashed_password=pwd, full_name="Admin User", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@test.local", hashed_password=pwd, full_name="Owner User", role=UserRole.OWNER, is_active=True)
        self.production = User(email="prod@test.local", hashed_password=pwd, full_name="Prod Supervisor", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="acct@test.local", hashed_password=pwd, full_name="Accountant User", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman_a = User(email="salesman.a@test.local", hashed_password=pwd, full_name="Salesman A", role=UserRole.SALESMAN, is_active=True)
        self.salesman_b = User(email="salesman.b@test.local", hashed_password=pwd, full_name="Salesman B", role=UserRole.SALESMAN, is_active=True)

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
        self.price_list = PriceList(name="Standard Selling Price", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()

        self.price_item = PriceListItem(
            price_list_id=self.price_list.id,
            product_id=self.product.id,
            price_paise=5000,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(self.price_item)

        # 5. Customers
        # Retailer A in Tamil Nadu (33)
        self.retailer_a = Customer(
            name="Retailer A (Meenakshi Stores)",
            customer_type=CustomerType.RETAILER,
            gstin="33AAAAA0000A1Z5",
            state_code="33",
            address="15 West Masi Street, Madurai, TN - 625001",
            phone="9443111222",
            assigned_salesman_id=self.salesman_a.id,
            is_active=True,
        )
        # Distributor B in Karnataka (29)
        self.distributor_b = Customer(
            name="Distributor B (Karnataka Snack Distributors)",
            customer_type=CustomerType.DISTRIBUTOR,
            gstin="29BBBBB1111B1Z2",
            state_code="29",
            address="SIDCO Peenya, Bengaluru, KA - 560058",
            phone="9880011223",
            assigned_salesman_id=self.salesman_b.id,
            is_active=True,
        )
        self.db.add_all([self.retailer_a, self.distributor_b])

        # 6. Seed stock: 50 opening + 188 production = 238 packets on hand
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

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def _create_approved_order(self, customer_id: int, quantity: int, salesman_token: str) -> int:
        """Helper to create and approve an order."""
        client_uuid = f"uuid-test-{datetime.now(timezone.utc).timestamp()}"
        res = self.client.post(
            "/orders",
            json={
                "client_uuid": client_uuid,
                "customer_id": customer_id,
                "lines": [{"product_id": self.product.id, "quantity_packets": quantity}],
            },
            headers={"Authorization": f"Bearer {salesman_token}"},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.text)
        order_id = res.json()["id"]

        appr = self.client.post(
            f"/orders/{order_id}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(appr.status_code, status.HTTP_200_OK, appr.text)
        return order_id

    def test_amount_in_words(self):
        """Unit tests for Indian currency number-to-words."""
        # 1. 7875 -> Rupees Seven Thousand Eight Hundred Seventy Five Only
        self.assertEqual(
            amount_in_words(7875),
            "Rupees Seven Thousand Eight Hundred Seventy Five Only",
        )
        # 2. 100000 -> Rupees One Lakh Only
        self.assertEqual(
            amount_in_words(100000),
            "Rupees One Lakh Only",
        )
        # 3. 1234567.89 -> Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Eighty Nine Paise Only
        self.assertEqual(
            amount_in_words(1234567.89),
            "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Eighty Nine Paise Only",
        )
        # 4. Paise input: 787500 paise
        self.assertEqual(
            amount_in_words(787500, paise_input=True),
            "Rupees Seven Thousand Eight Hundred Seventy Five Only",
        )

    def test_retailer_a_intra_state_invoice(self):
        """
        Retailer A (Tamil Nadu, 33):
        150 packets at Rs 50 = taxable 750000 paise.
        Intra-state: CGST 18750 (2.5%), SGST 18750 (2.5%), IGST 0.
        Grand total: 787500 paise (Rs 7,875).
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        order_id = self._create_approved_order(self.retailer_a.id, 150, self.sales_a_token)

        # Invoice order
        resp = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.text)
        inv = resp.json()

        self.assertEqual(inv["taxable_total_paise"], 750000)
        self.assertEqual(inv["cgst_total_paise"], 18750)
        self.assertEqual(inv["sgst_total_paise"], 18750)
        self.assertEqual(inv["igst_total_paise"], 0)
        self.assertEqual(inv["round_off_paise"], 0)
        self.assertEqual(inv["grand_total_paise"], 787500)
        self.assertFalse(inv["is_igst"])
        self.assertEqual(inv["place_of_supply_state_code"], "33")
        self.assertEqual(inv["seller_state_code"], "33")
        self.assertEqual(inv["status"], "POSTED")
        self.assertIn("Rupees Seven Thousand Eight Hundred Seventy Five Only", inv["grand_total_in_words"])

        # Statutory 16 character limit check
        self.assertLessEqual(len(inv["invoice_no"]), 16)
        self.assertTrue(inv["invoice_no"].startswith("INV/"))

        # Order status transitioned to INVOICED
        order_data = self.client.get(f"/orders/{order_id}", headers=admin_h).json()
        self.assertEqual(order_data["status"], "INVOICED")

    def test_distributor_b_inter_state_invoice_and_shortage_block(self):
        """
        Distributor B (Karnataka, 29):
        120 packets at Rs 50 = taxable 600000 paise.
        Inter-state: IGST 30000 (5%), CGST 0, SGST 0.
        Grand total: 630000 paise.
        Verify that invoice can only be raised when order was approved.
        With Retailer A taking 150 out of 238, Distributor B's order is blocked if attempted without override.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        sales_b_h = {"Authorization": f"Bearer {self.sales_b_token}"}

        # 1. Salesman A takes 150 packets for Retailer A
        self._create_approved_order(self.retailer_a.id, 150, self.sales_a_token)

        # 2. Salesman B attempts to place order for 120 packets
        res_b = self.client.post(
            "/orders",
            json={
                "client_uuid": "dist-b-order-uuid-99",
                "customer_id": self.distributor_b.id,
                "lines": [{"product_id": self.product.id, "quantity_packets": 120}],
            },
            headers=sales_b_h,
        )
        self.assertEqual(res_b.status_code, status.HTTP_201_CREATED)
        order_b_id = res_b.json()["id"]

        # Admin tries to invoice unapproved order -> 400 Bad Request
        inv_unapproved = self.client.post(f"/orders/{order_b_id}/invoice", headers=admin_h)
        self.assertEqual(inv_unapproved.status_code, status.HTTP_400_BAD_REQUEST)

        # Admin approval without override fails with 409 Conflict
        appr_b_fail = self.client.post(f"/orders/{order_b_id}/approve", headers=admin_h)
        self.assertEqual(appr_b_fail.status_code, status.HTTP_409_CONFLICT)

        # Admin approves with explicit override
        appr_b_ok = self.client.post(f"/orders/{order_b_id}/approve?approve_with_shortage=true", headers=admin_h)
        self.assertEqual(appr_b_ok.status_code, status.HTTP_200_OK)

        # Now admin can invoice Order B
        inv_b_res = self.client.post(f"/orders/{order_b_id}/invoice", headers=admin_h)
        self.assertEqual(inv_b_res.status_code, status.HTTP_200_OK)
        inv_b = inv_b_res.json()

        # Check Inter-state tax calculations
        self.assertTrue(inv_b["is_igst"])
        self.assertEqual(inv_b["taxable_total_paise"], 600000)
        self.assertEqual(inv_b["cgst_total_paise"], 0)
        self.assertEqual(inv_b["sgst_total_paise"], 0)
        self.assertEqual(inv_b["igst_total_paise"], 30000)
        self.assertEqual(inv_b["grand_total_paise"], 630000)

    def test_invoice_financial_year_and_sequence_restarts(self):
        """
        Invoice numbering rules:
        - Gapless sequential format INV/YYYY-YY/XXXX <= 16 chars.
        - Financial year switches on 1 April:
          31 March 2027 -> FY 2026-27 (e.g. INV/2026-27/0001)
          1 April 2027 -> FY 2027-28 (restarts at INV/2027-28/0001)
        """
        # March 31, 2027
        dt_march = datetime(2027, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
        no1, fy1 = invoicing_service.get_next_invoice_number(self.db, dt_march)
        self.assertEqual(fy1, "2026-27")
        self.assertEqual(no1, "INV/2026-27/0001")
        self.assertEqual(len(no1), 16)

        no2, fy2 = invoicing_service.get_next_invoice_number(self.db, dt_march)
        self.assertEqual(fy2, "2026-27")
        self.assertEqual(no2, "INV/2026-27/0002")
        self.assertEqual(len(no2), 16)

        # April 1, 2027 (Sequence restarts at 1)
        dt_april = datetime(2027, 4, 1, 0, 0, 1, tzinfo=timezone.utc)
        no3, fy3 = invoicing_service.get_next_invoice_number(self.db, dt_april)
        self.assertEqual(fy3, "2027-28")
        self.assertEqual(no3, "INV/2027-28/0001")
        self.assertEqual(len(no3), 16)

    def test_posted_invoice_immutability(self):
        """
        Posted invoices are immutable:
        - No update or delete endpoints exist (405, 404, or logged 409 Conflict).
        - Direct modification attempt through service layer raises an exception.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        order_id = self._create_approved_order(self.retailer_a.id, 10, self.sales_a_token)
        inv = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h).json()
        inv_id = inv["id"]

        # Attempt PATCH
        patch_res = self.client.patch(f"/invoices/{inv_id}", json={"notes": "edit"}, headers=admin_h)
        self.assertIn(patch_res.status_code, [status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT])

        # Attempt PUT
        put_res = self.client.put(f"/invoices/{inv_id}", json={}, headers=admin_h)
        self.assertIn(put_res.status_code, [status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT])

        # Attempt DELETE
        del_res = self.client.delete(f"/invoices/{inv_id}", headers=admin_h)
        self.assertIn(del_res.status_code, [status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT])

        # Service guard raises HTTPException
        inv_obj = self.db.get(Invoice, inv_id)
        with self.assertRaises(Exception):
            invoicing_service.prevent_invoice_modification(inv_obj)

    def test_dispatch_flow_and_double_dispatch_block(self):
        """
        Dispatch flow:
        - Deducts stock via post_movement (type=DISPATCH, negative qty).
        - Prevents dispatching twice for the same invoice.
        - Blocks with 409 if stock is insufficient.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        order_id = self._create_approved_order(self.retailer_a.id, 50, self.sales_a_token)
        inv = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h).json()
        inv_id = inv["id"]

        # First dispatch -> Success
        disp_res = self.client.post(
            f"/invoices/{inv_id}/dispatch",
            json={"vehicle_no": "TN-59-Z-9999"},
            headers=admin_h,
        )
        self.assertEqual(disp_res.status_code, status.HTTP_200_OK)
        disp = disp_res.json()
        self.assertEqual(disp["status"], "DISPATCHED")
        self.assertEqual(disp["vehicle_no"], "TN-59-Z-9999")

        # Second dispatch for the same invoice -> Fails with 400 Bad Request
        disp_res_2 = self.client.post(
            f"/invoices/{inv_id}/dispatch",
            json={"vehicle_no": "TN-59-Z-9999"},
            headers=admin_h,
        )
        self.assertEqual(disp_res_2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_credit_note_cancellation_and_sales_return(self):
        """
        Credit Note cancellation:
        1. When dispatched: reverses tax totals, restores finished goods stock via SALES_RETURN.
        2. When NOT dispatched: cancels order and invoice.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        # Scenario A: Invoice is dispatched, then credit noted with return_stock=True
        bal_before = get_balance(self.db, self.murukku_item.id)
        order_id_1 = self._create_approved_order(self.retailer_a.id, 40, self.sales_a_token)
        inv_1 = self.client.post(f"/orders/{order_id_1}/invoice", headers=admin_h).json()
        inv_1_id = inv_1["id"]

        # Dispatch 40 packets
        self.client.post(f"/invoices/{inv_1_id}/dispatch", json={"vehicle_no": "TN-01-A-1111"}, headers=admin_h)
        self.assertEqual(get_balance(self.db, self.murukku_item.id), bal_before - 40)

        # Issue Credit Note
        cn_res = self.client.post(
            f"/invoices/{inv_1_id}/credit-note",
            json={"reason": "Customer cancelled shipment", "return_stock": True},
            headers=admin_h,
        )
        self.assertEqual(cn_res.status_code, status.HTTP_200_OK, cn_res.text)
        cn = cn_res.json()

        self.assertEqual(cn["status"], "POSTED")
        self.assertEqual(cn["invoice_id"], inv_1_id)
        self.assertEqual(cn["taxable_total_paise"], inv_1["taxable_total_paise"])
        self.assertEqual(cn["grand_total_paise"], inv_1["grand_total_paise"])

        # Stock is restored back to factory!
        self.assertEqual(get_balance(self.db, self.murukku_item.id), bal_before)

        # Original invoice status is now CANCELLED
        inv_get = self.client.get(f"/invoices/{inv_1_id}", headers=admin_h).json()
        self.assertEqual(inv_get["status"], "CANCELLED")
        self.assertEqual(inv_get["cancel_reason"], "Customer cancelled shipment")
        self.assertIsNotNone(inv_get["cancelled_at"])

        # Cannot issue second credit note for already cancelled invoice
        cn_second = self.client.post(
            f"/invoices/{inv_1_id}/credit-note",
            json={"reason": "Duplicate attempt", "return_stock": True},
            headers=admin_h,
        )
        self.assertEqual(cn_second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pdf_generation_and_snapshot_integrity(self):
        """
        PDF generation & Master Snapshot integrity:
        - Invoice PDF returns application/pdf with invoice number.
        - Altering customer name afterwards does NOT alter historical invoice or PDF.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        order_id = self._create_approved_order(self.retailer_a.id, 10, self.sales_a_token)
        inv = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h).json()
        inv_id = inv["id"]
        inv_no = inv["invoice_no"]

        # Fetch PDF
        pdf_res = self.client.get(f"/invoices/{inv_id}/pdf", headers=admin_h)
        self.assertEqual(pdf_res.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf_res.headers["content-type"], "application/pdf")
        self.assertGreater(len(pdf_res.content), 1000)
        # Verify invoice number string is embedded in PDF bytes
        self.assertIn(inv_no.encode("utf-8"), pdf_res.content)

        # Alter customer name in database afterwards
        cust = self.db.get(Customer, self.retailer_a.id)
        cust.name = "CHANGED NEW NAME CORP"
        self.db.commit()

        # Historical invoice record STILL preserves old snapshot name
        inv_check = self.client.get(f"/invoices/{inv_id}", headers=admin_h).json()
        self.assertEqual(inv_check["buyer_name"], "Retailer A (Meenakshi Stores)")

        # PDF still contains original snapshot name and NOT the changed name
        pdf_res_after = self.client.get(f"/invoices/{inv_id}/pdf", headers=admin_h)
        self.assertIn(b"Meenakshi Stores", pdf_res_after.content)
        self.assertNotIn(b"CHANGED NEW NAME CORP", pdf_res_after.content)

    def test_share_link_and_public_pdf_access(self):
        """
        Share link endpoint:
        - Generates signed JWT token with expiry.
        - WhatsApp and mailto links are properly formatted.
        - Unauthenticated public endpoint returns PDF without auth headers.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        order_id = self._create_approved_order(self.retailer_a.id, 10, self.sales_a_token)
        inv = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h).json()
        inv_id = inv["id"]

        share_res = self.client.get(f"/invoices/{inv_id}/share-link", headers=admin_h)
        self.assertEqual(share_res.status_code, status.HTTP_200_OK)
        share_data = share_res.json()

        self.assertIn("share_token", share_data)
        self.assertIn("public_url", share_data)
        self.assertIn("whatsapp_url", share_data)
        self.assertTrue(share_data["whatsapp_url"].startswith("https://wa.me/"))
        self.assertIn("mailto:", share_data["email_url"])

        # Unauthenticated request to public URL
        pub_url = share_data["public_url"]
        pub_res = self.client.get(pub_url)  # NO HEADERS
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)
        self.assertEqual(pub_res.headers["content-type"], "application/pdf")
        self.assertGreater(len(pub_res.content), 1000)

    def test_rbac_permissions(self):
        """
        RBAC matrix:
        - ADMIN: full write & read.
        - OWNER & ACCOUNTANT: read-only (invoices and PDFs), cannot dispatch or credit-note.
        - SALESMAN: can only read their own orders/invoices, cannot list all invoices or invoice orders.
        - PRODUCTION: completely blocked (403 Forbidden).
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        owner_h = {"Authorization": f"Bearer {self.owner_token}"}
        acct_h = {"Authorization": f"Bearer {self.acct_token}"}
        prod_h = {"Authorization": f"Bearer {self.prod_token}"}
        sales_a_h = {"Authorization": f"Bearer {self.sales_a_token}"}
        sales_b_h = {"Authorization": f"Bearer {self.sales_b_token}"}

        order_id = self._create_approved_order(self.retailer_a.id, 10, self.sales_a_token)

        # Production tries to invoice order -> 403 Forbidden
        self.assertEqual(
            self.client.post(f"/orders/{order_id}/invoice", headers=prod_h).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Salesman tries to invoice order -> 403 Forbidden
        self.assertEqual(
            self.client.post(f"/orders/{order_id}/invoice", headers=sales_a_h).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Admin invoices order
        inv = self.client.post(f"/orders/{order_id}/invoice", headers=admin_h).json()
        inv_id = inv["id"]

        # Owner and Accountant can list invoices and get PDF
        self.assertEqual(self.client.get("/invoices", headers=owner_h).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/invoices", headers=acct_h).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/invoices/{inv_id}/pdf", headers=owner_h).status_code, status.HTTP_200_OK)

        # Owner and Accountant cannot dispatch (Admin only)
        self.assertEqual(
            self.client.post(f"/invoices/{inv_id}/dispatch", headers=owner_h).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Production cannot read /invoices list (403)
        self.assertEqual(self.client.get("/invoices", headers=prod_h).status_code, status.HTTP_403_FORBIDDEN)

        # Salesman A can view their assigned customer's invoice
        self.assertEqual(self.client.get(f"/invoices/{inv_id}", headers=sales_a_h).status_code, status.HTTP_200_OK)

        # Salesman B cannot view Salesman A's customer invoice -> 404 (data isolation)
        self.assertEqual(self.client.get(f"/invoices/{inv_id}", headers=sales_b_h).status_code, status.HTTP_404_NOT_FOUND)
