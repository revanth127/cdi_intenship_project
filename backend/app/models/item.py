import enum
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ItemType(str, enum.Enum):
    RAW_MATERIAL = "RAW_MATERIAL"
    PACKAGING = "PACKAGING"
    FINISHED_GOOD = "FINISHED_GOOD"


class Item(Base, TimestampMixin):
    """
    Unified inventory item master.
    All items (raw materials, packaging, finished goods) exist here so the
    stock ledger can reference a single item_id.
    Quantities are strictly in BASE UNITS (mass in grams, volume in ml, countable in pieces).
    """
    __tablename__ = "items"

    __table_args__ = (
        CheckConstraint("gst_rate_bp >= 0 AND gst_rate_bp <= 10000", name="ck_items_gst_rate_bp_range"),
        CheckConstraint("reorder_level IS NULL OR reorder_level >= 0", name="ck_items_reorder_level_non_negative"),
        CheckConstraint("opening_balance_qty IS NULL OR opening_balance_qty >= 0", name="ck_items_opening_balance_qty_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType, name="item_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    base_unit: Mapped[str] = mapped_column(String(16), nullable=False)       # e.g. "g", "ml", "piece", "packet"
    display_unit: Mapped[str] = mapped_column(String(16), nullable=False)    # e.g. "kg", "L", "piece", "packet"
    hsn_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    gst_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # basis points (e.g. 500 = 5%)
    reorder_level: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # in base units
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Initial opening stock fields (held here until ledger posting in Phase 3)
    opening_balance_qty: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # in base units
    opening_rate_paise: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)  # paise per base unit

    # Relationships
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="item", uselist=False)
