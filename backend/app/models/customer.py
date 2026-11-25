import enum
from typing import Optional
from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class CustomerType(str, enum.Enum):
    RETAILER = "RETAILER"
    DISTRIBUTOR = "DISTRIBUTOR"


class Customer(Base, TimestampMixin):
    """
    Customer master table supporting Retailers and Distributors.
    Maintains GSTIN, 2-digit State Code for GST tax calculation (CGST+SGST vs IGST),
    and salesman assignment.
    """
    __tablename__ = "customers"

    __table_args__ = (
        CheckConstraint("length(state_code) = 2", name="ck_customers_state_code_len"),
        Index("uq_customers_gstin", "gstin", unique=True, postgresql_where=text("gstin IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_type: Mapped[CustomerType] = mapped_column(
        Enum(CustomerType, name="customer_type_enum", native_enum=False),
        nullable=False,
    )
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)  # e.g. "33" for Tamil Nadu
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_salesman_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    assigned_salesman: Mapped[Optional["User"]] = relationship("User")
