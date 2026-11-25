from fastapi import APIRouter
from app.routers import (
    auth,
    boms,
    company,
    customers,
    health,
    items,
    me,
    orders,
    pricing,
    production,
    products,
    purchases,
    stock,
    suppliers,
    users,
)

api_router = APIRouter()

# Health
api_router.include_router(health.router)

# Authentication & User Management
api_router.include_router(auth.router)
api_router.include_router(users.router)

# Master Data CRUD Routers (protected by RBAC)
api_router.include_router(items.router)
api_router.include_router(products.router)
api_router.include_router(pricing.router)
api_router.include_router(customers.router)
api_router.include_router(suppliers.router)
api_router.include_router(boms.router)
api_router.include_router(company.router)

# Stock Ledger & Procurement Routers
api_router.include_router(purchases.router)
api_router.include_router(stock.router)

# Production Runs Router
api_router.include_router(production.router)

# Sales Orders & Salesman Mobile Routers
api_router.include_router(orders.router)
api_router.include_router(me.router)
