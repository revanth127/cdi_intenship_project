import enum
from decimal import Decimal
from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProductType(str, enum.Enum):
    RAW_MATERIAL = "RAW_MATERIAL"
    FINISHED_GOOD = "FINISHED_GOOD"
    PACKAGING = "PACKAGING"


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, name="product_type_enum", native_enum=False),
        nullable=False,
    )
    unit_of_measure: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    bom_components: Mapped[list["BomItem"]] = relationship(
        "BomItem",
        foreign_keys="BomItem.finished_good_id",
        back_populates="finished_good",
    )


class BomItem(Base, TimestampMixin):
    """
    Bill of Materials (BOM) linkage: defines raw material quantities
    required to produce one unit of a finished good.
    """
    __tablename__ = "bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    finished_good_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    raw_material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    quantity_required: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # Relationships
    finished_good: Mapped["Product"] = relationship(
        "Product", foreign_keys=[finished_good_id], back_populates="bom_components"
    )
    raw_material: Mapped["Product"] = relationship("Product", foreign_keys=[raw_material_id])
