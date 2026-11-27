from fastapi import APIRouter
from app.routers import (
    audit,
    auth,
    boms,
    company,
    costing,
    customers,
    dashboard,
    health,
    invoices,
    items,
    me,
    orders,
    overheads,
    payments,
    pricing,
    production,
    product_families,
    products,
    purchases,
    receivables,
    reports,
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
api_router.include_router(product_families.router)
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

# GST Invoices, Dispatches & Credit Notes
api_router.include_router(invoices.router)

# Payments, Allocations & Receivables
api_router.include_router(payments.router)
api_router.include_router(receivables.router)

# Overheads, Costing & Margins
api_router.include_router(overheads.router)
api_router.include_router(costing.router)

# Executive Dashboard
api_router.include_router(dashboard.router)

# Audit Trail & History
api_router.include_router(reports.router)
api_router.include_router(audit.router)
