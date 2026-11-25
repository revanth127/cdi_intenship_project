from datetime import datetime, timezone
from decimal import Decimal
import enum
from typing import Optional
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class OrderStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INVOICED = "INVOICED"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"


class PriceSource(str, enum.Enum):
    PRICE_LIST = "PRICE_LIST"
    CUSTOMER_OVERRIDE = "CUSTOMER_OVERRIDE"
    ADMIN_EDIT = "ADMIN_EDIT"


class Order(Base, TimestampMixin):
    """
    Sales order header tracking customer requests placed by salesmen and approved by admins.
    Includes client_uuid idempotency key for reliable offline sync from mobile devices.
    """
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint("total_amount_paise >= 0", name="ck_orders_total_paise_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    salesman_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", native_enum=False),
        nullable=False,
        default=OrderStatus.SUBMITTED,
        index=True,
    )
    total_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer")
    salesman: Mapped["User"] = relationship("User", foreign_keys=[salesman_id])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])
    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine", back_populates="order", cascade="all, delete-orphan", order_by="OrderLine.id"
    )
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        "OrderStatusHistory", back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.id"
    )


class OrderLine(Base, TimestampMixin):
    """
    Individual order item tracking requested packet quantities and price snapshots.
    """
    __tablename__ = "order_lines"

    __table_args__ = (
        CheckConstraint("quantity_packets > 0", name="ck_order_lines_quantity_positive"),
        CheckConstraint("unit_price_paise >= 0", name="ck_order_lines_unit_price_non_negative"),
        CheckConstraint("line_total_paise >= 0", name="ck_order_lines_line_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_source: Mapped[PriceSource] = mapped_column(
        Enum(PriceSource, name="price_source_enum", native_enum=False),
        nullable=False,
        default=PriceSource.PRICE_LIST,
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="lines")
    product: Mapped["Product"] = relationship("Product")


class OrderStatusHistory(Base):
    """
    Immutable lifecycle audit record of order status changes.
    """
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[OrderStatus]] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", native_enum=False),
        nullable=True,
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", native_enum=False),
        nullable=False,
    )
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="status_history")
    user: Mapped[Optional["User"]] = relationship("User")


class NumberingSequence(Base):
    """
    Sequence counter for gapless, race-free document numbering per financial year.
    Acquires row-level write locks (SELECT ... FOR UPDATE) on increment.
    Reused across Orders, Invoices, etc.
    """
    __tablename__ = "numbering_sequences"

    sequence_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    financial_year: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "2026-27"
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# Aliases for backwards-compatibility
SalesOrder = Order
OrderItem = OrderLine
