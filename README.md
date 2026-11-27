# Order-to-Audit

Order-to-Audit is a business application for a food manufacturer to track orders, inventory, production, invoicing, and audit data. Its FastAPI backend stores business records in PostgreSQL and exposes authenticated APIs. The React and TypeScript frontend provides role-specific screens, and Docker Compose runs the database, backend, and frontend together.

## Repository map

- `backend/app/` — FastAPI application, API routers, database models, schemas, and business services.
- `backend/alembic/` — database schema migrations.
- `backend/scripts/seed.py` — idempotent benchmark and demo-account seed.
- `backend/tests/` — backend API, business-rule, and seed tests.
- `frontend/src/app/` — routing and application shell.
- `frontend/src/features/` — authentication, owner dashboard, and salesman order screens.
- `frontend/src/lib/` — shared API and frontend utilities.
- `scripts/run_benchmark.py` — Section 5 benchmark checks.
- `scripts/seed_demo_volume.py` — optional extra demo data; not run by the default startup.
- `docker-compose.yml` — default database, migration/seed, backend, and frontend services.
- `docker-compose.dev.yml` — development reload and backend source mount.
- `Makefile` — common Compose, test, reset, and benchmark commands.

## Run with Docker Compose

Requirements: Docker Engine with the Compose plugin.

```sh
docker compose up --build
```

The backend waits for PostgreSQL, runs `alembic upgrade head`, runs the idempotent seed, then starts Uvicorn. The default Compose file does not mount backend source or enable reload.

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

The database is exposed on host port `5434` by default. To enable the demo-login panel, copy `.env.example` to `.env`, set `VITE_DEMO_MODE=true`, then rebuild with `docker compose up --build`. The demo panel is hidden by default.

To stop services and remove the seeded database volume:

```sh
docker compose down -v
```

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
| Accountant | `accountant@foodmfr.local` | `AcctPass123!` | GST invoices, receivables, payment allocation, and audit reports |
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

## Stack and rationale

The backend uses FastAPI, SQLAlchemy, Alembic, and PostgreSQL for typed HTTP APIs, relational persistence, and versioned schema changes. The frontend uses React, TypeScript, TanStack Query, and Vite to provide role-aware screens and API-backed data. Docker Compose makes the database, migrations, seed, API, and frontend reproducible as one local stack.

## Feature status

The repository does not include the Section 6 rubric text, so the following is an implementation inventory grouped under the requested headings, not a claim that it matches an unavailable rubric.

### Must-have

- **Done** — JWT login, role-based access checks, and role-specific landing pages.
- **Done** — Salesman order entry and customer assignment for the two seeded salesmen.
- **Done** — Inventory ledger, production runs, weighted-average costing, and variance calculations in the backend.
- **Done** — Invoice, payment, and receivables backend workflows.
- **Partial** — Overview dashboard uses API-backed inventory, sales, orders, variance, costing, and receivables data; some non-dashboard modules are placeholders.

### Should-have

- **Done** — Idempotent benchmark seed and an executable Section 5 benchmark.
- **Done** — Audit-oriented stock movements, order history, and invoice/credit-note domain workflows.
- **Partial** — Role-restricted Production, Stock, Receivables, and Reports pages exist in the frontend shell but currently display placeholder content.
- **Partial** — Salesman order flow supports offline-oriented client behavior; full offline synchronization coverage is not established by the repository's tests.

### Stretch

- **Done** — Docker Compose development override with backend reload and source mounting.
- **Done** — Optional demo-volume seed script, separate from the default benchmark seed.
- **Not done** — Hosted deployment URL and live-service verification.
- **Not done** — A Section 6-specific completion assessment; its rubric is not present in the repository.

## Business assumptions

