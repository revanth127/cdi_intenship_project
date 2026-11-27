from decimal import Decimal
from typing import Optional
import math
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class ProductFamily(Base, TimestampMixin):
    """
    Product family header (e.g. 'Murukku').
    Shares a common Bill of Materials across multiple pack size variants.
    """
    __tablename__ = "product_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    hsn_code: Mapped[str] = mapped_column(String(16), nullable=False)
    gst_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    variants: Mapped[list["Product"]] = relationship(
        "Product", back_populates="family", cascade="all, delete-orphan", order_by="Product.id"
    )
    boms: Mapped[list["BOM"]] = relationship(
        "BOM", back_populates="family", cascade="all, delete-orphan", order_by="BOM.version"
    )


class Product(Base, TimestampMixin):
    """
    Pack variant of a ProductFamily (e.g. 'Murukku 200 g', 'Murukku 500 g').
    Links 1:1 to an Item where item.item_type == FINISHED_GOOD.
    Maintains packaging ratio (packets per carton) and links to PackagingSpecs & PriceLists.
    """
    __tablename__ = "products"

    __table_args__ = (
        CheckConstraint("packets_per_carton > 0", name="ck_products_packets_per_carton_positive"),
        CheckConstraint("net_weight_g > 0", name="ck_products_net_weight_g_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    family_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("product_families.id", ondelete="CASCADE"), nullable=True, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    pack_name: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "Murukku 200 g"
    pack_size_desc: Mapped[str] = mapped_column(String(64), nullable=False, default="200 g")  # e.g. "200 g"
    net_weight_g: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    packets_per_carton: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __init__(self, **kwargs):
        if "pack_size_desc" in kwargs and "pack_name" not in kwargs:
            kwargs["pack_name"] = f"Murukku {kwargs['pack_size_desc']}"
        elif "pack_name" in kwargs and "pack_size_desc" not in kwargs:
            # e.g. "Murukku 200 g" -> "200 g"
            parts = kwargs["pack_name"].split(" ", 1)
            kwargs["pack_size_desc"] = parts[1] if len(parts) > 1 else kwargs["pack_name"]
        if "pack_name" not in kwargs:
            kwargs["pack_name"] = "Pack"
        if "pack_size_desc" not in kwargs:
            kwargs["pack_size_desc"] = "200 g"
        super().__init__(**kwargs)

    # Relationships
    family: Mapped["ProductFamily"] = relationship("ProductFamily", back_populates="variants")
    item: Mapped["Item"] = relationship("Item", back_populates="product")
    packaging_specs: Mapped[list["PackagingSpec"]] = relationship(
        "PackagingSpec", back_populates="product", cascade="all, delete-orphan", order_by="PackagingSpec.id"
    )
    price_list_items: Mapped[list["PriceListItem"]] = relationship(
        "PriceListItem", back_populates="product"
    )


class PackagingSpec(Base, TimestampMixin):
    """
    Packaging specifications specific to a product pack variant.
    Belongs to the VARIANT (Product), not the BOM.
    Rule: Planned packaging = CEIL(expected_packets * qty_base / per_packets),
    because packaging cannot be consumed in partial units (e.g. cartons).
    """
    __tablename__ = "packaging_specs"

    __table_args__ = (
        CheckConstraint("qty_base > 0", name="ck_packaging_specs_qty_base_positive"),
        CheckConstraint("per_packets > 0", name="ck_packaging_specs_per_packets_positive"),
        UniqueConstraint("product_id", "item_id", name="uq_packaging_specs_product_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty_base: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    per_packets: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_for_display: Mapped[str] = mapped_column(String(16), nullable=False, default="piece")

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="packaging_specs")
    item: Mapped["Item"] = relationship("Item")

    def calculate_planned_qty(self, expected_packets: int) -> int:
        """Calculates planned packaging quantity using CEIL rule."""
        if expected_packets <= 0:
            return 0
        return math.ceil((expected_packets * self.qty_base) / self.per_packets)
