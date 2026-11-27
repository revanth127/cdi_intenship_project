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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class OverheadCategory(str, enum.Enum):
    LABOUR = "LABOUR"
    GAS = "GAS"
    POWER = "POWER"
    OTHER = "OTHER"


class OverheadStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    VOIDED = "VOIDED"


class OverheadEntry(Base, TimestampMixin):
    """
    Overhead expenditure record (Labour, Gas, Power, Other).
    Allocated directly to a production run OR allocated across a calendar month's
    POSTED runs in proportion to good packets produced.
    Never written into the stock ledger to preserve ledger immutability.
    Entries are immutable; corrections are made by voiding with a mandatory reason.
    """
    __tablename__ = "overhead_entries"

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_overhead_entries_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    category: Mapped[OverheadCategory] = mapped_column(
        Enum(OverheadCategory, name="overhead_category_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    production_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("production_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    month: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, index=True)  # YYYY-MM
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[OverheadStatus] = mapped_column(
        Enum(OverheadStatus, name="overhead_status_enum", native_enum=False),
        nullable=False,
        default=OverheadStatus.ACTIVE,
        index=True,
    )
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    production_run: Mapped[Optional["ProductionRun"]] = relationship("ProductionRun")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])


class RunCostSheet(Base):
    """
    Derived cost snapshot for a production run.
    Regenerated on demand when run completes or when overhead entries change/void.
    Stores breakdown of material, labour, gas/power, and other costs,
    along with cost per good packet, standard BOM planned cost, and cost of loss.
    """
    __tablename__ = "run_cost_sheets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("production_runs.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    material_cost_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    labour_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    gas_power_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    other_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cost_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    good_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_per_packet: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    planned_cost_per_packet: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    cost_of_loss_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    run: Mapped["ProductionRun"] = relationship("ProductionRun")
