from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class PriceList(Base, TimestampMixin):
    """
    Selling price list header (e.g. Standard, Distributor, Retail).
    """
    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    items: Mapped[list["PriceListItem"]] = relationship(
        "PriceListItem", back_populates="price_list", cascade="all, delete-orphan"
    )


class PriceListItem(Base, TimestampMixin):
    """
    Price per packet in integer paise for a finished product on a specific price list.
    """
    __tablename__ = "price_list_items"

    __table_args__ = (
        CheckConstraint("price_paise >= 0", name="ck_price_list_items_price_non_negative"),
        UniqueConstraint("price_list_id", "product_id", "effective_from", name="uq_price_list_items_effective"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    price_list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Selling price per packet in paise
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    price_list: Mapped["PriceList"] = relationship("PriceList", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="price_list_items")


class CustomerPriceOverride(Base, TimestampMixin):
    """
    Optional price overrides specific to individual high-volume customers.
    """
    __tablename__ = "customer_price_overrides"

    __table_args__ = (
        CheckConstraint("price_paise >= 0", name="ck_customer_price_overrides_price_non_negative"),
        UniqueConstraint("customer_id", "product_id", "effective_from", name="uq_customer_price_overrides_effective"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Overridden price in paise
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer")
    product: Mapped["Product"] = relationship("Product")
