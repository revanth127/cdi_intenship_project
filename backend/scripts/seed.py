#!/usr/bin/env python3
"""
Seed script to populate initial baseline records (Admin user, standard units).
Can be run via: python scripts/seed.py
"""
import logging
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")


def seed_admin_user() -> None:
    db = SessionLocal()
    try:
        admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@order-to-audit.local")
        admin_password = os.getenv("SEED_ADMIN_PASSWORD", "AdminPass123!")
        admin_name = "System Administrator"

        stmt = select(User).where(User.email == admin_email)
        existing_admin = db.execute(stmt).scalar_one_or_none()

        if existing_admin:
            logger.info("Admin user (%s) already exists. Skipping creation.", admin_email)
            return

        admin_user = User(
            email=admin_email,
            hashed_password=get_password_hash(admin_password),
            full_name=admin_name,
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
        logger.info("Successfully created default admin user: %s", admin_email)
    except Exception as exc:
        db.rollback()
        logger.error("Error during seeding: %s", exc)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Starting database seeding...")
    seed_admin_user()
    logger.info("Database seeding completed.")
