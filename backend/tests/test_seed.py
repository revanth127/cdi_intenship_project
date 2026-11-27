from decimal import Decimal
import os
import sys
import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import Base
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.customer import Customer, CustomerType
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product
from app.models.user import User, UserRole
from scripts.seed import run_seed


class TestSeedScript(unittest.TestCase):
    """
    Test that scripts/seed.py:
    1. Successfully populates all required master rows with exact business parameters.
    2. Is completely idempotent when run multiple times consecutively.
    """

    def setUp(self):
        # Create an isolated in-memory SQLite database for testing seed execution
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_seed_creates_expected_master_records_and_is_idempotent(self):
        # First execution of seed
        run_seed(self.db)

        # 1. Verify CompanySettings
        company = self.db.get(CompanySettings, 1)
        self.assertIsNotNone(company)
        self.assertEqual(company.state_code, "33")  # Tamil Nadu
        self.assertEqual(company.variance_tolerance_pct, Decimal("3.00"))
        self.assertEqual(company.financial_year_start_month, 4)

        # 2. Verify Users (6 users: 2 salesmen, admin, supervisor, accountant, owner)
        users = self.db.scalars(select(User)).all()
        self.assertEqual(len(users), 6)
        roles = {u.role for u in users}
        self.assertIn(UserRole.ADMIN, roles)
        self.assertIn(UserRole.OWNER, roles)
        self.assertIn(UserRole.SALESMAN, roles)
        self.assertIn(UserRole.PRODUCTION, roles)
        self.assertIn(UserRole.ACCOUNTANT, roles)

        salesmen = [u for u in users if u.role == UserRole.SALESMAN]
        self.assertEqual(len(salesmen), 2)

        # 3. Verify Items (6 items)
        items = self.db.scalars(select(Item)).all()
        self.assertEqual(len(items), 6)
        item_dict = {i.name: i for i in items}

        # Flour: 100 kg opening (= 100,000 g); Rs 42/kg = 4.2 paise/g
        flour = item_dict["Flour"]
        self.assertEqual(flour.item_type, ItemType.RAW_MATERIAL)
        self.assertEqual(flour.base_unit, "g")
        self.assertEqual(flour.display_unit, "kg")
        self.assertEqual(flour.opening_balance_qty, 100000)
        self.assertEqual(flour.opening_rate_paise, Decimal("4.200000"))

        # Cooking oil: 30 L (= 30,000 ml); Rs 140/L = 14.0 paise/ml
        oil = item_dict["Cooking oil"]
        self.assertEqual(oil.item_type, ItemType.RAW_MATERIAL)
        self.assertEqual(oil.base_unit, "ml")
        self.assertEqual(oil.display_unit, "L")
        self.assertEqual(oil.opening_balance_qty, 30000)
        self.assertEqual(oil.opening_rate_paise, Decimal("14.000000"))

        # Salt and spice mix: 5 kg (= 5,000 g); Rs 200/kg = 20.0 paise/g
        spice = item_dict["Salt and spice mix"]
        self.assertEqual(spice.item_type, ItemType.RAW_MATERIAL)
        self.assertEqual(spice.base_unit, "g")
        self.assertEqual(spice.display_unit, "kg")
        self.assertEqual(spice.opening_balance_qty, 5000)
        self.assertEqual(spice.opening_rate_paise, Decimal("20.000000"))

        # 200 g pouch: 500 pieces; Rs 2.50 each = 250 paise/piece
        pouch = item_dict["200 g pouch"]
        self.assertEqual(pouch.item_type, ItemType.PACKAGING)
        self.assertEqual(pouch.base_unit, "piece")
        self.assertEqual(pouch.opening_balance_qty, 500)
        self.assertEqual(pouch.opening_rate_paise, Decimal("250.000000"))

        # Carton: 30 pieces; Rs 15 each = 1500 paise/piece
        carton = item_dict["Carton"]
        self.assertEqual(carton.item_type, ItemType.PACKAGING)
        self.assertEqual(carton.base_unit, "piece")
        self.assertEqual(carton.opening_balance_qty, 30)
        self.assertEqual(carton.opening_rate_paise, Decimal("1500.000000"))

        # Murukku 200 g: 50 packets; GST 5% = 500 bp
        murukku_item = item_dict["Murukku 200 g"]
        self.assertEqual(murukku_item.item_type, ItemType.FINISHED_GOOD)
        self.assertEqual(murukku_item.base_unit, "packet")
        self.assertEqual(murukku_item.opening_balance_qty, 50)
        self.assertEqual(murukku_item.gst_rate_bp, 500)

        # 4. Verify Product & PriceList
        product = self.db.scalar(select(Product).where(Product.item_id == murukku_item.id))
        self.assertIsNotNone(product)
        self.assertEqual(product.pack_size_desc, "200 g")
        self.assertEqual(product.packets_per_carton, 20)

        pli = self.db.scalar(select(PriceListItem).where(PriceListItem.product_id == product.id))
        self.assertIsNotNone(pli)
        self.assertEqual(pli.price_paise, 5000)  # Rs 50/packet in paise

        # 5. Verify BOM for Murukku 200 g (1 batch = 200 packets)
        bom = self.db.scalar(select(BOM).where(BOM.product_id == product.id, BOM.version == 1))
        self.assertIsNotNone(bom)
        self.assertEqual(bom.batch_output_packets, 200)

        bom_items = self.db.scalars(select(BOMItem).where(BOMItem.bom_id == bom.id)).all()
        self.assertEqual(len(bom_items), 3)
        bom_map = {bi.item_id: bi for bi in bom_items}

        self.assertEqual(bom_map[flour.id].quantity_per_batch, 40000)  # 40 kg flour
        self.assertEqual(bom_map[oil.id].quantity_per_batch, 10000)    # 10 L oil
        self.assertEqual(bom_map[spice.id].quantity_per_batch, 1200)   # 1.2 kg spice mix

        # Verify PackagingSpecs on Product variant (Murukku 200 g)
        from app.models.product import PackagingSpec
        pkg_specs = self.db.scalars(select(PackagingSpec).where(PackagingSpec.product_id == product.id)).all()
        self.assertEqual(len(pkg_specs), 2)
        pkg_map = {ps.item_id: ps for ps in pkg_specs}
        self.assertEqual(pkg_map[pouch.id].qty_base, 1)
        self.assertEqual(pkg_map[pouch.id].per_packets, 1)             # 1 pouch per 1 packet
        self.assertEqual(pkg_map[carton.id].qty_base, 1)
        self.assertEqual(pkg_map[carton.id].per_packets, 20)           # 1 carton per 20 packets

        # 6. Verify Customers
        customers = self.db.scalars(select(Customer)).all()
        self.assertEqual(len(customers), 2)
        cust_map = {c.gstin: c for c in customers}

        ret_a = cust_map["33AAAAA0000A1Z5"]
        self.assertEqual(ret_a.state_code, "33")
        self.assertEqual(ret_a.customer_type, CustomerType.RETAILER)

        dist_b = cust_map["29BBBBB1111B1Z2"]
        self.assertEqual(dist_b.state_code, "29")
        self.assertEqual(dist_b.customer_type, CustomerType.DISTRIBUTOR)

        # 7. Test Idempotence: execute run_seed AGAIN on the same database
        run_seed(self.db)

        # Counts must remain identical
        self.assertEqual(len(self.db.scalars(select(User)).all()), 6)
        self.assertEqual(len(self.db.scalars(select(Item)).all()), 6)
        self.assertEqual(len(self.db.scalars(select(Product)).all()), 1)
        self.assertEqual(len(self.db.scalars(select(BOM)).all()), 1)
        self.assertEqual(len(self.db.scalars(select(BOMItem)).all()), 3)
        self.assertEqual(len(self.db.scalars(select(PackagingSpec)).all()), 2)
        self.assertEqual(len(self.db.scalars(select(Customer)).all()), 2)
        self.assertEqual(len(self.db.scalars(select(CompanySettings)).all()), 1)


if __name__ == "__main__":
    unittest.main()
