# Order-to-Audit

Order-to-Audit is a business application for a food manufacturer to track orders, inventory, production, invoicing, and audit data. Its FastAPI backend stores business records in PostgreSQL and exposes authenticated APIs. The React and TypeScript frontend provides role-specific screens, and Docker Compose runs the database, backend, and frontend together.

## Repository map

- `backend/app/` — FastAPI application, API routers, database models, schemas, and business services.
- `backend/alembic/` — database schema migrations.
- `backend/scripts/seed.py` — idempotent master-data, opening-stock, and demo-account seed.
- `backend/tests/` — backend API, business-rule, and seed tests.
- `frontend/src/app/` — routing and application shell.
- `frontend/src/features/` — authentication, owner dashboard, and salesman order screens.
- `frontend/src/lib/` — shared API and frontend utilities.
- `scripts/apply_benchmark_state.py` — applies Section 5 transactions through the API.
- `scripts/run_benchmark.py` — Section 5 HTTP workflow and result checks.
- `scripts/seed_demo_volume.py` — optional extra demo data; not run by the default startup.
- `docker-compose.yml` — default database, migration/seed, backend, and frontend services.
- `docker-compose.dev.yml` — development reload and backend source mount.
- `Makefile` — common Compose, test, reset, and benchmark commands.

## Run with Docker Compose

Requirements: Docker Engine with the Compose plugin.

```sh
docker compose up --build
```

The backend waits for PostgreSQL, runs `alembic upgrade head`, loads idempotent master data and opening stock, then starts Uvicorn. It does not create purchases, production runs, orders, invoices, or payments by default. The default Compose file does not mount backend source or enable reload.

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

The database is exposed on host port `5434` by default. To enable the demo-login panel, copy `.env.example` to `.env`, set `VITE_DEMO_MODE=true`, then rebuild with `docker compose up --build`. The demo panel is hidden by default.

To stop services and remove the seeded database volume:

```sh
docker compose down -v
```

The default database contains only master data and opening stock. It creates no purchases, production runs, orders, invoices, or payments. To apply the Section 5 transactions for screenshots, run this after Compose is up:

```sh
make demo-state
```

`make demo-state` uses the same HTTP workflow as the benchmark but does not print the assertion table. Both commands require an untouched transaction database. To return to the clean seeded state, reset with `docker compose down -v` and start Compose again.

To use the development override (backend reload and source mount):

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### Non-Docker development

Use Python 3.12, Node.js/npm, and a running PostgreSQL instance. From the repository root, create a backend environment and install dependencies:

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

Set `DATABASE_URL` to the local PostgreSQL connection string and set one stable `SECRET_KEY` value in the shell. From `backend/`, run the schema migration, seed, and API:

```sh
cd backend
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/order_to_audit
export SECRET_KEY='replace-with-a-stable-secret-of-at-least-32-characters'
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py
.venv/bin/uvicorn app.main:app --reload
```

Run the frontend in a second terminal:

```sh
cd frontend
VITE_DEMO_MODE=true npm run dev
```

The Vite development server is available at http://localhost:3000.

## Demo logins

These are demo-only credentials created by the seed. The seed contains six accounts: one for each of the five roles, plus a second salesman assigned to Distributor B. The role descriptions below summarize the access configured for the demo accounts.

| Role | Email | Password | Demo access |
|---|---|---|---|
| Owner | `owner@foodmfr.local` | `OwnerPass123!` | Executive overview, costing, variance alerts, receivables, and telemetry |
| Admin | `admin@foodmfr.local` | `AdminPass123!` | System configuration, users, master data, and order approval |
| Production | `production@foodmfr.local` | `ProdPass123!` | BOMs, production runs, consumption, and variance alerts |
| Accountant | `accountant@foodmfr.local` | `AcctPass123!` | Read-only GST invoices, receivables, stock, orders; reports & exports (CSV/XLSX/PDF); audit history |
| Salesman A | `salesman.a@foodmfr.local` | `SalesPass123!` | Mobile order booking and pricing catalog for Retailer A |
| Salesman B | `salesman.b@foodmfr.local` | `SalesPass123!` | Mobile order booking and pricing catalog for Distributor B |

The first request can be slow when the application is hosted on a free tier that suspends idle services.

## Hosted deployment

**Hosted URL:** _To be added after deployment._

For Render or Railway, provision a managed PostgreSQL database and configure `DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, and the frontend's `VITE_DEMO_MODE` build argument as appropriate. Set `SECRET_KEY` once as a stable secret; do not generate a new value at each start, because existing access tokens are signed with it. The backend start command must migrate and seed before Uvicorn:

```sh
alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use the platform-provided database URL and set production CORS origins for the deployed frontend. Do not use the development fallback secret or demo credentials for a public production deployment.

