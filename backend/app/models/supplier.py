from typing import Optional
from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class Supplier(Base, TimestampMixin):
    """
    Vendor / Supplier master for procurement of raw materials and packaging.
    """
    __tablename__ = "suppliers"

    __table_args__ = (
        CheckConstraint("length(state_code) = 2", name="ck_suppliers_state_code_len"),
        Index("uq_suppliers_gstin", "gstin", unique=True, postgresql_where=text("gstin IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)  # 2-digit state code
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
