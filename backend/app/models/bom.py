from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class BOM(Base, TimestampMixin):
    """
    Bill of Materials header for recipe formulations.
    Belongs to a ProductFamily (e.g. 'Murukku'), NOT a specific pack variant.
    Defines versioning and expected raw output in grams per batch.
    """
    __tablename__ = "boms"

    __table_args__ = (
        CheckConstraint("expected_output_g > 0", name="ck_boms_expected_output_g_positive"),
        CheckConstraint("version > 0", name="ck_boms_version_positive"),
        UniqueConstraint("family_id", "version", name="uq_boms_family_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    family_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("product_families.id", ondelete="CASCADE"), nullable=True, index=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Expected output in grams (e.g. 40,000 g for benchmark batch)
    expected_output_g: Mapped[int] = mapped_column(Integer, nullable=False, default=40000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __init__(self, **kwargs):
        if "product_id" in kwargs and "family_id" not in kwargs:
            kwargs["family_id"] = kwargs.get("product_id")
        if "batch_output_packets" in kwargs and "expected_output_g" not in kwargs:
            kwargs["expected_output_g"] = kwargs.pop("batch_output_packets") * 200
        super().__init__(**kwargs)

    # Relationships
    family: Mapped["ProductFamily"] = relationship("ProductFamily", back_populates="boms")
    items: Mapped[list["BOMItem"]] = relationship(
        "BOMItem", back_populates="bom", cascade="all, delete-orphan", order_by="BOMItem.id"
    )

    @property
    def batch_output_packets(self) -> int:
        """Backward compatibility helper assuming standard 200 g pack if queried."""
        return self.expected_output_g // 200 if self.expected_output_g else 200


class BOMItem(Base, TimestampMixin):
    """
    Recipe line item linking required raw materials / ingredients.
    Restricted strictly to RAW_MATERIAL item types.
    Quantities are strictly in BASE UNITS as integers (grams, ml, etc.).
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
    # Stored in BASE UNITS (e.g. 40,000 g flour, 10,000 ml oil, 1,200 g spice mix)
    quantity_per_batch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_for_display: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "kg", "L"
    # Optional override of company variance tolerance percentage (e.g. 2.50%)
    variance_tolerance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    @property
    def quantity_per_batch_base(self) -> int:
        return self.quantity_per_batch

    @quantity_per_batch_base.setter
    def quantity_per_batch_base(self, value: int):
        self.quantity_per_batch = value

    @property
    def tolerance_override(self) -> Optional[Decimal]:
        return self.variance_tolerance_pct

    @tolerance_override.setter
    def tolerance_override(self, value: Optional[Decimal]):
        self.variance_tolerance_pct = value

    # Relationships
    bom: Mapped["BOM"] = relationship("BOM", back_populates="items")
    item: Mapped["Item"] = relationship("Item")
