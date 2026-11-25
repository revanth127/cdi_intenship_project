from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class BOM(Base, TimestampMixin):
    """
    Bill of Materials header for finished product recipes.
    Defines versioning and batch output yield in packets.
    """
    __tablename__ = "boms"

    __table_args__ = (
        CheckConstraint("batch_output_packets > 0", name="ck_boms_batch_output_packets_positive"),
        CheckConstraint("version > 0", name="ck_boms_version_positive"),
        UniqueConstraint("product_id", "version", name="uq_boms_product_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    batch_output_packets: Mapped[int] = mapped_column(Integer, nullable=False)  # e.g. 200 packets per batch
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="boms")
    items: Mapped[list["BOMItem"]] = relationship(
        "BOMItem", back_populates="bom", cascade="all, delete-orphan"
    )


class BOMItem(Base, TimestampMixin):
    """
    Recipe line item linking required ingredients and packaging.
    Quantities are strictly in BASE UNITS as integers (grams, ml, pieces).
    """
    __tablename__ = "bom_items"

    __table_args__ = (
        CheckConstraint("quantity_per_batch > 0", name="ck_bom_items_quantity_per_batch_positive"),
        UniqueConstraint("bom_id", "item_id", name="uq_bom_items_bom_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("boms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Stored in BASE UNITS (e.g. 40,000 g flour, 10,000 ml oil, 200 pouches)
    quantity_per_batch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_for_display: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "kg", "L", "piece"
    # Optional override of company variance tolerance percentage (e.g. 2.50%)
    variance_tolerance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    # Relationships
    bom: Mapped["BOM"] = relationship("BOM", back_populates="items")
    item: Mapped["Item"] = relationship("Item")
