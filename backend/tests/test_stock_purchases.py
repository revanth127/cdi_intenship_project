from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
import unittest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.item import Item, ItemType
from app.models.purchase import Purchase, PurchaseLine, PurchaseStatus
from app.models.stock import MovementType, StockMovement
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.schemas.purchase import PurchaseCreate, PurchaseLineCreate
from app.services.purchase import cancel_purchase, create_and_post_purchase
from app.services.stock import (
    InsufficientStockError,
    get_balance,
    get_stock_summary,
    get_valuation,
    post_adjustment,
    post_movement,
)


class TestStockLedgerAndPurchases(unittest.TestCase):
    """
    Test suite covering:
    - Moving weighted average cost calculation
    - Insufficient stock 409 prevention
    - Purchase posting and cancellation with reversal movements
    - Immutability of stock_movements (UPDATE/DELETE prevention)
    - Concurrency protection against negative stock
    - Mathematical invariant: opening + receipts - issues +/- adjustments = closing
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)

        # Install SQLite immutability trigger for testing DB-level protection
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

        pwd = get_password_hash("Password123!")
        self.admin = User(email="admin@stock.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.production = User(email="production@stock.local", hashed_password=pwd, full_name="Production", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="accountant@stock.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.salesman = User(email="salesman@stock.local", hashed_password=pwd, full_name="Salesman", role=UserRole.SALESMAN, is_active=True)

        self.db.add_all([self.admin, self.production, self.accountant, self.salesman])
        self.db.commit()

        # Seed supplier
        self.supplier = Supplier(
            name="Sri Lakshmi Agro Mills",
            gstin="33AAAAA1111A1Z1",
            state_code="33",
            phone="9876543210",
            address="Theni Road, Madurai",
        )
        self.db.add(self.supplier)

        # Seed Item: Flour
        self.flour = Item(
            name="Flour",
            item_type=ItemType.RAW_MATERIAL,
            base_unit="g",
            display_unit="kg",
            hsn_code="1101",
            opening_balance_qty=100000,
            opening_rate_paise=Decimal("4.200000"),
        )
        # Seed Finished Item: Murukku 200 g
        self.murukku = Item(
            name="Murukku 200 g",
            item_type=ItemType.FINISHED_GOOD,
            base_unit="packet",
            display_unit="packet",
            hsn_code="1905",
            gst_rate_bp=500,
            opening_balance_qty=50,
            opening_rate_paise=Decimal("3500.000000"),
        )
        self.db.add_all([self.flour, self.murukku])
        self.db.commit()

        # Post OPENING movement for Flour: 100 kg (100,000 g) @ Rs 42/kg (= 4.200000 paise/g)
        post_movement(
            db=self.db,
            item_id=self.flour.id,
            movement_type=MovementType.OPENING,
            quantity_base=100000,
            unit_cost=Decimal("4.200000"),
            source_type="OPENING",
            source_id="SEED",
            user=self.admin,
            note="100 kg opening balance @ Rs 42/kg",
        )
        # Post OPENING for Murukku: 50 packets @ Rs 35 (3500 paise)
        post_movement(
            db=self.db,
            item_id=self.murukku.id,
            movement_type=MovementType.OPENING,
            quantity_base=50,
            unit_cost=Decimal("3500.000000"),
            source_type="OPENING",
            source_id="SEED",
            user=self.admin,
            note="50 packets opening balance",
        )
        self.db.commit()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _headers(self, user: User) -> dict[str, str]:
        token = create_access_token(subject=user.id, role=user.role)
        return {"Authorization": f"Bearer {token}"}

    def test_weighted_average_cost_flour_purchase(self):
        """
        Requirement:
        60 kg flour purchase at Rs 45/kg on top of 100 kg opening:
        - Opening: 100,000 g @ 4.200000 paise/g -> Value = 420,000 paise
        - Purchase: 60,000 g @ 4.500000 paise/g (Rs 45/kg) -> Value = 270,000 paise
        - Total quantity = 160,000 g
        - Total value = 690,000 paise
        - Weighted average cost = 690,000 / 160,000 = 4.312500 paise/g (= Rs 43.125/kg)
        - Stored as Numeric without rounding loss!
        """
        payload = PurchaseCreate(
            supplier_id=self.supplier.id,
            supplier_invoice_no="INV-SUP-101",
            notes="60 kg flour purchase",
            lines=[
                PurchaseLineCreate(
                    item_id=self.flour.id,
                    quantity_entered=Decimal("60"),
                    unit_entered="kg",
                    rate_paise=4500,  # Rs 45/kg in paise
                )
            ],
        )

        purchase = create_and_post_purchase(self.db, payload, self.admin)
        self.assertEqual(purchase.status, PurchaseStatus.POSTED)
        self.assertEqual(purchase.total_paise, 270000)  # 60 * 4500

        # Check balance
        bal = get_balance(self.db, self.flour.id)
        self.assertEqual(bal, 160000)  # 100,000 + 60,000

        # Check valuation
        val = get_valuation(self.db, self.flour.id)
        self.assertEqual(val["balance_base"], 160000)
        self.assertEqual(val["total_value_paise"], 690000)

        # Expected moving weighted average cost: 4.312500 paise/g
        expected_unit_cost = Decimal("4.312500")
        self.assertEqual(val["weighted_avg_cost_paise"], expected_unit_cost)

    def test_issue_more_than_available_raises_409_and_no_row_written(self):
        """
        Requirement:
        Attempting to issue more stock than currently available raises
        InsufficientStockError (HTTP 409 Conflict) and writes no ledger row.
        """
        current_bal = get_balance(self.db, self.flour.id)
        self.assertEqual(current_bal, 100000)

        initial_rows_count = len(
            self.db.scalars(select(StockMovement).where(StockMovement.item_id == self.flour.id)).all()
        )

        # Attempt to issue 100,001 g (1 g more than available)
        with self.assertRaises(InsufficientStockError) as cm:
            post_movement(
                db=self.db,
                item_id=self.flour.id,
                movement_type=MovementType.PRODUCTION_ISSUE,
                quantity_base=-100001,
                unit_cost=Decimal("4.200000"),
                source_type="PRODUCTION_RUN",
                source_id="TEST-RUN-001",
                user=self.admin,
            )

        self.assertEqual(cm.exception.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(cm.exception.detail["available_base"], 100000)
        self.assertEqual(cm.exception.detail["requested_base"], 100001)

        # Verify no ledger row was written
        after_rows_count = len(
            self.db.scalars(select(StockMovement).where(StockMovement.item_id == self.flour.id)).all()
        )
        self.assertEqual(initial_rows_count, after_rows_count)
        self.assertEqual(get_balance(self.db, self.flour.id), 100000)

    def test_cancelling_purchase_writes_reversal_rows_and_restores_balance(self):
        """
        Requirement:
        Cancelling a purchase writes REVERSAL movements and restores the balance.
        """
        # First post a 60 kg purchase
        payload = PurchaseCreate(
            supplier_id=self.supplier.id,
            lines=[
                PurchaseLineCreate(
                    item_id=self.flour.id,
                    quantity_entered=Decimal("60"),
                    unit_entered="kg",
                    rate_paise=4500,
                )
            ],
        )
        purchase = create_and_post_purchase(self.db, payload, self.admin)
        self.assertEqual(get_balance(self.db, self.flour.id), 160000)

        # Cancel the purchase
        cancelled_purchase = cancel_purchase(
            db=self.db,
            purchase_id=purchase.id,
            user=self.admin,
            reason="Defective supplier delivery",
        )
        self.assertEqual(cancelled_purchase.status, PurchaseStatus.CANCELLED)

        # Balance must be restored to 100,000 g
        bal_after_cancel = get_balance(self.db, self.flour.id)
        self.assertEqual(bal_after_cancel, 100000)

        # Verify a REVERSAL row exists
        reversal_mov = self.db.scalar(
            select(StockMovement).where(
                StockMovement.item_id == self.flour.id,
                StockMovement.movement_type == MovementType.REVERSAL,
            )
        )
        self.assertIsNotNone(reversal_mov)
        self.assertEqual(reversal_mov.quantity_base, -60000)

        # Moving average cost is restored back to 4.200000 paise/g
        val = get_valuation(self.db, self.flour.id)
        self.assertEqual(val["weighted_avg_cost_paise"], Decimal("4.200000"))

    def test_ledger_update_or_delete_attempts_fail(self):
        """
        Requirement:
        Direct UPDATE/DELETE on stock_movements table fails via DB-level trigger.
        """
        movement = self.db.scalar(select(StockMovement).where(StockMovement.item_id == self.flour.id))
        self.assertIsNotNone(movement)

        # Attempt raw SQL UPDATE -> must fail
        with self.assertRaises(Exception):
            self.db.execute(
                text("UPDATE stock_movements SET quantity_base = 999999 WHERE id = :id"),
                {"id": movement.id},
            )
            self.db.commit()

        self.db.rollback()

        # Attempt raw SQL DELETE -> must fail
        with self.assertRaises(Exception):
            self.db.execute(
                text("DELETE FROM stock_movements WHERE id = :id"),
                {"id": movement.id},
            )
            self.db.commit()

        self.db.rollback()

    def test_concurrent_issues_cannot_make_stock_negative(self):
        """
        Requirement:
        Concurrent issues cannot make stock negative (tested with row-level locks).
        """
        # Set flour balance to exactly 50,000 g
        post_movement(
            db=self.db,
            item_id=self.flour.id,
            movement_type=MovementType.PRODUCTION_ISSUE,
            quantity_base=-50000,
            unit_cost=Decimal("4.200000"),
            source_type="PRODUCTION_RUN",
            user=self.admin,
        )
        self.db.commit()
        self.assertEqual(get_balance(self.db, self.flour.id), 50000)

        # Two competing sessions trying to issue 40,000 g each (Total requested: 80,000 > 50,000)
        session1 = self.SessionLocal()
        session2 = self.SessionLocal()

        try:
            # Session 1 successfully issues 40,000 g
            post_movement(
                db=session1,
                item_id=self.flour.id,
                movement_type=MovementType.PRODUCTION_ISSUE,
                quantity_base=-40000,
                unit_cost=Decimal("4.200000"),
                source_type="PRODUCTION_RUN",
                user=self.admin,
            )
            session1.commit()

            # Session 2 tries to issue 40,000 g -> only 10,000 remains -> must raise 409
            with self.assertRaises(InsufficientStockError) as cm:
                post_movement(
                    db=session2,
                    item_id=self.flour.id,
                    movement_type=MovementType.PRODUCTION_ISSUE,
                    quantity_base=-40000,
                    unit_cost=Decimal("4.200000"),
                    source_type="PRODUCTION_RUN",
                    user=self.admin,
                )
            self.assertEqual(cm.exception.status_code, status.HTTP_409_CONFLICT)
            session2.rollback()
        finally:
            session1.close()
            session2.close()

        # Final stock must be exactly 10,000 g (strictly non-negative)
        self.assertEqual(get_balance(self.db, self.flour.id), 10000)

    def test_closing_equals_opening_plus_receipts_minus_issues(self):
        """
        Requirement:
        opening + receipts - issues +/- adjustments = closing holds for every item.
        """
        # Execute adjustment of +5,000 g
        post_adjustment(
            db=self.db,
            item_id=self.flour.id,
            delta=5000,
            reason="Physical inventory surplus",
            user=self.admin,
        )
        self.db.commit()

        summaries = get_stock_summary(self.db)
        for s in summaries:
            self.assertTrue(s["reconciled"])
            computed_closing = (
                s["opening_balance_base"]
                + s["receipts_base"]
                - s["issues_base"]
                + s["adjustments_base"]
            )
            self.assertEqual(computed_closing, s["closing_balance_base"])

    def test_salesman_restricted_to_finished_goods(self):
        """
        Requirement:
        Salesman may only read finished-goods availability.
        """
        headers = self._headers(self.salesman)

        # Salesman reading raw materials gets 403 Forbidden
        res_raw = self.client.get("/api/v1/stock/summary?item_type=RAW_MATERIAL", headers=headers)
        self.assertEqual(res_raw.status_code, status.HTTP_403_FORBIDDEN)

        # Salesman reading finished goods gets 200 OK
        res_fg = self.client.get("/api/v1/stock/summary?item_type=FINISHED_GOOD", headers=headers)
        self.assertEqual(res_fg.status_code, status.HTTP_200_OK)
        data = res_fg.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Murukku 200 g")


if __name__ == "__main__":
    unittest.main()
