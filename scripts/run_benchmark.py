#!/usr/bin/env python3
"""Execute Section 5 against the live API, starting from seeded master data only."""
import json
import os
import sys
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from scripts.seed import DEMO_CREDENTIALS

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")


class DirtyBenchmarkState(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, method: str, path: str, token: str, payload=None):
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        request = Request(self._url(path), data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read()
                return json.loads(content) if content else None
        except HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"{method} {self._url(path)} returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Could not reach API at {self.base_url}: {error.reason}") from error

    def login(self, email: str, password: str) -> dict:
        request = Request(
            self._url("/auth/login"),
            data=urlencode({"username": email, "password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"Login for {email} returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Could not reach API at {self.base_url}: {error.reason}") from error


class Checks:
    def __init__(self):
        self.rows: list[tuple[str, str, str, bool]] = []

    def add(self, name: str, expected: str, actual: str, passed: bool) -> None:
        self.rows.append((name, expected, actual, bool(passed)))

    def print_table(self) -> None:
        print(f"\n{'CHECK':<45} | {'EXPECTED':<45} | {'ACTUAL':<52} | STATUS")
        print("-" * 154)
        for name, expected, actual, passed in self.rows:
            print(f"{name:<45} | {expected:<45} | {actual:<52} | {'PASS' if passed else 'FAIL'}")
        print("-" * 154)
        print(f"{sum(row[3] for row in self.rows)}/{len(self.rows)} checks passed.")

    @property
    def passed(self) -> bool:
        return bool(self.rows) and all(row[3] for row in self.rows)


def _credential(role_name: str, name_starts_with: str | None = None) -> dict:
    for entry in DEMO_CREDENTIALS:
        if entry["role_name"] == role_name and (
            name_starts_with is None or entry["name"].startswith(name_starts_with)
        ):
            return entry
    raise RuntimeError(f"No seed credential found for {role_name} {name_starts_with or ''}".strip())


def _login_roles(client: ApiClient, checks: Checks) -> dict[str, str]:
    role_specs = (
        ("OWNER", "OWNER", None),
        ("ADMIN", "ADMIN", None),
        ("PRODUCTION", "PRODUCTION", None),
        ("ACCOUNTANT", "ACCOUNTANT", None),
        ("SALESMAN_A", "SALESMAN", "Salesman A"),
        ("SALESMAN_B", "SALESMAN", "Salesman B"),
    )
    tokens = {}
    for key, role_name, name_starts_with in role_specs:
        credential = _credential(role_name, name_starts_with)
        response = client.login(credential["email"], credential["password"])
        token = response.get("access_token")
        if not token:
            raise RuntimeError(f"Login for {credential['email']} returned no access token.")
        profile = client.request("GET", "/auth/me", token)
        actual_role = profile.get("role", "missing")
        checks.add(f"Login: {credential['name']}", role_name, actual_role, actual_role == role_name)
        tokens[key] = token
    return tokens


def _ensure_clean(client: ApiClient, owner_token: str, checks: Checks) -> None:
    paths = ("/purchases", "/production", "/orders", "/invoices", "/payments", "/overheads")
    counts = {path: len(client.request("GET", path, owner_token)) for path in paths}
    existing = sum(counts.values())
    checks.add("Clean starting database", "0 benchmark transactions", f"{existing} transactions", existing == 0)
    if existing:
        raise DirtyBenchmarkState


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _money(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def _stock_map(client: ApiClient, token: str) -> dict[str, dict]:
    return {item["name"]: item for item in client.request("GET", "/stock/summary", token)}


def _apply_section5(client: ApiClient, tokens: dict[str, str], checks: Checks) -> None:
    owner = tokens["OWNER"]
    admin = tokens["ADMIN"]
    production = tokens["PRODUCTION"]
    items = client.request("GET", "/items", owner)
    item_by_name = {item["name"]: item for item in items}
    products = client.request("GET", "/products", owner)
    customers = client.request("GET", "/customers", owner)
    suppliers = client.request("GET", "/suppliers", owner)
    product = next(item for item in products if item["pack_name"] == "Murukku 200 g")
    retailer_a = next(item for item in customers if item["gstin"] == "33AAAAA0000A1Z5")
    distributor_b = next(item for item in customers if item["gstin"] == "29BBBBB1111B1Z2")
    supplier = next(item for item in suppliers if item["gstin"] == "33AAAAA1111A1Z1")

    # Section 5, step 1: receive 60 kg flour at Rs 45/kg.
    client.request("POST", "/purchases", admin, {
        "supplier_id": supplier["id"],
        "supplier_invoice_no": f"SECTION5-{uuid4().hex[:12]}",
        "notes": "Section 5 benchmark flour purchase",
        "lines": [{
            "item_id": item_by_name["Flour"]["id"],
            "quantity_entered": "60",
            "unit_entered": "kg",
            "rate_paise": 4500,
        }],
    })
    stock = _stock_map(client, owner)
    flour_kg = Decimal(stock["Flour"]["closing_balance_base"]) / 1000
    flour_wac = _decimal(stock["Flour"]["weighted_avg_cost_paise"])
    checks.add("Flour after purchase", "160 kg", f"{flour_kg:.0f} kg", flour_kg == 160)
    checks.add("Flour post-purchase WAC", "4.312500 paise/g", f"{flour_wac:.6f} paise/g",
               flour_wac == Decimal("4.312500"))

    # Steps 2-3: record actuals, then post the production run.
    run = client.request("POST", "/production", production, {
        "product_id": product["id"],
        "batches": "1.0000",
        "notes": "Section 5 benchmark production run",
    })
    run_id = run["id"]
    client.request("PATCH", f"/production/{run_id}", production, {
        "actual_good_packets": 188,
        "lines": [
            {"item_id": item_by_name["Flour"]["id"], "actual_qty_base": 40000},
            {"item_id": item_by_name["Cooking oil"]["id"], "actual_qty_base": 10500},
            {"item_id": item_by_name["Salt and spice mix"]["id"], "actual_qty_base": 1200},
            {"item_id": item_by_name["200 g pouch"]["id"], "damaged_qty_base": 6},
            {"item_id": item_by_name["Carton"]["id"], "actual_qty_base": 9},
        ],
    })
    client.request("POST", f"/production/{run_id}/post", production, {})
    run = client.request("GET", f"/production/{run_id}", owner)
    stock = _stock_map(client, owner)
    flour_kg = Decimal(stock["Flour"]["closing_balance_base"]) / 1000
    oil_l = Decimal(stock["Cooking oil"]["closing_balance_base"]) / 1000
    spice_kg = Decimal(stock["Salt and spice mix"]["closing_balance_base"]) / 1000
    pouch_count = stock["200 g pouch"]["closing_balance_base"]
    carton_count = stock["Carton"]["closing_balance_base"]
    finished_after_run = stock["Murukku 200 g"]["closing_balance_base"]
    checks.add("Flour after production", "120 kg", f"{flour_kg:.0f} kg", flour_kg == 120)
    checks.add("Cooking oil after production", "19.5 L", f"{oil_l:.1f} L", oil_l == Decimal("19.5"))
    checks.add("Spice after production", "3.8 kg", f"{spice_kg:.1f} kg", spice_kg == Decimal("3.8"))
    checks.add("Pouches after production", "306", str(pouch_count), pouch_count == 306)
    checks.add("Cartons after production", "21", str(carton_count), carton_count == 21)
    checks.add("Finished goods after production", "238 packets", f"{finished_after_run} packets",
               finished_after_run == 238)
    checks.add("Production good output", "188 packets", f"{run['actual_good_packets']} packets",
               run["actual_good_packets"] == 188)

    variance_lines = {line["item_name"]: line for line in run["variance_report"]["lines"]}
    yield_report = run["variance_report"]["yield_report"]
    variance_checks = (
        ("Yield variance", yield_report["yield_variance_pct"], yield_report["is_flagged"],
         Decimal("-6.00"), True),
        ("Oil variance", variance_lines["Cooking oil"]["variance_pct"],
         variance_lines["Cooking oil"]["is_flagged"], Decimal("5.00"), True),
        ("Carton variance", variance_lines["Carton"]["variance_pct"],
         variance_lines["Carton"]["is_flagged"], Decimal("-10.00"), True),
        ("Pouch variance", variance_lines["200 g pouch"]["variance_pct"],
         variance_lines["200 g pouch"]["is_flagged"], Decimal("-3.00"), False),
    )
    for label, raw_value, flagged, expected_value, expected_flagged in variance_checks:
        value = _decimal(raw_value)
        actual = f"{value:+.2f}% ({'Flagged' if flagged else 'Not flagged'})"
        expected = f"{expected_value:+.2f}% ({'Flagged' if expected_flagged else 'Not flagged'})"
        checks.add(label, expected, actual, value == expected_value and flagged is expected_flagged)
    checks.add("Material cost", "Rs 4,055.00", _money(run["total_material_cost_paise"]),
               run["total_material_cost_paise"] == 405500)

    # Step 4: add Rs 1,200 labour and Rs 600 gas to the posted run.
    for category, amount in (("LABOUR", 120000), ("GAS", 60000)):
        client.request("POST", "/overheads", production, {
            "category": category,
            "amount_paise": amount,
            "production_run_id": run_id,
            "description": f"Section 5 benchmark {category.lower()}",
        })
    run_cost = client.request("GET", f"/costing/runs/{run_id}", owner)
    checks.add("Direct overheads", "Rs 1,800.00", _money(run_cost["total_overheads_paise"]),
               run_cost["total_overheads_paise"] == 180000)
    checks.add("Total production cost", "Rs 5,855.00", _money(run_cost["total_cost_paise"]),
               run_cost["total_cost_paise"] == 585500)
    cost = client.request("GET", f"/costing/products?product_id={product['id']}", owner)[0]
    cost_per_packet = _decimal(cost["cost_per_packet"])
    margin_pct = _decimal(cost["margin_pct"])
    checks.add("Cost per packet", "Rs 31.14", f"Rs {cost_per_packet:.2f}",
               cost_per_packet == Decimal("31.14"))
    checks.add("Selling price per packet", "Rs 50.00", f"Rs {_decimal(cost['selling_price']):.2f}",
               _decimal(cost["selling_price"]) == Decimal("50.00"))
    checks.add("Margin", "37.7%", f"{margin_pct:.1f}%", margin_pct == Decimal("37.7"))

    # Steps 5-8: Retailer A order, approval, invoice, dispatch, and part payment.
    order_a = client.request("POST", "/orders", tokens["SALESMAN_A"], {
        "client_uuid": f"section5-retailer-{uuid4()}",
        "customer_id": retailer_a["id"],
        "lines": [{"product_id": product["id"], "quantity_packets": 150}],
    })
    client.request("POST", f"/orders/{order_a['id']}/approve", admin, {})
    invoice = client.request("POST", f"/orders/{order_a['id']}/invoice", admin, {})
    invoice_actual = (
        f"{_money(invoice['taxable_total_paise'])} + "
        f"{_money(invoice['cgst_total_paise'])} CGST + "
        f"{_money(invoice['sgst_total_paise'])} SGST = {_money(invoice['grand_total_paise'])}"
    )
    invoice_expected = "Rs 7,500.00 + Rs 187.50 CGST + Rs 187.50 SGST = Rs 7,875.00"
    invoice_ok = (
        invoice["taxable_total_paise"] == 750000
        and invoice["cgst_total_paise"] == 18750
        and invoice["sgst_total_paise"] == 18750
        and invoice["igst_total_paise"] == 0
        and invoice["grand_total_paise"] == 787500
    )
    checks.add("Retailer A invoice and GST", invoice_expected, invoice_actual, invoice_ok)
    client.request("POST", f"/invoices/{invoice['id']}/dispatch", admin, {})
    client.request("POST", "/payments", admin, {
        "customer_id": retailer_a["id"],
        "amount_paise": 400000,
        "mode": "UPI",
        "allocations": [{"invoice_id": invoice["id"], "amount_paise": 400000}],
    })
    summary = client.request("GET", "/dashboard/summary?range=today", owner)
    outstanding = summary["receivables"]["total_outstanding_paise"]
    checks.add("Retailer A outstanding", "Rs 3,875.00", _money(outstanding), outstanding == 387500)
    stock_after_dispatch = _stock_map(client, owner)
    finished_after_dispatch = stock_after_dispatch["Murukku 200 g"]["closing_balance_base"]
    checks.add("Finished goods after dispatch", "88 packets", f"{finished_after_dispatch} packets",
               finished_after_dispatch == 88)

    # Step 9: Salesman B submits 120 packets; show shortage and estimated IGST.
    order_b = client.request("POST", "/orders", tokens["SALESMAN_B"], {
        "client_uuid": f"section5-distributor-{uuid4()}",
        "customer_id": distributor_b["id"],
        "lines": [{"product_id": product["id"], "quantity_packets": 120}],
    })
    order_b = client.request("GET", f"/orders/{order_b['id']}", owner)
    shortage = order_b["stock_availability"][0]["shortage"]
    checks.add("Distributor B shortage", "Short by 32 packets", f"Short by {shortage} packets",
               shortage == 32 and order_b["status"] == "SUBMITTED")
    estimated_igst = order_b["estimated_tax"]["igst_paise"]
    checks.add("Distributor B estimated IGST", "Rs 300.00", _money(estimated_igst),
               estimated_igst == 30000 and order_b["status"] == "SUBMITTED")


def _run(*, show_table: bool) -> bool:
    checks = Checks()
    client = ApiClient(API_BASE_URL)
    print(f"API: {API_BASE_URL}")
    try:
        tokens = _login_roles(client, checks)
        _ensure_clean(client, tokens["OWNER"], checks)
        _apply_section5(client, tokens, checks)
    except DirtyBenchmarkState:
        print("Reset with docker compose down -v")
    except Exception as error:
        print(f"HTTP benchmark failed: {error}")
        checks.add("HTTP workflow", "completed", str(error), False)
    if show_table:
        checks.print_table()
        print("\nALL SECTION 5 CHECKS PASSED." if checks.passed else "\nSECTION 5 CHECKS FAILED.")
    elif checks.passed:
        print("Section 5 demo transactions applied via HTTP API.")
    else:
        print("Section 5 demo state was not fully applied; inspect the error above.")
    return checks.passed


def run_benchmark() -> bool:
    return _run(show_table=True)


def apply_benchmark_state() -> bool:
    return _run(show_table=False)


if __name__ == "__main__":
    sys.exit(0 if run_benchmark() else 1)