- GST rate for the benchmark finished product: **5%**.
- Item HSN codes are seeded as master data (for example, finished Murukku `1905`); tax treatment follows the item/customer/company state data.
- Financial year starts in **April** and ends in **March**.
- Invoice identifiers use the backend format `INV/YYYY-YY/NNNN` (for example, `INV/2026-27/0001`); order identifiers use `ORD-YYYY-NNNN`.
- Amounts are represented in paise. GST components are rounded independently to whole paise using `ROUND_HALF_UP`; other calculated money values use decimal half-up rounding.
- Sales quantities for the benchmark finished product are measured in **packets**.

## Section 5 benchmark

With backend dependencies installed and the Compose database running, run the real database checks:

```sh
make benchmark
```

The following values are from the repository's `scripts/run_benchmark.py` output against the seeded database:

| Check | Expected | Actual | Result |
|---|---:|---:|---|
| Flour post-purchase WAC | 4.312500 paise/g | 4.312500 paise/g | PASS |
| Flour post-run inventory | 120.0 kg | 120.0 kg | PASS |
| Cooking oil post-run inventory | 19.5 L | 19.5 L | PASS |
| Spice mix post-run inventory | 3.8 kg | 3.8 kg | PASS |
| 200 g pouch post-run inventory | 306 pieces | 306 pieces | PASS |
| Carton post-run inventory | 21 pieces | 21 pieces | PASS |
| Murukku 200 g finished stock after dispatch | 88 packets | 88 packets | PASS |
| Production good-packet output | 188 packets | 188 packets | PASS |
| Oil variance | +5.00% (Flagged) | +5.00% (Flagged) | PASS |
| Carton variance | -10.00% (Flagged) | -10.00% (Flagged) | PASS |
| Pouch variance | -3.00% (Not flagged) | -3.00% (Not flagged) | PASS |
| Yield variance | -6.00% (Flagged) | -6.00% (Flagged) | PASS |
| Run material cost | Rs 4,055.00 | Rs 4,055.00 | PASS |
| Direct overheads (Labour + Gas) | Rs 1,800.00 | Rs 1,800.00 | PASS |
| Total run cost | Rs 5,855.00 | Rs 5,855.00 | PASS |
| Cost per packet (Weighted Average) | Rs 31.14 | Rs 31.14 | PASS |
| Selling price per packet | Rs 50.00 | Rs 50.00 | PASS |
| Gross commercial margin | 37.7% | 37.7% | PASS |
| Retailer A invoice total (150 packets + 5% GST) | Rs 7,875.00 | Rs 7,875.00 | PASS |
| Retailer A outstanding after Rs 4,000 payment | Rs 3,875.00 | Rs 3,875.00 | PASS |
| Distributor B order shortage | Short by 32 packets | Short by 32 packets | PASS |

The valuation method is moving weighted average: material issues are valued at the moving weighted-average cost. All shift overheads (Labour Rs 1,200 and Gas Rs 600) are divided over the **188 good packets**; damaged or scrap packets do not absorb inventory value. The benchmark weighted-average result is **Rs 31.14 per packet**. The FIFO comparison in the benchmark script is **Rs 30.90 per packet**.

The benchmark has three variance alerts: oil at +5%, yield at -6%, and cartons at -10%. Pouches at -3.0% are not flagged because the threshold is strictly greater than 3%. Distributor B's submitted order is 120 packets while only 88 are available, so it is shown as a 32-packet shortage with an estimated inter-state GST (IGST) amount; it is not an invoice.

To add optional volume after starting the database, run:

```sh
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5434/order_to_audit backend/.venv/bin/python scripts/seed_demo_volume.py
```

This is not part of the default Compose startup or the benchmark seed.

## Audit trail and invoice edits

Posted invoices are immutable. Changes made to an order before invoicing are recorded in its order history. Invoice cancellation is represented by a credit note rather than editing a posted invoice.

## Known gaps

- The frontend's Production, Stock, Receivables, and Reports routes currently show placeholder pages; backend workflows exist for related operations.
- The Section 6 rubric is not included in this repository, so its requested tier-by-tier rubric compliance cannot be independently verified here.
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
