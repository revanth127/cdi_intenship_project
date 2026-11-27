import os
import sys
import unittest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.main import app
from app.models.user import UserRole
from scripts.seed import DEMO_CREDENTIALS, run_seed


class TestDemoRolesAndRBAC(unittest.TestCase):
    """
    Part 2 Verification Tests:
    1. Each seeded user can log in with their defined demo password.
    2. Each of the five roles is blocked with HTTP 403 Forbidden from at least two
       endpoints that belong to other roles.
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

        # Seed master data & users idempotently
        run_seed(self.db)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        app.dependency_overrides.clear()

    def test_all_seeded_users_can_log_in(self):
        """Verify each seeded user can log in via /auth/login with configured demo password."""
        for cred in DEMO_CREDENTIALS:
            resp = self.client.post(
                "/auth/login",
                data={"username": cred["email"], "password": cred["password"]},
            )
            self.assertEqual(
                resp.status_code,
                status.HTTP_200_OK,
                f"User {cred['email']} failed to log in: {resp.text}",
            )
            data = resp.json()
            self.assertIn("access_token", data)
            self.assertEqual(data["token_type"].lower(), "bearer")
            self.assertEqual(data["user"]["email"], cred["email"])
            self.assertEqual(data["user"]["role"], cred["role"].value)

    def test_each_role_is_blocked_from_at_least_two_endpoints_with_403(self):
        """
        Verify each role is blocked (HTTP 403 Forbidden) from at least two endpoints
        belonging to other roles.
        """
        tokens: dict[str, str] = {}
        for cred in DEMO_CREDENTIALS:
            resp = self.client.post(
                "/auth/login",
                data={"username": cred["email"], "password": cred["password"]},
            )
            tokens[cred["role_name"]] = resp.json()["access_token"]

        # 1. OWNER (Blocked from ADMIN-only endpoints: /users)
        owner_h = {"Authorization": f"Bearer {tokens['OWNER']}"}
        resp_owner_1 = self.client.get("/users", headers=owner_h)
        self.assertEqual(resp_owner_1.status_code, status.HTTP_403_FORBIDDEN)
        resp_owner_2 = self.client.post("/users", json={"email": "u@test.local"}, headers=owner_h)
        self.assertEqual(resp_owner_2.status_code, status.HTTP_403_FORBIDDEN)

        # 2. ADMIN (Blocked from SALESMAN-only endpoints: /me/orders, /me/sales/customer-wise)
        admin_h = {"Authorization": f"Bearer {tokens['ADMIN']}"}
        resp_admin_1 = self.client.get("/me/orders", headers=admin_h)
        self.assertEqual(resp_admin_1.status_code, status.HTTP_403_FORBIDDEN)
        resp_admin_2 = self.client.get("/me/sales/customer-wise", headers=admin_h)
        self.assertEqual(resp_admin_2.status_code, status.HTTP_403_FORBIDDEN)

        # 3. SALESMAN (Blocked from /dashboard/summary and /production)
        sales_h = {"Authorization": f"Bearer {tokens['SALESMAN']}"}
        resp_sales_1 = self.client.get("/dashboard/summary", headers=sales_h)
        self.assertEqual(resp_sales_1.status_code, status.HTTP_403_FORBIDDEN)
        resp_sales_2 = self.client.post("/production", json={}, headers=sales_h)
        self.assertEqual(resp_sales_2.status_code, status.HTTP_403_FORBIDDEN)

        # 4. PRODUCTION (Blocked from /dashboard/summary and /users)
        prod_h = {"Authorization": f"Bearer {tokens['PRODUCTION']}"}
        resp_prod_1 = self.client.get("/dashboard/summary", headers=prod_h)
        self.assertEqual(resp_prod_1.status_code, status.HTTP_403_FORBIDDEN)
        resp_prod_2 = self.client.get("/users", headers=prod_h)
        self.assertEqual(resp_prod_2.status_code, status.HTTP_403_FORBIDDEN)

        # 5. ACCOUNTANT (Blocked from /production and /users)
        acct_h = {"Authorization": f"Bearer {tokens['ACCOUNTANT']}"}
        resp_acct_1 = self.client.post("/production", json={}, headers=acct_h)
        self.assertEqual(resp_acct_1.status_code, status.HTTP_403_FORBIDDEN)
        resp_acct_2 = self.client.get("/users", headers=acct_h)
        self.assertEqual(resp_acct_2.status_code, status.HTTP_403_FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
