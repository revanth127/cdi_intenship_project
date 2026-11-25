from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, boms, me, orders, production, users
from app.routers.api import api_router
from app.routers.health import router as health_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

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
app.include_router(boms.router)        # supports /boms directly
app.include_router(production.router)  # supports /production directly
app.include_router(orders.router)      # supports /orders directly
app.include_router(me.router)          # supports /me directly

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
