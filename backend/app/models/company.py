from decimal import Decimal
from sqlalchemy import CheckConstraint, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class CompanySettings(Base, TimestampMixin):
    """
    Single-row company settings holding company profile, GSTIN,
    and fiscal policies.
    """
    __tablename__ = "company_settings"

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_company_settings_single_row"),
        CheckConstraint("financial_year_start_month BETWEEN 1 AND 12", name="ck_company_settings_fy_start_month"),
        CheckConstraint("variance_tolerance_pct >= 0", name="ck_company_settings_variance_tolerance_non_negative"),
        CheckConstraint("length(state_code) = 2", name="ck_company_settings_state_code_len"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, default="33")  # Tamil Nadu = 33
    address: Mapped[str] = mapped_column(Text, nullable=False)
    financial_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False, default=4)  # April
    variance_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("3.00"))
    invoice_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="INV-")
