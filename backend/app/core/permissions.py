from app.models.user import UserRole

# Master Data & Transaction Permission Matrix:
# Maps resources to roles authorized for READ and WRITE operations
RESOURCE_PERMISSIONS = {
    "items": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION],
        "write": [UserRole.ADMIN],
    },
    "boms": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION],
        "write": [UserRole.ADMIN],
    },
    "products": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION, UserRole.SALESMAN],
        "write": [UserRole.ADMIN],
    },
    "pricing": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN],
        "write": [UserRole.ADMIN],
    },
    "customers": {
        # SALESMAN can read only customers assigned to them; ADMIN, OWNER, ACCOUNTANT read all
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.SALESMAN],
        "write": [UserRole.ADMIN],
    },
    "suppliers": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT],
        "write": [UserRole.ADMIN],
    },
    "company_settings": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT],
        "write": [UserRole.ADMIN],
    },
    "users": {
        "read": [UserRole.ADMIN],
        "write": [UserRole.ADMIN],
    },
    "audit_logs": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT],
        "write": [UserRole.ADMIN],
    },
    "purchases": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION],
        "write": [UserRole.ADMIN, UserRole.PRODUCTION], # Cancellation is ADMIN only
    },
    "production_runs": {
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION],
        "write": [UserRole.ADMIN, UserRole.PRODUCTION], # Cancellation is ADMIN only
    },
    "stock": {
        # SALESMAN can only read finished-goods availability; others read all
        "read": [UserRole.ADMIN, UserRole.OWNER, UserRole.ACCOUNTANT, UserRole.PRODUCTION, UserRole.SALESMAN],
        "adjust": [UserRole.ADMIN],
    },
}
