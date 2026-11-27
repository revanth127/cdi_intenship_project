import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    audit,
    auth,
    boms,
    costing,
    dashboard,
    invoices,
    me,
    orders,
    overheads,
    payments,
    product_families,
    production,
    receivables,
    users,
)
from app.routers.api import api_router
from app.routers.health import router as health_router
from app.services.audit import current_ip_address, current_request_id

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    client_ip = request.headers.get("X-Forwarded-For")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    token_req = current_request_id.set(req_id)
    token_ip = current_ip_address.set(client_ip)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        current_request_id.reset(token_req)
        current_ip_address.reset(token_ip)

# Enable CORS for frontend running on localhost / configured origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Root-level endpoints
app.include_router(health_router)
app.include_router(auth.router)        # supports /auth/login and /auth/me directly
app.include_router(users.router)       # supports /users directly
app.include_router(product_families.router) # supports /product-families directly
app.include_router(boms.router)        # supports /boms directly
app.include_router(production.router)  # supports /production directly
app.include_router(orders.router)      # supports /orders directly
app.include_router(me.router)          # supports /me directly
app.include_router(invoices.router)    # supports /invoices directly
app.include_router(payments.router)    # supports /payments directly
app.include_router(receivables.router) # supports /receivables and /customers/{id}/statement directly
app.include_router(overheads.router)   # supports /overheads directly
app.include_router(costing.router)     # supports /costing directly
app.include_router(dashboard.router)   # supports /dashboard directly
app.include_router(audit.router)       # supports /audit-log directly

# Versioned API routes (/api/v1/...)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
    }
