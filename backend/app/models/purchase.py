from datetime import datetime, timezone
import enum
from typing import Optional
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class PurchaseStatus(str, enum.Enum):
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class Purchase(Base, TimestampMixin):
    """
    Supplier raw material and packaging purchase order/receipt.
    When created, immediately posts immutable rows to stock_movements in the same transaction.
    """
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purchase_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_invoice_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    purchase_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[PurchaseStatus] = mapped_column(
        Enum(PurchaseStatus, name="purchase_status_enum", native_enum=False),
        nullable=False,
        default=PurchaseStatus.POSTED,
    )
    # Total invoice amount in integer paise
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier")
    creator: Mapped[Optional["User"]] = relationship("User")
    lines: Mapped[list["PurchaseLine"]] = relationship(
        "PurchaseLine", back_populates="purchase", cascade="all, delete-orphan"
    )


class PurchaseLine(Base, TimestampMixin):
    """
    Line item for goods received under a purchase receipt.
    Stores entered commercial quantity and entered unit rate alongside canonical base units.
    """
    __tablename__ = "purchase_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purchase_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Canonical quantity in BASE UNITS (grams, ml, pieces)
    quantity_base: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Unit entered by operator (e.g. "kg", "L", "piece")
    unit_entered: Mapped[str] = mapped_column(String(16), nullable=False)

    # Rate entered per entered unit in integer paise (e.g. Rs 45/kg -> 4500 paise per kg)
    rate_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Line total in integer paise
    line_total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    purchase: Mapped["Purchase"] = relationship("Purchase", back_populates="lines")
    item: Mapped["Item"] = relationship("Item")
