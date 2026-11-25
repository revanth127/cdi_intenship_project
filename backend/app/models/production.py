import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProductionRunStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class ProductionRun(Base, TimestampMixin):
    """
    Production run tracking BOM consumption and yield output.
    Status lifecycle: DRAFT -> POSTED (or CANCELLED).
    """
    __tablename__ = "production_runs"

    __table_args__ = (
        CheckConstraint("batches > 0", name="ck_production_runs_batches_positive"),
        CheckConstraint("expected_output_packets >= 0", name="ck_production_runs_expected_output_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("boms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bom_version: Mapped[int] = mapped_column(Integer, nullable=False)
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    batches: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("1.0000"))
    batch_size_packets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[ProductionRunStatus] = mapped_column(
        Enum(ProductionRunStatus, name="production_run_status_enum", native_enum=False),
        nullable=False,
        default=ProductionRunStatus.DRAFT,
    )
    expected_output_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_good_packets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wastage_packets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    yield_variance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    is_yield_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_material_cost_paise: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    unit_material_cost_paise: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    posted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    bom: Mapped["BOM"] = relationship("BOM")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    poster: Mapped[Optional["User"]] = relationship("User", foreign_keys=[posted_by])
    lines: Mapped[list["ProductionRunLine"]] = relationship(
        "ProductionRunLine", back_populates="run", cascade="all, delete-orphan", order_by="ProductionRunLine.id"
    )


class ProductionRunLine(Base, TimestampMixin):
    """
    Individual raw material and packaging consumption line for a production run.
    Tracks planned, actual, damaged, variance, unit cost, and cost value.
    """
    __tablename__ = "production_run_lines"

    __table_args__ = (
        CheckConstraint("planned_qty_base >= 0", name="ck_prod_run_lines_planned_qty_non_negative"),
        CheckConstraint("damaged_qty_base >= 0", name="ck_prod_run_lines_damaged_qty_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("production_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    planned_qty_base: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_qty_base: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    damaged_qty_base: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    variance_qty_base: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    variance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)  # paise per base unit
    value_paise: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    unit_for_display: Mapped[str] = mapped_column(String(16), nullable=False)

    # Relationships
    run: Mapped["ProductionRun"] = relationship("ProductionRun", back_populates="lines")
    item: Mapped["Item"] = relationship("Item")
