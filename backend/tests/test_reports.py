"""Tests for the report registry + shared exporters (JSON/CSV/XLSX/PDF).

Benchmark data: Section 5 transactions applied on clean seed.
"""
import csv
import io
import os
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import UserRole
from scripts.seed import run_seed, seed_benchmark_transactions

BENCHMARK_MONTH = {"from": "2026-11-01", "to": "2026-11-30"}


class TestReports(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = self.SessionLocal()
        run_seed(self.db)
        from app.models.item import Item
        from app.models.product import Product
        from app.models.user import User
        from app.models.customer import Customer
        from app.models.supplier import Supplier
        users = {u.email: u for u in self.db.query(User).all()}
        items = {i.name: i for i in self.db.query(Item).all()}
        product = self.db.query(Product).first()
        customers = self.db.query(Customer).all()
        supplier = self.db.query(Supplier).first()
        seed_benchmark_transactions(self.db, users, items, product, customers, supplier)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.users = {u.role.value: u for u in self.db.query(__import__("app.models.user", fromlist=["User"]).User).all()}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _auth(self, role: str) -> dict:
        # find a user with this role
        from app.models.user import User
        user = self.db.query(User).filter(User.role == UserRole(role)).first()
        token = create_access_token(subject=user.id, role=user.role)
        return {"Authorization": f"Bearer {token}"}

    # ---------- helpers ----------

    def _get(self, name, fmt="json", role="ADMIN", **params):
        return self.client.get(
            f"/api/v1/reports/{name}",
            params={"format": fmt, **params},
            headers=self._auth(role),
        )

    # ---------- sales register ----------

    def test_sales_register_benchmark(self):
        res = self._get("sales_register", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        row = next(r for r in data["rows"] if r["document_type"] == "INVOICE")
        self.assertEqual(row["customer"], "Retailer A (Meenakshi Stores)")
        self.assertEqual(row["taxable_paise"], 750000)
        self.assertEqual(row["cgst_paise"], 18750)
        self.assertEqual(row["sgst_paise"], 18750)
        self.assertEqual(row["total_paise"], 787500)
        self.assertEqual(data["totals"]["taxable_paise"], 750000)
        self.assertEqual(data["totals"]["cgst_paise"], 18750)
        self.assertEqual(data["totals"]["sgst_paise"], 18750)
        self.assertEqual(data["totals"]["total_paise"], 787500)

    def test_sales_register_csv_rows_equal_json_rows(self):
        json_res = self._get("sales_register", **BENCHMARK_MONTH).json()
        csv_res = self._get("sales_register", fmt="csv", **BENCHMARK_MONTH)
        self.assertEqual(csv_res.status_code, 200)
        rows = list(csv.reader(io.StringIO(csv_res.text)))
        header, data_rows, totals_row = rows[0], rows[1:-1], rows[-1]
        # same number of rows
        self.assertEqual(len(data_rows), len(json_res["rows"]))
        # same order + key fields
        for jrow, crow in zip(json_res["rows"], data_rows):
            self.assertEqual(jrow["document_no"], crow[1])
            self.assertEqual(jrow["customer"], crow[3])
        # CSV uses plain decimals for money (Rs 7500.00 / 187.50 / 7875.00)
        self.assertIn("7500.00", totals_row)
        self.assertIn("187.50", totals_row)
        self.assertIn("7875.00", totals_row)
        self.assertNotIn("₹", csv_res.text)
        self.assertNotIn(",", totals_row[header.index("Taxable")] if "Taxable" in header else "")

    def test_sales_register_xlsx_numeric_money_cells(self):
        res = self._get("sales_register", fmt="xlsx", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(res.content))
        ws = wb.active
        headers = [c.value for c in ws[1]]
        taxable_col = headers.index("Taxable") + 1
        data_row = ws[2]
        self.assertIsInstance(data_row[taxable_col - 1].value, (int, float))
        # totals row numeric
        totals_row = ws[ws.max_row]
        self.assertIsInstance(totals_row[taxable_col - 1].value, (int, float))
        self.assertEqual(totals_row[taxable_col - 1].value, 7500.0)
        # number format + freeze panes + autofilter + header row
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertTrue(ws.auto_filter.ref)
        self.assertEqual(ws[1][taxable_col - 1].value, "Taxable")

    def test_sales_register_pdf(self):
        res = self._get("sales_register", fmt="pdf", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.content.startswith(b"%PDF"))

    # ---------- gst_outward ----------

    def test_gst_outward_3_1a_benchmark(self):
        res = self._get("gst_outward", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200, res.text)
        totals = res.json()["totals"]
        self.assertEqual(totals["gstr_3_1a"]["outward_taxable_paise"], 750000)
        self.assertEqual(totals["gstr_3_1a"]["cgst_paise"], 18750)
        self.assertEqual(totals["gstr_3_1a"]["sgst_paise"], 18750)
        self.assertEqual(totals["taxable_paise"], 750000)
        # HSN summary present, finished goods HSN 1905
        hsn_codes = {h["hsn_code"] for h in totals["hsn_summary"]}
        self.assertIn("1905", hsn_codes)

    # ---------- stock ----------

    def test_stock_summary_benchmark(self):
        res = self._get("stock_summary", as_of="2026-11-30", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200, res.text)
        rows = {r["name"]: r for r in res.json()["rows"]}
        self.assertEqual(rows["Flour"]["closing_balance_base"], 120000)  # 120 kg
        self.assertEqual(rows["Flour"]["closing_balance_display"], "120")
        self.assertEqual(float(rows["Cooking oil"]["closing_balance_display"]), 19.5)
        self.assertEqual(rows["200 g pouch"]["closing_balance_base"], 306)
        self.assertEqual(rows["Carton"]["closing_balance_base"], 21)
        self.assertEqual(rows["Murukku 200 g"]["closing_balance_base"], 88)  # finished goods 88
        # raw / packaging / finished split available
        types = {r["item_type"] for r in res.json()["rows"]}
        self.assertTrue({"RAW_MATERIAL", "PACKAGING", "FINISHED_GOOD"}.issubset(types))

    def test_stock_summary_xlsx(self):
        res = self._get("stock_summary", fmt="xlsx", as_of="2026-11-30")
        self.assertEqual(res.status_code, 200)
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(res.content)).active
        self.assertEqual(ws.freeze_panes, "A2")

    # ---------- production ----------

    def test_production_report_benchmark(self):
        res = self._get("production_report", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200, res.text)
        rows = res.json()["rows"]
        by_item = {r["item"]: r for r in rows}
        self.assertEqual(by_item["Cooking oil"]["planned_qty_base"], 10000)
        self.assertEqual(by_item["Cooking oil"]["actual_qty_base"], 10500)
        self.assertTrue(by_item["Cooking oil"]["is_flagged"])
        self.assertEqual(by_item["Carton"]["actual_qty_base"], 9)
        self.assertTrue(by_item["Carton"]["is_flagged"])
        self.assertEqual(by_item["200 g pouch"]["actual_qty_base"], 194)
        self.assertFalse(by_item["200 g pouch"]["is_flagged"])
        self.assertEqual(by_item["Flour"]["wastage_packets"], 12)
        self.assertEqual(by_item["Flour"]["actual_good_packets"], 188)

    # ---------- purchase register ----------

    def test_purchase_register(self):
        res = self._get("purchase_register", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200)
        rows = res.json()["rows"]
        flour = next(r for r in rows if r["item"] == "Flour")
        self.assertEqual(flour["quantity_base"], 60000)  # 60 kg
        self.assertEqual(flour["line_total_paise"], 270000)  # Rs 45/kg -> Rs 2700

    # ---------- collections ----------

    def test_collections_outstanding(self):
        res = self._get("collections_outstanding", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200, res.text)
        rows = {r["customer"]: r for r in res.json()["rows"]}
        retailer = rows["Retailer A (Meenakshi Stores)"]
        self.assertEqual(retailer["payments_paise"], 400000)
        self.assertEqual(retailer["total_outstanding_paise"], 387500)

    # ---------- sales by customer product ----------

    def test_sales_by_customer_product(self):
        res = self._get("sales_by_customer_product", **BENCHMARK_MONTH)
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["rows"] if r["customer"].startswith("Retailer A"))
        self.assertEqual(row["quantity_packets"], 150)
        self.assertEqual(row["taxable_paise"], 750000)

    # ---------- formats ----------

    def test_json_csv_xlsx_pdf_parity_sales_register(self):
        name = "sales_register"
        js = self._get(name, **BENCHMARK_MONTH).json()
        cs = list(csv.reader(io.StringIO(self._get(name, fmt="csv", **BENCHMARK_MONTH).text)))
        self.assertEqual(len(js["rows"]), len(cs) - 2)  # header + rows + totals
        self.assertEqual(self._get(name, fmt="pdf", **BENCHMARK_MONTH).content[:5], b"%PDF-")
        self.assertTrue(self._get(name, fmt="xlsx", **BENCHMARK_MONTH).content[:2] == b"PK")

    # ---------- IST business dates ----------

    def test_ist_date_boundary(self):
        # invoice dated 2026-11-30 in month; 2026-12-01 not in month
        in_period_month = self._get("sales_register", **BENCHMARK_MONTH).json()["totals"]["row_count"]
        empty = self._get("sales_register", **{"from": "2026-12-01", "to": "2026-12-01"}).json()["totals"]["row_count"]
        self.assertGreaterEqual(in_period_month, 1)
        self.assertEqual(empty, 0)  # invoice on 1st of next month is NOT in month
        # invoice on the last day of the month IS in: query its own IST date
        from app.models.invoice import Invoice
        from app.services.reports import ist_date
        inv = self.db.query(Invoice).first()
        d = ist_date(inv.invoice_date).isoformat()
        narrow = self._get("sales_register", **{"from": d, "to": d}).json()["totals"]["row_count"]
        self.assertGreaterEqual(narrow, 1)

    def test_ist_invoice_on_first_of_next_month_not_in_month(self):
        from app.services.reports import in_period, ist_date
        from datetime import datetime, timezone
        # 2026-11-30 20:00 UTC == 2026-12-01 01:30 IST -> NOT in November
        dt = datetime(2026, 11, 30, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(ist_date(dt).isoformat(), "2026-12-01")
        self.assertFalse(in_period(dt, __import__("datetime").date(2026, 11, 1), __import__("datetime").date(2026, 11, 30)))
        # 2026-11-29 20:00 UTC == 2026-11-30 01:30 IST -> in November
        dt2 = datetime(2026, 11, 29, 20, 0, tzinfo=timezone.utc)
        self.assertTrue(in_period(dt2, __import__("datetime").date(2026, 11, 1), __import__("datetime").date(2026, 11, 30)))

    # ---------- permissions ----------

    def test_permissions_admin_accountant_owner_all(self):
        for role in ("ADMIN", "ACCOUNTANT", "OWNER"):
            res = self._get("sales_register", role=role)
            self.assertEqual(res.status_code, 200, f"{role}: {res.text}")
            res = self._get("gst_outward", role=role)
            self.assertEqual(res.status_code, 200)

    def test_permissions_production_stock_and_production_only(self):
        self.assertEqual(self._get("stock_summary", role="PRODUCTION").status_code, 200)
        self.assertEqual(self._get("stock_ledger", role="PRODUCTION").status_code, 200)
        self.assertEqual(self._get("production_report", role="PRODUCTION").status_code, 200)
        self.assertEqual(self._get("sales_register", role="PRODUCTION").status_code, 403)
        self.assertEqual(self._get("gst_outward", role="PRODUCTION").status_code, 403)
        self.assertEqual(self._get("purchase_register", role="PRODUCTION").status_code, 403)
        self.assertEqual(self._get("collections_outstanding", role="PRODUCTION").status_code, 403)

    def test_permissions_salesman_none(self):
        self.assertEqual(self._get("stock_summary", role="SALESMAN").status_code, 403)
        self.assertEqual(self._get("sales_register", role="SALESMAN").status_code, 403)

    # ---------- audit logging ----------

    def test_export_logs_audit(self):
        from app.models.audit import AuditLog
        before = self.db.query(AuditLog).filter(AuditLog.action == "REPORT_EXPORTED").count()
        self._get("sales_register", fmt="csv", **BENCHMARK_MONTH)
        self.db.expire_all()
        after = self.db.query(AuditLog).filter(AuditLog.action == "REPORT_EXPORTED").count()
        self.assertEqual(after, before + 1)

    def test_unknown_report_404(self):
        self.assertEqual(self._get("nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
