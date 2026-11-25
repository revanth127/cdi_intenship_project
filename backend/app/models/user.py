import enum
from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"
    SALESMAN = "SALESMAN"
    PRODUCTION = "PRODUCTION"
    ACCOUNTANT = "ACCOUNTANT"

    # Compatibility alias
    PRODUCTION_SUPERVISOR = "PRODUCTION"


class User(Base, TimestampMixin):
    """
    User entity with role-based access for salesman, production,
    accountant, administrator, and business owner.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        default=UserRole.SALESMAN,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
