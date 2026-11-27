import os
import sys
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.db import Base, get_db
from app.main import app

# Use TEST_DATABASE_URL if defined; fallback to SQLite in-memory for portable local unit testing
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def engine():
    """
    Session-scoped database engine for testing.
    Creates all tables at start and drops them at teardown.
    """
    if TEST_DB_URL.startswith("sqlite"):
        test_engine = create_engine(
            TEST_DB_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)

    Base.metadata.create_all(bind=test_engine)

    # Attach immutable append-only triggers for stock_movements and audit_logs in SQLite tests
    if test_engine.dialect.name == "sqlite":
        from sqlalchemy import text
        with test_engine.begin() as conn:
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_update
            BEFORE UPDATE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'Audit logs are strictly immutable. UPDATE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_delete
            BEFORE DELETE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'Audit logs are strictly immutable. DELETE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_stock_movements_update
            BEFORE UPDATE ON stock_movements
            BEGIN
                SELECT RAISE(ABORT, 'Stock movements are strictly immutable. UPDATE operations are forbidden.');
            END;
            """))
            conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_stock_movements_delete
            BEFORE DELETE ON stock_movements
            BEGIN
                SELECT RAISE(ABORT, 'Stock movements are strictly immutable. DELETE operations are forbidden.');
            END;
            """))

    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """
    Function-scoped database session wrapped inside an outer transaction.
    At the end of each test, the transaction is rolled back, guaranteeing
    that tests remain completely isolated without residual test data.
    """
    connection = engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
    )
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with get_db dependency overridden to use the rolled-back test session.
    """
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