## Design note

See [`docs/design-note.md`](docs/design-note.md) — data model / ER diagram, stock-ledger invariants, BOM scaling & unit conversion, variance, and **costing + valuation method** (moving weighted average; FIFO comparison; overhead allocation). See also [`docs/code-walkthrough.md`](docs/code-walkthrough.md).

## Stack and rationale

The backend uses FastAPI, SQLAlchemy, Alembic, and PostgreSQL for typed HTTP APIs, relational persistence, and versioned schema changes. The frontend uses React, TypeScript, TanStack Query, and Vite to provide role-aware screens and API-backed data. Docker Compose makes the database, migrations, seed, API, and frontend reproducible as one local stack.

## Feature status

Mapped to the internship task's **Section 6 scope tiers**. This inventory reflects what is implemented and verified; it is not a claim beyond the repository.

### Must have (minimum to be considered) — all **Done**

- **Login with at least three roles** (salesman, admin, production) — **Done**: JWT login, **5 roles** (OWNER/ADMIN/PRODUCTION/ACCOUNTANT/SALESMAN), role-specific landing + sidebar, 403 on unauthorized. Six seeded demo accounts.
- **Product, customer, raw-material and BOM masters** — **Done**: `products`, `customers`, `items` (raw + packaging + finished), `boms`/`bom_items`, `suppliers`, admin master-data screens + CRUD APIs.
- **Mobile-friendly order entry and admin approval** — **Done**: salesman order screen (works on mobile, offline), admin approve/reject/edit.
- **GST invoice as PDF** — **Done**: immutable GST invoice + ReportLab PDF + WhatsApp share link.
- **Production run updates raw-material and finished-goods stock automatically** — **Done**: atomic `PRODUCTION_ISSUE` + `PRODUCTION_OUTPUT`, shortage check.
- **Planned vs actual consumption and yield, variance shown** — **Done**: per-line variance + yield variance + **flagged** chips, strict >tolerance (default 3%).
- **Stock summary and stock ledger** — **Done**: append-only `stock_movements`, running balance, source-document links, reconcile; tabs raw/packaging/finished.
- **Sales register and stock report, exportable to Excel/CSV** — **Done**: `sales_register` + `stock_summary`, CSV + **XLSX** + PDF.

### Should have — all **Done**

- **Purchases and supplier records** — **Done**.
- **Payments, outstanding and ageing** — **Done**: FIFO/explicit allocation, advance, reverse, outstanding, ageing buckets, statement.
- **Cost per packet with overheads** — **Done**: material + labour/gas/power/other ÷ good packets; **moving weighted average**; FIFO shown as comparison only.
- **GST summary report** — **Done**: `gst_outward` GSTR-1 / GSTR-3B 3.1(a) + HSN.
- **Variance alerts beyond a tolerance** — **Done** (line + yield, strict >3%).
- **Owner dashboard** — **Done**: KPIs, sales trend, variance, costing, receivables ageing, telemetry.
- Also **Done**: audit trail; order + invoice history; **credit notes**; immutable posted invoices; gapless numbering; **Section 5 benchmark verified** (`make benchmark`, 31/31); accountant read-only; offline-oriented salesman; reconcile.

### Stretch goals (bonus once must-haves work) — picked

