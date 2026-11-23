from fastapi import APIRouter
from app.routers import health

api_router = APIRouter()
api_router.include_router(health.router)

# Future domain routers will be mounted here:
# api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
# api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
# api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
# api_router.include_router(production.router, prefix="/production", tags=["Production"])
# api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
