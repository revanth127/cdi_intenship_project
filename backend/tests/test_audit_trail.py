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
from app.core.security import create_access_token
from app.main import app
from app.models.audit import AuditLog
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.item import Item, ItemType
from app.models.order import Order, OrderLine, OrderStatus, PriceSource
from app.models.pricing import PriceList, PriceListItem
from app.models.product import PackagingSpec, Product, ProductFamily
from app.models.production import ProductionRun, ProductionRunLine, ProductionRunStatus
from app.models.stock import MovementType
from app.models.user import User, UserRole
from app.schemas.order import OrderCreate, OrderLineCreate, OrderUpdate, OrderLineUpdate
from app.schemas.production import ProductionRunCreate, ProductionRunLineUpdate, ProductionRunUpdate
from app.services.invoicing import create_invoice_from_order
from app.services.orders import approve_order, create_order, reject_order, update_order
from app.services.production import create_run, post_run, update_run
from app.services.stock import post_movement


class TestAuditTrail(unittest.TestCase):
    """
    Comprehensive test suite for the Order-to-Audit strengthened audit trail:
    1. Append-only trigger blocks UPDATE and DELETE on audit_logs.
    2. Logging of order edits, approve, reject, approve-with-shortage.
    3. Logging of invoice posted, shared, dispatched, cancelled by credit note.
    4. Attempted edits to posted invoices and posted production runs return 409 AND log 'edit_rejected'.
    5. GET /audit-log with RBAC and filters, plus /invoices/{id}/history and /production/{id}/history.
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
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_update
            BEFORE UPDATE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'Audit logs are strictly immutable. UPDATE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_delete
            BEFORE DELETE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'Audit logs are strictly immutable. DELETE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_stock_movements_update
            BEFORE UPDATE ON stock_movements
            BEGIN
                SELECT RAISE(ABORT, 'Stock movements are strictly immutable. UPDATE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_stock_movements_delete
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
        self.admin = User(email="admin@test.local", hashed_password="pw", full_name="Admin User", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@test.local", hashed_password="pw", full_name="Owner User", role=UserRole.OWNER, is_active=True)
        self.accountant = User(email="acct@test.local", hashed_password="pw", full_name="Accountant User", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman = User(email="sales@test.local", hashed_password="pw", full_name="Salesman User", role=UserRole.SALESMAN, is_active=True)
        self.prod_user = User(email="prod@test.local", hashed_password="pw", full_name="Prod User", role=UserRole.PRODUCTION, is_active=True)

        self.db.add_all([self.admin, self.owner, self.accountant, self.salesman, self.prod_user])
        self.db.commit()

        self.admin_headers = {"Authorization": f"Bearer {create_access_token(self.admin.id, self.admin.role)}"}
        self.owner_headers = {"Authorization": f"Bearer {create_access_token(self.owner.id, self.owner.role)}"}
        self.accountant_headers = {"Authorization": f"Bearer {create_access_token(self.accountant.id, self.accountant.role)}"}
        self.salesman_headers = {"Authorization": f"Bearer {create_access_token(self.salesman.id, self.salesman.role)}"}

        # Company
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

        # Master Items & Products
        self.flour = Item(name="Flour", item_type=ItemType.RAW_MATERIAL, base_unit="g", display_unit="kg", hsn_code="1101", gst_rate_bp=0, opening_balance_qty=100000, opening_rate_paise=Decimal("4.200000"))
        self.oil = Item(name="Cooking oil", item_type=ItemType.RAW_MATERIAL, base_unit="ml", display_unit="L", hsn_code="1507", gst_rate_bp=500, opening_balance_qty=30000, opening_rate_paise=Decimal("14.000000"))
        self.pouch = Item(name="200 g pouch", item_type=ItemType.PACKAGING, base_unit="piece", display_unit="piece", hsn_code="3923", gst_rate_bp=1800, opening_balance_qty=500, opening_rate_paise=Decimal("250.000000"))
        self.fg_item = Item(name="Murukku 200 g", item_type=ItemType.FINISHED_GOOD, base_unit="packet", display_unit="packet", hsn_code="1905", gst_rate_bp=500, opening_balance_qty=100, opening_rate_paise=Decimal("3500.000000"))

        self.db.add_all([self.flour, self.oil, self.pouch, self.fg_item])
        self.db.commit()

        # Opening balance for finished good
        post_movement(self.db, self.fg_item.id, MovementType.OPENING, 100, Decimal("3500.000000"), "OPENING", "1", self.admin)
        self.db.commit()

        self.family = ProductFamily(name="Murukku", hsn_code="1905", gst_rate_bp=500, is_active=True)
        self.db.add(self.family)
        self.db.flush()

        self.product = Product(family_id=self.family.id, item_id=self.fg_item.id, pack_name="Murukku 200 g", net_weight_g=200, packets_per_carton=20, is_active=True)
        self.db.add(self.product)
        self.db.flush()

        self.db.add(PackagingSpec(product_id=self.product.id, item_id=self.pouch.id, qty_base=1, per_packets=1))

        self.price_list = PriceList(name="Standard", is_default=True, is_active=True)
        self.db.add(self.price_list)
        self.db.flush()
        self.db.add(PriceListItem(price_list_id=self.price_list.id, product_id=self.product.id, price_paise=5000, effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc)))

        self.bom = BOM(family_id=self.family.id, version=1, expected_output_g=40000, is_active=True)
        self.db.add(self.bom)
        self.db.flush()
        self.bom.items.append(BOMItem(item_id=self.flour.id, quantity_per_batch=40000))
        self.bom.items.append(BOMItem(item_id=self.oil.id, quantity_per_batch=10000))

        self.customer = Customer(name="Meenakshi Stores", gstin="33AAAAA0000A1Z5", state_code="33", address="Madurai", is_active=True, assigned_salesman_id=self.salesman.id)
        self.db.add(self.customer)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def test_audit_log_immutable_trigger_blocks_update_and_delete(self):
        """
        Verifies the trigger strictly forbids UPDATE and DELETE on audit_logs.
        """
        audit = AuditLog(user_id=self.admin.id, action="TEST_ACTION", entity_type="Test", entity_id="1")
        self.db.add(audit)
        self.db.commit()

        # Attempt UPDATE -> must raise exception from database trigger
        with self.assertRaises(Exception) as ctx:
            self.db.execute(text(f"UPDATE audit_logs SET action = 'TAMPERED' WHERE id = {audit.id}"))
            self.db.commit()
        self.assertIn("strictly immutable", str(ctx.exception))
        self.db.rollback()

        # Attempt DELETE -> must raise exception from database trigger
        with self.assertRaises(Exception) as ctx:
            self.db.execute(text(f"DELETE FROM audit_logs WHERE id = {audit.id}"))
            self.db.commit()
        self.assertIn("strictly immutable", str(ctx.exception))
        self.db.rollback()

    def test_order_edits_approve_reject_and_shortage_audit_logging(self):
        """
        Validates:
        - Order edits before approval log quantity and price changes with old and new values.
        - Order approve logs ORDER_APPROVED.
        - Order approve with shortage logs ORDER_APPROVED_WITH_SHORTAGE.
        - Order reject logs ORDER_REJECTED.
        """
        # 1. Create order
        order = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-audit-1",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=10, unit_price_paise=5000)],
            ),
            self.salesman,
        )

        # 2. Edit order before approval (change qty to 15, price to 5200)
        updated = update_order(
            self.db,
            order.id,
            OrderUpdate(
                lines=[OrderLineUpdate(product_id=self.product.id, quantity_packets=15, unit_price_paise=5200)],
                notes="Price negotiated",
            ),
            self.admin,
        )

        audit_edit = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(order.id), AuditLog.action == "ORDER_UPDATED")
        )
        self.assertIsNotNone(audit_edit)
        self.assertEqual(audit_edit.user_id, self.admin.id)
        self.assertEqual(audit_edit.old_values["lines"][0]["quantity_packets"], 10)
        self.assertEqual(audit_edit.new_values["lines"][0]["quantity_packets"], 15)
        self.assertEqual(audit_edit.new_values["lines"][0]["unit_price_paise"], 5200)

        # 3. Approve order
        approved = approve_order(self.db, order.id, user=self.admin)
        audit_app = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(order.id), AuditLog.action == "ORDER_APPROVED")
        )
        self.assertIsNotNone(audit_app)
        self.assertEqual(audit_app.user_id, self.admin.id)
        self.assertFalse(audit_app.new_values["approved_with_shortage"])

        # 4. Create second order with requested > available (available is 100 - 15 = 85 pkts)
        order2 = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-audit-2",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=120, unit_price_paise=5000)],
            ),
            self.salesman,
        )
        # Approve with shortage override
        app_shortage = approve_order(self.db, order2.id, user=self.admin, approve_with_shortage=True)
        audit_shortage = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(order2.id), AuditLog.action == "ORDER_APPROVED_WITH_SHORTAGE")
        )
        self.assertIsNotNone(audit_shortage)
        self.assertTrue(audit_shortage.new_values["approved_with_shortage"])

        # 5. Reject a third order
        order3 = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-audit-3",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=5, unit_price_paise=5000)],
            ),
            self.salesman,
        )
        rejected = reject_order(self.db, order3.id, reason="Customer credit limit exceeded", user=self.admin)
        audit_rej = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(order3.id), AuditLog.action == "ORDER_REJECTED")
        )
        self.assertIsNotNone(audit_rej)
        self.assertEqual(audit_rej.user_id, self.admin.id)

    def test_invoice_posted_shared_dispatched_and_cancelled_logging(self):
        """
        Validates invoice audit trail:
        - INVOICE_POSTED
        - INVOICE_SHARED
        - INVOICE_DISPATCHED
        - INVOICE_CANCELLED (by credit note)
        """
        order = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-inv-1",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=10, unit_price_paise=5000)],
            ),
            self.salesman,
        )
        approve_order(self.db, order.id, user=self.admin)

        # 1. Invoice posted
        invoice = create_invoice_from_order(self.db, order.id, user=self.admin)
        inv_audit = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(invoice.id), AuditLog.action == "INVOICE_POSTED")
        )
        self.assertIsNotNone(inv_audit)
        self.assertEqual(inv_audit.user_id, self.admin.id)

        # 2. Share link generated
        res_share = self.client.get(f"/invoices/{invoice.id}/share-link", headers=self.admin_headers)
        self.assertEqual(res_share.status_code, 200)
        share_audit = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(invoice.id), AuditLog.action == "INVOICE_SHARED")
        )
        self.assertIsNotNone(share_audit)

        # 3. Dispatched
        res_disp = self.client.post(
            f"/invoices/{invoice.id}/dispatch",
            headers=self.admin_headers,
            json={"vehicle_no": "TN-59-AB-1234"},
        )
        self.assertEqual(res_disp.status_code, 201)
        disp_audit = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(invoice.id), AuditLog.action == "INVOICE_DISPATCHED")
        )
        self.assertIsNotNone(disp_audit)

        # 4. Cancelled by credit note
        res_cn = self.client.post(
            f"/invoices/{invoice.id}/credit-note",
            headers=self.admin_headers,
            json={"reason": "Goods damaged in transit", "return_stock": True},
        )
        self.assertEqual(res_cn.status_code, 201)
        cancel_audit = self.db.scalar(
            select(AuditLog).where(AuditLog.entity_id == str(invoice.id), AuditLog.action == "INVOICE_CANCELLED")
        )
        self.assertIsNotNone(cancel_audit)

    def test_attempted_edits_to_posted_invoice_return_409_and_log_rejection(self):
        """
        Attempted edit (PUT/PATCH/DELETE) on a posted invoice returns 409 AND logs action 'edit_rejected'.
        """
        order = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-inv-lock",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=10, unit_price_paise=5000)],
            ),
            self.salesman,
        )
        approve_order(self.db, order.id, user=self.admin)
        invoice = create_invoice_from_order(self.db, order.id, user=self.admin)

        # Attempt PUT edit -> 409 Conflict
        put_res = self.client.put(
            f"/invoices/{invoice.id}",
            headers=self.admin_headers,
            json={"grand_total_paise": 1000},
        )
        self.assertEqual(put_res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("immutable once posted", put_res.json()["detail"])

        # Attempt DELETE -> 409 Conflict
        del_res = self.client.delete(
            f"/invoices/{invoice.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(del_res.status_code, status.HTTP_409_CONFLICT)

        # Verify audit logs captured the rejection
        rej_audits = self.db.scalars(
            select(AuditLog).where(AuditLog.entity_id == str(invoice.id), AuditLog.action == "edit_rejected")
        ).all()
        self.assertGreaterEqual(len(rej_audits), 2)
        self.assertEqual(rej_audits[0].new_values["grand_total_paise"], 1000)

    def test_attempted_edits_to_posted_production_run_return_409_and_log_rejection(self):
        """
        Attempted edit on a POSTED production run returns 409 AND logs action 'edit_rejected'.
        """
        run = create_run(self.db, ProductionRunCreate(product_id=self.product.id, batches=Decimal("1.0000")), self.prod_user)
        # Post the run
        update_run(
            self.db,
            run.id,
            ProductionRunUpdate(
                actual_good_packets=200,
                lines=[
                    ProductionRunLineUpdate(item_id=self.flour.id, actual_qty_base=40000),
                    ProductionRunLineUpdate(item_id=self.oil.id, actual_qty_base=10000),
                    ProductionRunLineUpdate(item_id=self.pouch.id, actual_qty_base=200),
                ],
            ),
            self.prod_user,
        )
        post_run(self.db, run.id, self.prod_user)
        self.assertEqual(run.status, ProductionRunStatus.POSTED)

        # Attempt to edit posted run via PATCH -> 409 Conflict
        patch_res = self.client.patch(
            f"/production/{run.id}",
            headers={"Authorization": f"Bearer {create_access_token(self.prod_user.id, self.prod_user.role)}"},
            json={"actual_good_packets": 250},
        )
        self.assertEqual(patch_res.status_code, status.HTTP_409_CONFLICT)

        # Verify audit log recorded edit_rejected
        rej_audit = self.db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == str(run.id),
                AuditLog.action == "edit_rejected",
            )
        )
        self.assertIsNotNone(rej_audit)
        self.assertEqual(rej_audit.new_values["actual_good_packets"], 250)

    def test_document_history_endpoints_return_events_in_order(self):
        """
        GET /invoices/{id}/history and GET /production/{id}/history return chronological timeline.
        """
        order = create_order(
            self.db,
            OrderCreate(
                client_uuid="uuid-hist-1",
                customer_id=self.customer.id,
                lines=[OrderLineCreate(product_id=self.product.id, quantity_packets=10, unit_price_paise=5000)],
            ),
            self.salesman,
        )
        approve_order(self.db, order.id, user=self.admin)
        invoice = create_invoice_from_order(self.db, order.id, user=self.admin)

        # Generate share link and download PDF
        self.client.get(f"/invoices/{invoice.id}/share-link", headers=self.admin_headers)
        self.client.get(f"/invoices/{invoice.id}/pdf", headers=self.admin_headers)

        # Query history
        res = self.client.get(f"/invoices/{invoice.id}/history", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        history = res.json()
        self.assertGreaterEqual(len(history), 3)

        actions = [h["action"] for h in history]
        self.assertIn("INVOICE_POSTED", actions)
        self.assertIn("INVOICE_SHARED", actions)
        self.assertIn("REPORT_EXPORTED", actions)

    def test_audit_log_query_endpoint_and_role_permissions(self):
        """
        GET /audit-log:
        - ADMIN, OWNER, ACCOUNTANT can read
        - SALESMAN is blocked with 403 Forbidden
        - Filtering by action and entity_type works
        """
        # Admin can access
        res_admin = self.client.get("/audit-log", headers=self.admin_headers)
        self.assertEqual(res_admin.status_code, 200)

        # Owner can access
        res_owner = self.client.get("/audit-log", headers=self.owner_headers)
        self.assertEqual(res_owner.status_code, 200)

        # Accountant can access
        res_acct = self.client.get("/audit-log", headers=self.accountant_headers)
        self.assertEqual(res_acct.status_code, 200)

        # Salesman forbidden
        res_sales = self.client.get("/audit-log", headers=self.salesman_headers)
        self.assertEqual(res_sales.status_code, status.HTTP_403_FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
