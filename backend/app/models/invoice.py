import enum
from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class InvoiceStatus(str, enum.Enum):
    ISSUED = "ISSUED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("sales_orders.id"), nullable=False, unique=True, index=True)
    customer_gstin: Mapped[str] = mapped_column(String(15), nullable=True)

    # All monetary amounts strictly stored in integer paise
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", native_enum=False),
        nullable=False,
        default=InvoiceStatus.ISSUED,
    )

    # Relationships
    order: Mapped["SalesOrder"] = relationship("SalesOrder")
