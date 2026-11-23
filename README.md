# Order-to-Audit System Backend

Backend scaffolding for a food manufacturer "Order-to-Audit" system (salesmen order placement, admin GST invoicing, production supervisor BOM-based run logging, and accountant reports).

## Tech Stack

- **Framework**: FastAPI (Python 3.12)
- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.x (Typed, `Mapped[]` style with declarative constraint naming)
- **Migrations**: Alembic
- **Validation & Settings**: Pydantic v2 & `pydantic-settings`
- **Authentication**: JWT (OAuth2 Password Bearer flow ready)
- **Monetary Storage**: Strict integer paise arithmetic (`utils/money.py` using `Decimal` & `ROUND_HALF_UP`)

---

## Folder Structure

```text
backend/
  app/
    main.py          # FastAPI application initialization & middleware
    core/            # config.py, db.py, security.py
    models/          # SQLAlchemy 2.x models (user, product, order, invoice, production, audit)
    schemas/         # Pydantic v2 validation schemas
    routers/         # Thin FastAPI routers (health, api v1)
    services/        # Business logic services (keeps routers thin)
    utils/           # units.py, money.py (integer paise helpers)
  alembic/           # Migration environment & versions
  alembic.ini        # Alembic configuration
  tests/             # pytest suite with rolled-back transaction fixtures
  scripts/           # Seed scripts (seed.py)
  requirements.txt   # Python dependencies
  Dockerfile         # Container image definition
docker-compose.yml   # Multi-container orchestration (PostgreSQL + FastAPI backend)
.env.example         # Environment template (no committed secrets)
.gitignore
README.md
```

---

## Quickstart with Docker Compose

### 1. Copy Environment Configuration
```bash
cp .env.example .env
```

### 2. Start Services (PostgreSQL + Backend)
```bash
docker compose up --build -d
```
The database container includes an automated healthcheck. The backend container waits until PostgreSQL is healthy before launching.

### 3. Run Database Migrations
```bash
docker compose exec backend alembic upgrade head
```

### 4. Seed Initial Data (Admin User)
```bash
docker compose exec backend python scripts/seed.py
```

### 5. Run Test Suite
```bash
docker compose exec backend pytest -v
```

### 6. Verify Endpoints
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Local Development (Without Docker)

### 1. Create and Activate Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 3. Configure Local `.env`
Ensure your PostgreSQL instance is running and your `.env` contains your connection credentials:
```bash
cp .env.example .env
```

### 4. Run Migrations
From within the `backend/` directory:
```bash
cd backend
alembic upgrade head
```

### 5. Run Tests
```bash
cd backend
pytest -v
```

### 6. Start Development Server
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Monetary System Rules

- Money is **ALWAYS** stored as integer paise (1 Rupee = 100 Paise).
- `rupees_to_paise(Decimal|str) -> int` strictly rejects floating-point types to eliminate IEEE-754 precision errors.
- `paise_to_rupees_str(int) -> str` formats paise into 2-decimal-place strings for UI presentation.
- Rounding helper utilizes `Decimal.quantize(..., rounding=ROUND_HALF_UP)`.
