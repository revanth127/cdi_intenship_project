from typing import Optional
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin


class Product(Base, TimestampMixin):
    """
    Finished good commercial pack details.
    Links 1:1 to an Item where item.item_type == FINISHED_GOOD.
    Maintains packaging ratio (packets per carton) and links to BOMs & PriceLists.
    """
    __tablename__ = "products"

    __table_args__ = (
        CheckConstraint("packets_per_carton > 0", name="ck_products_packets_per_carton_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    pack_size_desc: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "200 g"
    packets_per_carton: Mapped[int] = mapped_column(Integer, nullable=False, default=20)

    # Relationships
    item: Mapped["Item"] = relationship("Item", back_populates="product")
    boms: Mapped[list["BOM"]] = relationship("BOM", back_populates="product", cascade="all, delete-orphan")
    price_list_items: Mapped[list["PriceListItem"]] = relationship("PriceListItem", back_populates="product")
