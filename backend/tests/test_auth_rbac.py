from datetime import timedelta
from decimal import Decimal
import os
import sys
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
from app.models.audit import AuditLog
from app.models.customer import Customer, CustomerType
from app.models.item import Item, ItemType
from app.models.user import User, UserRole


class TestAuthAndRBAC(unittest.TestCase):
    """
    Test suite for Authentication (JWT) and Role-Based Access Control (RBAC).
    """

    def setUp(self):
        # Create an isolated SQLite database in memory for testing
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = self.SessionLocal()

        # Seed sample users for each role
        pwd = get_password_hash("TestPassword123!")

        self.admin = User(email="admin@test.local", hashed_password=pwd, full_name="Admin", role=UserRole.ADMIN, is_active=True)
        self.owner = User(email="owner@test.local", hashed_password=pwd, full_name="Owner", role=UserRole.OWNER, is_active=True)
        self.salesman_a = User(email="salesman.a@test.local", hashed_password=pwd, full_name="Salesman A", role=UserRole.SALESMAN, is_active=True)
        self.salesman_b = User(email="salesman.b@test.local", hashed_password=pwd, full_name="Salesman B", role=UserRole.SALESMAN, is_active=True)
        self.production = User(email="production@test.local", hashed_password=pwd, full_name="Production", role=UserRole.PRODUCTION, is_active=True)
        self.accountant = User(email="accountant@test.local", hashed_password=pwd, full_name="Accountant", role=UserRole.ACCOUNTANT, is_active=True)
        self.inactive_user = User(email="inactive@test.local", hashed_password=pwd, full_name="Inactive", role=UserRole.SALESMAN, is_active=False)

        self.db.add_all([
            self.admin, self.owner, self.salesman_a, self.salesman_b,
            self.production, self.accountant, self.inactive_user
        ])
        self.db.commit()

        # Refresh instances
        for u in [self.admin, self.owner, self.salesman_a, self.salesman_b, self.production, self.accountant, self.inactive_user]:
            self.db.refresh(u)

        # Seed test items and customers
        self.flour = Item(
            name="Test Flour",
            item_type=ItemType.RAW_MATERIAL,
            base_unit="g",
            display_unit="kg",
            gst_rate_bp=0,
            opening_balance_qty=10000,
        )
        self.customer_a = Customer(
            name="Customer of A",
            customer_type=CustomerType.RETAILER,
            state_code="33",
            address="Madurai",
            phone="9999911111",
            assigned_salesman_id=self.salesman_a.id,
            is_active=True,
        )
        self.customer_b = Customer(
            name="Customer of B",
            customer_type=CustomerType.DISTRIBUTOR,
            state_code="29",
            address="Bengaluru",
            phone="9999922222",
            assigned_salesman_id=self.salesman_b.id,
            is_active=True,
        )
        self.db.add_all([self.flour, self.customer_a, self.customer_b])
        self.db.commit()
        self.db.refresh(self.flour)
        self.db.refresh(self.customer_a)
        self.db.refresh(self.customer_b)

        # Configure TestClient with overridden get_db
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

    def _get_auth_headers(self, user: User) -> dict[str, str]:
        token = create_access_token(subject=user.id, role=user.role)
        return {"Authorization": f"Bearer {token}"}

    def test_login_success(self):
        res = self.client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.local", "password": "TestPassword123!"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["email"], "admin@test.local")
        self.assertEqual(data["user"]["role"], "ADMIN")

    def test_login_failure_wrong_password(self):
        res = self.client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.local", "password": "WrongPassword!"},
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("Incorrect email or password", res.json()["detail"])

    def test_login_failure_nonexistent_user(self):
        res = self.client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@test.local", "password": "AnyPassword!"},
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_inactive_user_blocked(self):
        res = self.client.post(
            "/api/v1/auth/login",
            data={"username": "inactive@test.local", "password": "TestPassword123!"},
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("deactivated", res.json()["detail"].lower())

    def test_invalid_or_expired_token_rejected(self):
        # Tampered token
        res = self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.fake.token"})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Expired token
        expired_token = create_access_token(
            subject=self.admin.id,
            role=self.admin.role,
            expires_delta=timedelta(seconds=-10),
        )
        res = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_current_user_me(self):
        headers = self._get_auth_headers(self.admin)
        res = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["email"], "admin@test.local")

    def test_rbac_salesman_cannot_create_items(self):
        headers = self._get_auth_headers(self.salesman_a)
        res = self.client.post(
            "/api/v1/items",
            headers=headers,
            json={
                "name": "Unauthorized Item",
                "item_type": "RAW_MATERIAL",
                "base_unit": "g",
                "display_unit": "kg",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rbac_salesman_cannot_create_users(self):
        headers = self._get_auth_headers(self.salesman_a)
        res = self.client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": "hacked@test.local",
                "full_name": "Hacked",
                "password": "Password123!",
                "role": "ADMIN",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rbac_production_cannot_create_users(self):
        headers = self._get_auth_headers(self.production)
        res = self.client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": "another@test.local",
                "full_name": "Test",
                "password": "Password123!",
                "role": "PRODUCTION",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rbac_production_can_read_items(self):
        headers = self._get_auth_headers(self.production)
        res = self.client.get("/api/v1/items", headers=headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.json()), 1)

    def test_rbac_accountant_is_read_only(self):
        headers = self._get_auth_headers(self.accountant)

        # Can read items
        res_read = self.client.get("/api/v1/items", headers=headers)
        self.assertEqual(res_read.status_code, status.HTTP_200_OK)

        # Cannot write items
        res_write = self.client.post(
            "/api/v1/items",
            headers=headers,
            json={
                "name": "Accountant Item",
                "item_type": "RAW_MATERIAL",
                "base_unit": "g",
                "display_unit": "kg",
            },
        )
        self.assertEqual(res_write.status_code, status.HTTP_403_FORBIDDEN)

    def test_rbac_admin_can_create_user(self):
        headers = self._get_auth_headers(self.admin)
        res = self.client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": "new.user@test.local",
                "full_name": "New User",
                "password": "SecurePassword123!",
                "role": "SALESMAN",
                "is_active": True,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["email"], "new.user@test.local")

    def test_rbac_salesman_isolated_customer_access(self):
        headers_a = self._get_auth_headers(self.salesman_a)

        # Salesman A list customers: should only receive customer_a
        res_list = self.client.get("/api/v1/customers", headers=headers_a)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        data = res_list.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.customer_a.id)

        # Salesman A can read customer_a directly
        res_get_own = self.client.get(f"/api/v1/customers/{self.customer_a.id}", headers=headers_a)
        self.assertEqual(res_get_own.status_code, status.HTTP_200_OK)

        # Salesman A reading customer_b gets 403 Forbidden
        res_get_other = self.client.get(f"/api/v1/customers/{self.customer_b.id}", headers=headers_a)
        self.assertEqual(res_get_other.status_code, status.HTTP_403_FORBIDDEN)

    def test_audit_log_written_when_role_changed(self):
        headers = self._get_auth_headers(self.admin)

        # Change salesman_a role to ACCOUNTANT
        res = self.client.patch(
            f"/api/v1/users/{self.salesman_a.id}",
            headers=headers,
            json={"role": "ACCOUNTANT"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["role"], "ACCOUNTANT")

        # Verify audit_log entry was created
        audit_entry = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "USER_ROLE_CHANGED",
                AuditLog.entity_id == str(self.salesman_a.id),
            )
        )
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.user_id, self.admin.id)
        self.assertEqual(audit_entry.entity_type, "User")
        self.assertEqual(audit_entry.old_values["role"], "SALESMAN")
        self.assertEqual(audit_entry.new_values["role"], "ACCOUNTANT")


if __name__ == "__main__":
    unittest.main()
