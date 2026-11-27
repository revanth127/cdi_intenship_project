from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import sys
from typing import Optional
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
from app.models.invoice import CreditNote, Invoice, InvoiceLine, InvoiceStatus
from app.models.item import Item, ItemType
from app.models.order import Order, OrderLine, OrderStatus
from app.models.payment import Payment, PaymentAllocation, PaymentMode, PaymentStatus
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.stock import MovementType
from app.models.user import User, UserRole
from app.services import invoicing as invoicing_service
from app.services import receivables as receivables_service
from app.services.stock import post_movement


class TestReceivablesPhase7(unittest.TestCase):
    """
    Test suite for Phase 7: Customer Payments, Allocations,
    Outstanding Balances, Customer Statements, and Receivables Ageing.
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
            financial_year_start_month=4,
            variance_tolerance_pct=Decimal("3.00"),
        )
        self.db.add(self.company)

        # 2. Users & Roles
        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@rec.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@rec.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.production = User(email="prod@rec.local", hashed_password=pwd, full_name="Prod", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="acct@rec.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman_a = User(email="salesman.a@rec.local", hashed_password=pwd, full_name="Salesman A", role=UserRole.SALESMAN, is_active=True)
        self.salesman_b = User(email="salesman.b@rec.local", hashed_password=pwd, full_name="Salesman B", role=UserRole.SALESMAN, is_active=True)

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

        # 3. Item, Product & Pricing
        self.murukku_item = Item(
            name="Murukku 200 g",
            item_type=ItemType.FINISHED_GOOD,
            base_unit="packet",
            display_unit="packet",
            hsn_code="1905",
            gst_rate_bp=500,  # 5% GST
            opening_balance_qty=1000,
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

        self.price_list = PriceList(name="Standard Selling Price", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()

        self.price_item = PriceListItem(
            price_list_id=self.price_list.id,
            product_id=self.product.id,
            price_paise=5000,  # Rs 50
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.add(self.price_item)

        # 4. Customers
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

        # 5. Inventory
        post_movement(
            db=self.db,
            item_id=self.murukku_item.id,
            movement_type=MovementType.OPENING,
            quantity_base=1000,
            unit_cost=Decimal("5000.000000"),
            source_type="OPENING",
            source_id="1",
            user=self.admin,
            movement_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def _create_invoice(self, customer_id: int, quantity: int, inv_date: Optional[datetime] = None) -> Invoice:
        """Helper to create an invoice directly for testing."""
        client_uuid = f"uuid-{datetime.now(timezone.utc).timestamp()}-{quantity}"
        order_res = self.client.post(
            "/orders",
            json={
                "client_uuid": client_uuid,
                "customer_id": customer_id,
                "lines": [{"product_id": self.product.id, "quantity_packets": quantity}],
            },
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(order_res.status_code, status.HTTP_201_CREATED, order_res.text)
        order_id = order_res.json()["id"]

        # Approve
        self.client.post(f"/orders/{order_id}/approve", headers={"Authorization": f"Bearer {self.admin_token}"})

        # Invoice
        inv_res = self.client.post(f"/orders/{order_id}/invoice", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(inv_res.status_code, status.HTTP_200_OK, inv_res.text)
        inv_id = inv_res.json()["id"]

        inv = self.db.get(Invoice, inv_id)
        if inv_date:
            inv.invoice_date = inv_date
            self.db.commit()
            self.db.refresh(inv)
        return inv

    def test_benchmark_part_payment_and_outstanding(self):
        """
        Retailer A invoice 787500 paise (150 pkts @ Rs 50 + 5% GST = Rs 7,875).
        Payment 400000 paise (Rs 4,000).
        - Invoice outstanding becomes 387500 paise (Rs 3,875).
        - Customer outstanding becomes 387500 paise.
        """
        inv = self._create_invoice(self.retailer_a.id, 150)
        self.assertEqual(inv.grand_total_paise, 787500)

        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        pay_res = self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 400000,
                "mode": "UPI",
                "reference_no": "UPI-REF-001",
                "allocations": [{"invoice_id": inv.id, "amount_paise": 400000}],
            },
            headers=admin_h,
        )
        self.assertEqual(pay_res.status_code, status.HTTP_201_CREATED, pay_res.text)
        pay_data = pay_res.json()
        self.assertEqual(pay_data["allocated_paise"], 400000)
        self.assertEqual(pay_data["unallocated_advance_paise"], 0)
        self.assertTrue(pay_data["receipt_no"].startswith("RCT/"))

        # Verify Invoice and Customer Outstandings
        out_res = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h)
        self.assertEqual(out_res.status_code, status.HTTP_200_OK)
        out_data = out_res.json()

        self.assertEqual(out_data["open_invoices_outstanding_paise"], 387500)
        self.assertEqual(out_data["unallocated_advance_paise"], 0)
        self.assertEqual(out_data["total_outstanding_paise"], 387500)
        self.assertEqual(len(out_data["invoices"]), 1)
        self.assertEqual(out_data["invoices"][0]["outstanding_paise"], 387500)

    def test_payment_greater_than_outstanding_becomes_advance(self):
        """
        Payment greater than outstanding:
        Invoice = 52500 paise (10 pkts).
        Payment = 100000 paise (Rs 1,000).
        Excess (47500 paise) becomes ADVANCE.
        Customer balance becomes -47500 (credit balance, shown clearly).
        """
        inv = self._create_invoice(self.retailer_a.id, 10)
        self.assertEqual(inv.grand_total_paise, 52500)

        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        pay_res = self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 100000,
                "mode": "BANK",
                "reference_no": "IMPS123456",
                # Auto-allocation omitted -> auto-allocates 52500, rest is advance
            },
            headers=admin_h,
        )
        self.assertEqual(pay_res.status_code, status.HTTP_201_CREATED)
        pay_data = pay_res.json()
        self.assertEqual(pay_data["allocated_paise"], 52500)
        self.assertEqual(pay_data["unallocated_advance_paise"], 47500)

        # Customer balance check
        out_res = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h)
        out_data = out_res.json()
        self.assertEqual(out_data["open_invoices_outstanding_paise"], 0)
        self.assertEqual(out_data["unallocated_advance_paise"], 47500)
        self.assertEqual(out_data["total_outstanding_paise"], -47500)  # Negative credit balance

    def test_over_allocation_rejected_with_409(self):
        """
        Over-allocating to an invoice beyond its current outstanding is rejected with 409 Conflict.
        """
        inv = self._create_invoice(self.retailer_a.id, 10)  # grand_total = 52500 paise
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        pay_fail = self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 60000,
                "mode": "CASH",
                "allocations": [{"invoice_id": inv.id, "amount_paise": 60000}],  # 60000 > 52500
            },
            headers=admin_h,
        )
        self.assertEqual(pay_fail.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("exceeds current outstanding", pay_fail.json()["detail"])

    def test_fifo_auto_allocation_across_three_invoices(self):
        """
        FIFO Auto-allocation across 3 chronological invoices:
        Inv 1: 10 pkts = 52500 paise
        Inv 2: 20 pkts = 105000 paise
        Inv 3: 30 pkts = 157500 paise
        Total = 315000 paise
        Payment: 200000 paise
        Auto-allocation:
          Inv 1: 52500 (fully paid, outstanding 0)
          Inv 2: 105000 (fully paid, outstanding 0)
          Inv 3: 42500 (partially paid, outstanding = 157500 - 42500 = 115000)
        """
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 10, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 20, tzinfo=timezone.utc)

        inv1 = self._create_invoice(self.retailer_a.id, 10, inv_date=t1)
        inv2 = self._create_invoice(self.retailer_a.id, 20, inv_date=t2)
        inv3 = self._create_invoice(self.retailer_a.id, 30, inv_date=t3)

        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        pay_res = self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 200000,
                "mode": "BANK",
            },
            headers=admin_h,
        )
        self.assertEqual(pay_res.status_code, status.HTTP_201_CREATED)
        pay_data = pay_res.json()
        allocs = {a["invoice_id"]: a["amount_paise"] for a in pay_data["allocations"]}

        self.assertEqual(allocs[inv1.id], 52500)
        self.assertEqual(allocs[inv2.id], 105000)
        self.assertEqual(allocs[inv3.id], 42500)

        # Check outstanding on Inv 3
        out_res = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h)
        out_data = out_res.json()
        self.assertEqual(len(out_data["invoices"]), 1)  # Only Inv 3 is open
        self.assertEqual(out_data["invoices"][0]["invoice_id"], inv3.id)
        self.assertEqual(out_data["invoices"][0]["outstanding_paise"], 115000)

    def test_payment_reversal_restores_outstanding(self):
        """
        Reversing a payment:
        - Marks status REVERSED.
        - Keeps payment row and allocation links for audit trail.
        - Restores invoice and customer outstanding balances exactly.
        - Logs audit trail entry.
        """
        inv = self._create_invoice(self.retailer_a.id, 20)  # 105000 paise
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        # Make payment
        pay = self.client.post(
            "/payments",
            json={"customer_id": self.retailer_a.id, "amount_paise": 105000, "mode": "UPI"},
            headers=admin_h,
        ).json()
        pay_id = pay["id"]

        # Outstanding is 0
        out_1 = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h).json()
        self.assertEqual(out_1["total_outstanding_paise"], 0)

        # Reverse payment
        rev_res = self.client.post(
            f"/payments/{pay_id}/reverse",
            json={"reason": "Customer cheque bounced / reversal requested"},
            headers=admin_h,
        )
        self.assertEqual(rev_res.status_code, status.HTTP_200_OK)
        rev_data = rev_res.json()
        self.assertEqual(rev_data["status"], "REVERSED")
        self.assertEqual(rev_data["reverse_reason"], "Customer cheque bounced / reversal requested")
        self.assertIsNotNone(rev_data["reversed_at"])

        # Outstanding is restored to 105000 paise
        out_2 = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h).json()
        self.assertEqual(out_2["total_outstanding_paise"], 105000)
        self.assertEqual(out_2["invoices"][0]["outstanding_paise"], 105000)

    def test_credit_note_after_part_payment_reduces_outstanding(self):
        """
        Credit note after a part payment:
        Inv = 105000 paise.
        Part payment = 40000 paise -> Outstanding = 65000 paise.
        Credit Note issued for invoice (cancels invoice / reverses remaining tax).
        Outstanding becomes 0, and the paid 40000 paise becomes unallocated customer ADVANCE!
        """
        inv = self._create_invoice(self.retailer_a.id, 20)  # 105000 paise
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}

        # Part payment 40000
        self.client.post(
            "/payments",
            json={"customer_id": self.retailer_a.id, "amount_paise": 40000, "mode": "CASH"},
            headers=admin_h,
        )

        # Issue Credit Note to cancel invoice
        cn_res = self.client.post(
            f"/invoices/{inv.id}/credit-note",
            json={"reason": "Customer cancelled order completely", "return_stock": False},
            headers=admin_h,
        )
        self.assertEqual(cn_res.status_code, status.HTTP_200_OK)

        # Outstanding check
        out = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=admin_h).json()
        self.assertEqual(out["open_invoices_outstanding_paise"], 0)
        self.assertEqual(out["unallocated_advance_paise"], 40000)
        self.assertEqual(out["total_outstanding_paise"], -40000)  # Customer has 40000 paise in advance credit

    def test_ageing_boundaries_and_past_as_of(self):
        """
        Ageing buckets:
        - 0-30 days (day 30 belongs to 0-30 bucket)
        - 31-60 days
        - 61-90 days
        - 90+ days
        Past as_of ignores later transactions.
        """
        as_of_date = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Create invoices with exact day offsets from 2026-06-01:
        # Day 30: 2026-05-02 -> bucket 0-30
        inv_30 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=30))
        # Day 31: 2026-05-01 -> bucket 31-60
        inv_31 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=31))
        # Day 60: 2026-04-02 -> bucket 31-60
        inv_60 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=60))
        # Day 61: 2026-04-01 -> bucket 61-90
        inv_61 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=61))
        # Day 90: 2026-03-03 -> bucket 61-90
        inv_90 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=90))
        # Day 91: 2026-03-02 -> bucket 90+
        inv_91 = self._create_invoice(self.retailer_a.id, 10, inv_date=as_of_date - timedelta(days=91))

        # Each invoice for 10 pkts = 52500 paise
        amt = 52500

        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        ageing_res = self.client.get(
            f"/receivables/ageing?as_of={as_of_date.isoformat()}&customer_id={self.retailer_a.id}",
            headers=admin_h,
        )
        self.assertEqual(ageing_res.status_code, status.HTTP_200_OK)
        data = ageing_res.json()
        row = data["customers"][0]

        # Verify bucket placement:
        # 0-30 days: inv_30 (52500)
        self.assertEqual(row["bucket_0_30_paise"], amt)
        # 31-60 days: inv_31 + inv_60 = 2 * 52500 = 105000
        self.assertEqual(row["bucket_31_60_paise"], amt * 2)
        # 61-90 days: inv_61 + inv_90 = 2 * 52500 = 105000
        self.assertEqual(row["bucket_61_90_paise"], amt * 2)
        # 90+ days: inv_91 = 52500
        self.assertEqual(row["bucket_90_plus_paise"], amt)

        self.assertEqual(row["gross_outstanding_paise"], amt * 6)
        self.assertEqual(row["total_outstanding_paise"], amt * 6)

        # Later payment (on 2026-07-01) is ignored when as_of is 2026-06-01
        self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": amt * 6,
                "mode": "BANK",
                "payment_date": (as_of_date + timedelta(days=30)).isoformat(),
            },
            headers=admin_h,
        )

        # Re-fetch as of 2026-06-01: later payment is ignored
        ageing_past = self.client.get(
            f"/receivables/ageing?as_of={as_of_date.isoformat()}&customer_id={self.retailer_a.id}",
            headers=admin_h,
        ).json()
        row_past = ageing_past["customers"][0]
        self.assertEqual(row_past["total_outstanding_paise"], amt * 6)

    def test_customer_statement_closing_balance_matches_outstanding(self):
        """
        Statement of Account:
        Opening balance + debits - credits == closing balance == customer_outstanding.
        """
        admin_h = {"Authorization": f"Bearer {self.admin_token}"}
        base_time = datetime(2026, 2, 1, tzinfo=timezone.utc)

        # Period 1 (prior to statement window): Invoice 52500, Payment 20000 -> Opening = 32500
        self._create_invoice(self.retailer_a.id, 10, inv_date=base_time)
        self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 20000,
                "mode": "CASH",
                "payment_date": (base_time + timedelta(days=1)).isoformat(),
            },
            headers=admin_h,
        )

        # Statement window: 2026-03-01 to 2026-04-01
        start_w = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end_w = datetime(2026, 4, 1, tzinfo=timezone.utc)

        # Transaction 1: Invoice on 2026-03-05 = 105000 paise
        self._create_invoice(self.retailer_a.id, 20, inv_date=start_w + timedelta(days=4))
        # Transaction 2: Payment on 2026-03-15 = 50000 paise
        self.client.post(
            "/payments",
            json={
                "customer_id": self.retailer_a.id,
                "amount_paise": 50000,
                "mode": "UPI",
                "payment_date": (start_w + timedelta(days=14)).isoformat(),
            },
            headers=admin_h,
        )

        stmt_res = self.client.get(
            f"/customers/{self.retailer_a.id}/statement?from={start_w.isoformat()}&to={end_w.isoformat()}",
            headers=admin_h,
        )
        self.assertEqual(stmt_res.status_code, status.HTTP_200_OK)
        stmt = stmt_res.json()

        self.assertEqual(stmt["opening_balance_paise"], 32500)
        self.assertEqual(stmt["total_debits_paise"], 105000)
        self.assertEqual(stmt["total_credits_paise"], 50000)
        expected_closing = 32500 + 105000 - 50000  # 87500 paise
        self.assertEqual(stmt["closing_balance_paise"], expected_closing)

        # Verify against customer_outstanding as_of=end_w
        out = self.client.get(
            f"/receivables/outstanding?customer_id={self.retailer_a.id}&as_of={end_w.isoformat()}",
            headers=admin_h,
        ).json()
        self.assertEqual(out["total_outstanding_paise"], expected_closing)

    def test_salesman_isolation_for_receivables(self):
        """
        Salesman isolation:
        - Salesman A can view Retailer A's receivables (assigned).
        - Salesman A CANNOT view Distributor B's receivables (assigned to Salesman B) -> 404 Not Found.
        - Salesman cannot post payments -> 403 Forbidden.
        """
        sales_a_h = {"Authorization": f"Bearer {self.sales_a_token}"}
        sales_b_h = {"Authorization": f"Bearer {self.sales_b_token}"}

        # Salesman A reads Retailer A
        res_a = self.client.get(f"/receivables/outstanding?customer_id={self.retailer_a.id}", headers=sales_a_h)
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)

        # Salesman A attempts to read Distributor B (assigned to Salesman B) -> 404
        res_forbidden = self.client.get(f"/receivables/outstanding?customer_id={self.distributor_b.id}", headers=sales_a_h)
        self.assertEqual(res_forbidden.status_code, status.HTTP_404_NOT_FOUND)

        # Salesman cannot post payments
        res_post = self.client.post(
            "/payments",
            json={"customer_id": self.retailer_a.id, "amount_paise": 10000, "mode": "CASH"},
            headers=sales_a_h,
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)