- **Done — Offline order capture with sync** (IndexedDB outbox + sync engine + `client_uuid` idempotency).
- **Partial — Batch and expiry tracking**: `stock_movements.batch_no`/`expiry_date` columns + `post_movement()` args; **not** exposed via API/UI and **not** FEFO dispatch.
- **Partial — Reorder levels and low-stock alerts**: `items.reorder_level` + owner-dashboard low-stock (falls back to lowest-5); setting reorder level is admin/master-data, not a dedicated alert screen.
- **Done — Docker Compose development override**; **optional demo-volume seed** (not default).
- **Not done** — production planning from pending orders ("to fulfil today's orders, make N batches"); salesman route/visit log + GPS check-in; **Tally-compatible export**; e-Invoice / e-Way Bill mock government API; Tamil-language floor-staff UI. See **Known gaps**.
- **Not done** — hosted live link (`Hosted URL` to be added) and **demo video** (deliverable #4; not producible in-repo). Local `make up` / `make benchmark` works.

### Core scope notes

- **Work-in-progress stock** (Section 4.4 optional) is **not** modeled; only raw / packaging / finished goods.
- **Customer-specific prices / schemes** (Section 4.1 optional) use seeded **price lists**; full per-customer schemes are optional and not built.
- **Salesman customer-wise sales** (Section 3): salesman sees own order status; customer-wise view is via statement on own customers, not a full salesman sales report. Reports are not available to salesmen.
- **Posted invoices are immutable**; PUT/PATCH/DELETE return **409** + audit `edit_rejected`; correction = **credit note**. **Stock movements** and **audit log** are append-only (DB triggers); payments are reversed, not edited.

## Endpoint list per screen

All API routes are mounted under `/api/v1` (and re-exported at root). Writes require the roles shown; accountant is read-only.

### Owner Overview (`/`, OWNER)
- `GET /dashboard/summary?range=today|7d|30d`
- `GET /orders?status=SUBMITTED`

### Admin Orders (`/orders`, ADMIN; read-only for ACCOUNTANT)
- `GET /orders`, `GET /orders/{id}`
- `PATCH /orders/{id}` (edit lines, admin)
- `POST /orders/{id}/approve`, `POST /orders/{id}/reject`, `POST /orders/{id}/invoice` (admin)

### Salesman New Order (`/orders/new`, SALESMAN + owner/admin)
- `GET /customers`, `GET /products`, `POST /orders`, `GET /orders` (salesman-scoped); offline IndexedDB outbox synced via `POST /orders`

### Salesman My Orders (`/orders/my`, `/orders`, SALESMAN)
- Local IndexedDB outbox; `POST /orders`, `GET /orders` (salesman-scoped); offline sync engine

### Invoices (`/invoices`, ADMIN + ACCOUNTANT; read-only for ACCOUNTANT)
- `GET /invoices`, `GET /invoices/{id}`, `GET /invoices/{id}/pdf`, `GET /invoices/{id}/share-link`, `GET /invoices/{id}/history`
- `POST /orders/{id}/invoice`, `POST /invoices/{id}/dispatch`, `POST /invoices/{id}/credit-note`, `GET /invoices/credit-notes/{id}/pdf` (dispatch/credit admin); `GET /invoices/{id}/share-link`
- invoice is created from an approved order; grand total for Retailer A benchmark = Rs 7,500 + Rs 187.50 CGST + Rs 187.50 SGST = **Rs 7,875.00**

### Receivables (`/receivables`, ADMIN + ACCOUNTANT; read-only for ACCOUNTANT)
- `GET /receivables/outstanding`, `GET /receivables/ageing`, `GET /receivables/collections`, `GET /customers/{id}/statement`
- `POST /payments` (record payment, FIFO or explicit allocation; admin), `GET /payments`, `POST /payments/{id}/reverse`, `POST /customers/{id}/allocate-advance`
- benchmark: Rs 7,875 invoice − Rs 4,000 payment → outstanding **Rs 3,875.00**

### Purchases (`/purchases`, OWNER/ADMIN/PRODUCTION)
- `GET /suppliers`, `GET /items`, `GET /purchases`, `GET /purchases/{id}`, `POST /purchases`, `POST /purchases/{id}/cancel` (cancel admin)

### Stock (`/stock`, OWNER/ADMIN/PRODUCTION/ACCOUNTANT read-only for accountant)
- `GET /stock/summary`, `GET /stock/ledger?item_id=`, `GET /stock/reconcile`, `POST /stock/adjustments` (admin)

### Production (`/production`, OWNER/ADMIN/PRODUCTION; backend read ADMIN/OWNER/ACCOUNTANT/PRODUCTION, write ADMIN/PRODUCTION)
- `GET /production`, `GET /production/{id}`, `GET /products`, `GET /boms`
- `POST /production`, `PATCH /production/{id}`, `POST /production/{id}/post`, `POST /production/{id}/cancel`
- `GET /costing/runs/{id}`, `GET /costing/products`, `POST /overheads`
- variance chips: oil +5.0%, yield −6.0%, cartons −10.0% flagged; pouches −3.0% not flagged (strict >3%); flour 120 kg after purchase+production

### Reports (`/reports`, OWNER/ADMIN/ACCOUNTANT; PRODUCTION stock+production only; SALESMAN none)
- `GET /reports` (list for role), `GET /reports/{name}?from=&to=&as_of=&format=json|csv|xlsx|pdf`
- business dates are plain IST dates; money paise internally; CSV plain decimals; XLSX numeric + header + freeze + autofilter + totals; every export logs `REPORT_EXPORTED` in `audit_log`
- reports: `sales_register`, `stock_summary`, `stock_ledger`, `gst_outward`, `purchase_register`, `production_report`, `collections_outstanding`, `sales_by_customer_product`

## Business assumptions

- GST rate for the benchmark finished product: **5%**.
- Item HSN codes are seeded as master data (for example, finished Murukku `1905`); tax treatment follows the item/customer/company state data.
- Financial year starts in **April** and ends in **March**.
- Invoice identifiers use the backend format `INV/YYYY-YY/NNNN` (for example, `INV/2026-27/0001`); order identifiers use `ORD-YYYY-NNNN`.
- Amounts are represented in paise. GST components are rounded independently to whole paise using `ROUND_HALF_UP`; other calculated money values use decimal half-up rounding.
- Sales quantities for the benchmark finished product are measured in **packets**.

## Section 5 benchmark

The database must be in the default master-data-only state. `make benchmark` logs in through the API as Owner, Admin, Production, Accountant, Salesman A, and Salesman B, executes Section 5 steps 1–9, and checks the results. It stops with `Reset with docker compose down -v` if it finds existing transactions; run it once per reset. The default API URL includes `/api/v1`; override it when needed:

```sh
make benchmark
```

```sh
API_BASE_URL=http://localhost:8000/api/v1 make benchmark
```

`make demo-state` executes those same transactions through the API without the benchmark result table, for screenshots. It also requires a clean database. Fresh HTTP execution on a clean seeded database: **`make benchmark`, 31/31 checks passed**.

| Check | Expected | Actual | Result |
|---|---:|---:|---|
| Owner, Admin, Production, Accountant, and both Salesmen log in | Six role-correct sessions | Six role-correct sessions | Pass |
| Flour after purchase, then production | 160 kg, then 120 kg | 160 kg, then 120 kg | Pass |
| Finished goods after production, then dispatch | 238 packets, then 88 packets | 238 packets, then 88 packets | Pass |
| Oil, spice, pouches, cartons after production | 19.5 L, 3.8 kg, 306, 21 | 19.5 L, 3.8 kg, 306, 21 | Pass |
| Yield, oil, carton, pouch variance | -6.00% flagged; +5.00% flagged; -10.00% flagged; -3.00% not flagged | -6.00% flagged; +5.00% flagged; -10.00% flagged; -3.00% not flagged | Pass |
| Material cost and overheads | Rs 4,055.00 and Rs 1,800.00 | Rs 4,055.00 and Rs 1,800.00 | Pass |
| Total production cost, cost per packet, selling price, margin | Rs 5,855.00; Rs 31.14; Rs 50.00; 37.7% | Rs 5,855.00; Rs 31.14; Rs 50.00; 37.7% | Pass |
| Retailer A invoice | Rs 7,500.00 + Rs 187.50 CGST + Rs 187.50 SGST = Rs 7,875.00 | Rs 7,500.00 + Rs 187.50 CGST + Rs 187.50 SGST = Rs 7,875.00 | Pass |
| Retailer A outstanding after Rs 4,000 payment | Rs 3,875.00 | Rs 3,875.00 | Pass |
| Distributor B order and IGST estimate | Short by 32 packets; Rs 300.00 IGST | Short by 32 packets; Rs 300.00 IGST | Pass |

The valuation method is moving weighted average: material issues are valued at the moving weighted-average cost. All shift overheads (Labour Rs 1,200 and Gas Rs 600) are divided over the **188 good packets**; damaged or scrap packets do not absorb inventory value. The expected weighted-average result is **Rs 31.14 per packet**. Under the FIFO alternative, using the earlier Rs 42/kg flour lot, the comparison is **Rs 30.90 per packet**.

The benchmark has three variance alerts: oil at +5%, yield at -6%, and cartons at -10%. Pouches at -3.0% are not flagged because the threshold is strictly greater than 3%. Distributor B's submitted order is 120 packets while only 88 are available, so it is shown as a 32-packet shortage with an estimated inter-state GST (IGST) amount; it is not an invoice.

To add optional volume after starting the database, run:

```sh
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5434/order_to_audit backend/.venv/bin/python scripts/seed_demo_volume.py
```

This is not part of the default Compose startup or the benchmark seed.

## Audit trail and invoice edits

Posted invoices are immutable. Changes made to an order before invoicing are recorded in its order history. Invoice cancellation is represented by a credit note rather than editing a posted invoice.

## Known gaps

- The `/reports` Reports page covers operational reports; GSTR-1/3B output is exposed as `gst_outward` JSON/CSV/XLSX/PDF, not a filed return.
- Section 6 tiers are mapped in **Feature status**; this is a self-assessment, not external verification.
- No hosted URL is configured yet.
- Demo accounts and their passwords are intended only for local evaluation.
- The default Compose secret is a development fallback; set a unique stable `SECRET_KEY` for deployment.

## Tests

Install the backend and frontend dependencies as described under [Non-Docker development](#non-docker-development), then run from the repository root:

```sh
make test-backend
make test-frontend
```

To run both suites:

```sh
make test
```
