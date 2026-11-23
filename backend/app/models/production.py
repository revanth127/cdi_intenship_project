import enum
from decimal import Decimal
from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProductionRunStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ProductionRun(Base, TimestampMixin):
    __tablename__ = "production_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    supervisor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    actual_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True, default=None)
    status: Mapped[ProductionRunStatus] = mapped_column(
        Enum(ProductionRunStatus, name="production_run_status_enum", native_enum=False),
        nullable=False,
        default=ProductionRunStatus.PLANNED,
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    supervisor: Mapped["User"] = relationship("User")
