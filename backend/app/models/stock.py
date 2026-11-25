from datetime import datetime, timezone
from decimal import Decimal
import enum
from typing import Optional
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MovementType(str, enum.Enum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    PRODUCTION_ISSUE = "PRODUCTION_ISSUE"
    PRODUCTION_OUTPUT = "PRODUCTION_OUTPUT"
    DISPATCH = "DISPATCH"
    SALES_RETURN = "SALES_RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    WASTAGE = "WASTAGE"
    REVERSAL = "REVERSAL"


class StockMovement(Base):
    """
    Append-only, immutable inventory ledger.
    Every physical movement in or out of the factory is recorded here.
    Balance of any item at any point in time = SUM(quantity_base).
    UPDATE and DELETE are strictly forbidden and guarded at DB level via triggers.
    """
    __tablename__ = "stock_movements"

    __table_args__ = (
        Index("ix_stock_movements_item_date", "item_id", "movement_date"),
        Index("ix_stock_movements_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    movement_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, name="movement_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    # SIGNED quantity in base units: positive for receipts, negative for issues/consumption
    quantity_base: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Unit cost in paise per base unit with up to 6 decimal places (e.g. 4.200000 paise/g)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # SIGNED monetary value in whole paise (rounded ROUND_HALF_UP)
    value_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Audit traceability linking to source document (PURCHASE, PRODUCTION_RUN, INVOICE, ADJUSTMENT, etc.)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Link to original movement if this row reverses an earlier entry
    reverses_movement_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True
    )

    # Future batch tracking stretch columns
    batch_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    item: Mapped["Item"] = relationship("Item")
    creator: Mapped[Optional["User"]] = relationship("User")
    reverses_movement: Mapped[Optional["StockMovement"]] = relationship(
        "StockMovement", remote_side=[id]
    )
