#!/usr/bin/env python3
"""
Seed script for Master Data Layer.
Loads items, finished product, pricing, BOM, company settings, customers, and users.
Safe and idempotent: can be executed multiple times without errors or duplicate rows.
"""
from datetime import datetime, timezone
from decimal import Decimal
import logging
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import get_password_hash
from app.models.bom import BOM, BOMItem
from app.models.company import CompanySettings
from app.models.customer import Customer, CustomerType
from app.models.item import Item, ItemType
from app.models.pricing import PriceList, PriceListItem
from app.models.product import Product, ProductFamily, PackagingSpec
from app.models.supplier import Supplier
from app.models.user import User, UserRole

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

# ------------------------------------------------------------------------------
# DEMO USER CREDENTIALS CONFIGURATION
# Defined in ONE place for deterministic evaluation across all 5 roles.
# ------------------------------------------------------------------------------
DEMO_CREDENTIALS = [
    {
        "role": UserRole.OWNER,
        "role_name": "OWNER",
        "email": "owner@foodmfr.local",
        "name": "Senthil Nathan (Owner)",
        "password": "OwnerPass123!",
        "access": "Executive Overview, costing margins, variance alerts, receivables & telemetry",
    },
    {
        "role": UserRole.ADMIN,
        "role_name": "ADMIN",
        "email": "admin@foodmfr.local",
        "name": "System Administrator",
        "password": "AdminPass123!",
        "access": "Full system configuration, user accounts, master data & order approval",
    },
    {
        "role": UserRole.PRODUCTION,
        "role_name": "PRODUCTION",
        "email": "production@foodmfr.local",
        "name": "Production Supervisor",
        "password": "ProdPass123!",
        "access": "BOM management, production batch logging, consumption & variance alerts",
    },
    {
        "role": UserRole.ACCOUNTANT,
        "role_name": "ACCOUNTANT",
        "email": "accountant@foodmfr.local",
        "name": "Chief Accountant",
        "password": "AcctPass123!",
        "access": "GST Invoices, receivables ageing, payment allocations & audit reports",
    },
    {
        "role": UserRole.SALESMAN,
        "role_name": "SALESMAN",
        "email": "salesman.a@foodmfr.local",
        "name": "Salesman A (Madurai)",
        "password": "SalesPass123!",
        "access": "Mobile offline field order booking & pricing catalog (Retailer A)",
    },
    {
        "role": UserRole.SALESMAN,
        "role_name": "SALESMAN",
        "email": "salesman.b@foodmfr.local",
        "name": "Salesman B (Bengaluru)",
        "password": "SalesPass123!",
        "access": "Mobile offline field order booking & pricing catalog (Distributor B)",
    },
]


def print_credentials_table() -> None:
    border = "=" * 105
    header = f"{'ROLE':<12} | {'EMAIL':<28} | {'PASSWORD':<16} | {'ACCESS SUMMARY'}"
    div = "-" * 105
    print("\n" + border)
    print("DEMO CREDENTIALS TABLE")
    print(border)
    print(header)
    print(div)
    for cred in DEMO_CREDENTIALS:
        print(f"{cred['role_name']:<12} | {cred['email']:<28} | {cred['password']:<16} | {cred['access']}")
    print(border + "\n")


def seed_company_settings(db: Session) -> CompanySettings:
    """Seed or update company configuration (Tamil Nadu, state code 33)."""
    company = db.get(CompanySettings, 1)
    if not company:
        company = CompanySettings(
            id=1,
            company_name="Sri Murugan Traditional Foods Pvt Ltd",
            gstin="33AABCS1234D1Z8",
            state_code="33",
            address="Plot 42, SIDCO Industrial Estate, Kappalur, Madurai, Tamil Nadu - 625008",
            financial_year_start_month=4,
            variance_tolerance_pct=Decimal("3.00"),
            invoice_prefix="INV-",
        )
        db.add(company)
        db.flush()
        logger.info("Created CompanySettings (State 33 - Tamil Nadu).")
    else:
        company.company_name = "Sri Murugan Traditional Foods Pvt Ltd"
        company.gstin = "33AABCS1234D1Z8"
        company.state_code = "33"
        company.variance_tolerance_pct = Decimal("3.00")
        logger.info("CompanySettings already exists; refreshed.")
    return company


def seed_users(db: Session) -> dict[str, User]:
    """
    Seed system users across the 5 core roles from DEMO_CREDENTIALS config:
    - OWNER
    - ADMIN
    - PRODUCTION
    - ACCOUNTANT
    - SALESMAN (Salesman A & Salesman B)
    """
    user_map = {}
    for u_data in DEMO_CREDENTIALS:
        stmt = select(User).where(User.email == u_data["email"])
        user = db.scalar(stmt)
        hashed_pwd = get_password_hash(u_data["password"])
        if not user:
            user = User(
                email=u_data["email"],
                hashed_password=hashed_pwd,
                full_name=u_data["name"],
                role=u_data["role"],
                is_active=True,
            )
            db.add(user)
            db.flush()
            logger.info("Created user %s (%s)", user.full_name, user.role.value)
        else:
            user.role = u_data["role"]
            user.hashed_password = hashed_pwd
            user.full_name = u_data["name"]
            user.is_active = True
        user_map[u_data["email"]] = user

    return user_map


def seed_items(db: Session) -> dict[str, Item]:
    """
    Seed inventory items with opening stock in BASE UNITS (grams, ml, pieces):
    - Flour: 100 kg = 100,000 g; Rs 42/kg = 4.2 paise/g
    - Cooking oil: 30 L = 30,000 ml; Rs 140/L = 14.0 paise/ml
    - Salt and spice mix: 5 kg = 5,000 g; Rs 200/kg = 20.0 paise/g
    - 200 g pouch: 500 pieces; Rs 2.50 each = 250 paise/piece
    - Carton: 30 pieces; Rs 15 each = 1500 paise/piece
    - Murukku 200 g (finished): 50 packets; GST 5%
    """
    item_definitions = [
        {
            "name": "Flour",
            "item_type": ItemType.RAW_MATERIAL,
            "base_unit": "g",
            "display_unit": "kg",
            "hsn_code": "1101",
            "gst_rate_bp": 0,
            "opening_balance_qty": 100000,           # 100 kg in grams
            "opening_rate_paise": Decimal("4.200000"),  # 4200 paise / 1000 g
        },
        {
            "name": "Cooking oil",
            "item_type": ItemType.RAW_MATERIAL,
            "base_unit": "ml",
            "display_unit": "L",
            "hsn_code": "1507",
            "gst_rate_bp": 500,                      # 5% GST
            "opening_balance_qty": 30000,            # 30 L in ml
            "opening_rate_paise": Decimal("14.000000"), # 14000 paise / 1000 ml
        },
        {
            "name": "Salt and spice mix",
            "item_type": ItemType.RAW_MATERIAL,
            "base_unit": "g",
            "display_unit": "kg",
            "hsn_code": "0910",
            "gst_rate_bp": 500,
            "opening_balance_qty": 5000,             # 5 kg in grams
            "opening_rate_paise": Decimal("20.000000"), # 20000 paise / 1000 g
        },
        {
            "name": "200 g pouch",
            "item_type": ItemType.PACKAGING,
            "base_unit": "piece",
            "display_unit": "piece",
            "hsn_code": "3923",
            "gst_rate_bp": 1800,                     # 18% GST
            "opening_balance_qty": 500,              # 500 pieces
            "opening_rate_paise": Decimal("250.000000"),# Rs 2.50 in paise
        },
        {
            "name": "Carton",
            "item_type": ItemType.PACKAGING,
            "base_unit": "piece",
            "display_unit": "piece",
            "hsn_code": "4819",
            "gst_rate_bp": 1200,                     # 12% GST
            "opening_balance_qty": 30,               # 30 cartons/boxes
            "opening_rate_paise": Decimal("1500.000000"),# Rs 15 in paise
        },
        {
            "name": "Murukku 200 g",
            "item_type": ItemType.FINISHED_GOOD,
            "base_unit": "packet",
            "display_unit": "packet",
            "hsn_code": "1905",
            "gst_rate_bp": 500,                      # 5% GST on snacks
            "opening_balance_qty": 50,               # 50 packets
            "opening_rate_paise": Decimal("5000.000000"),# Selling price Rs 50/packet
        },
    ]

    item_map = {}
    for idef in item_definitions:
        item = db.scalar(select(Item).where(Item.name == idef["name"]))
        if not item:
            item = Item(**idef)
            db.add(item)
            db.flush()
            logger.info("Created Item: %s (%s)", item.name, item.item_type.value)
        else:
            item.opening_balance_qty = idef["opening_balance_qty"]
            item.opening_rate_paise = idef["opening_rate_paise"]
            item.gst_rate_bp = idef["gst_rate_bp"]
        item_map[idef["name"]] = item

    return item_map


def seed_product_family(db: Session) -> ProductFamily:
    """Seed ProductFamily 'Murukku' sharing common BOM across variants."""
    family = db.scalar(select(ProductFamily).where(ProductFamily.name == "Murukku"))
    if not family:
        family = ProductFamily(
            name="Murukku",
            hsn_code="1905",
            gst_rate_bp=500,
            is_active=True,
        )
        db.add(family)
        db.flush()
        logger.info("Created ProductFamily: Murukku (HSN 1905, 5% GST)")
    return family


def seed_product_and_pricing(db: Session, family: ProductFamily, items: dict[str, Item]) -> Product:
    """
    Seed Product pack variant for Murukku 200 g, its PackagingSpecs,
    and Default PriceList with Rs 50/packet.
    """
    finished_item = items["Murukku 200 g"]
    product = db.scalar(select(Product).where(Product.item_id == finished_item.id))
    if not product:
        product = Product(
            family_id=family.id,
            item_id=finished_item.id,
            pack_name="Murukku 200 g",
            net_weight_g=200,
            packets_per_carton=20,  # 1 carton holds 20 packets
            is_active=True,
        )
        db.add(product)
        db.flush()
        logger.info("Created Product variant: Murukku 200 g (20 packets/carton).")
    else:
        product.family_id = family.id
        product.pack_name = "Murukku 200 g"
        product.net_weight_g = 200
        product.packets_per_carton = 20

    # Seed PackagingSpec for Murukku 200 g:
    # Pouch: 1 per 1 packet
    # Carton: 1 per 20 packets
    pouch_spec = db.scalar(
        select(PackagingSpec).where(
            PackagingSpec.product_id == product.id,
            PackagingSpec.item_id == items["200 g pouch"].id,
        )
    )
    if not pouch_spec:
        pouch_spec = PackagingSpec(
            product_id=product.id,
            item_id=items["200 g pouch"].id,
            qty_base=1,
            per_packets=1,
            unit_for_display="piece",
        )
        db.add(pouch_spec)
        logger.info("Created PackagingSpec for Murukku 200 g: 200 g pouch (1 per 1 packet)")

    carton_spec = db.scalar(
        select(PackagingSpec).where(
            PackagingSpec.product_id == product.id,
            PackagingSpec.item_id == items["Carton"].id,
        )
    )
    if not carton_spec:
        carton_spec = PackagingSpec(
            product_id=product.id,
            item_id=items["Carton"].id,
            qty_base=1,
            per_packets=20,
            unit_for_display="piece",
        )
        db.add(carton_spec)
        logger.info("Created PackagingSpec for Murukku 200 g: Carton (1 per 20 packets)")

    # Seed Default PriceList
    price_list = db.scalar(select(PriceList).where(PriceList.name == "Standard Selling Price"))
    if not price_list:
        price_list = PriceList(
            name="Standard Selling Price",
            description="Default wholesale and retail selling price list",
            is_default=True,
            is_active=True,
        )
        db.add(price_list)
        db.flush()
        logger.info("Created Default PriceList.")

    # Price per packet: Rs 50 = 5000 paise
    pli = db.scalar(
        select(PriceListItem).where(
            PriceListItem.price_list_id == price_list.id,
            PriceListItem.product_id == product.id,
        )
    )
    if not pli:
        pli = PriceListItem(
            price_list_id=price_list.id,
            product_id=product.id,
            price_paise=5000,  # Rs 50 in paise
            effective_from=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        db.add(pli)
        db.flush()
        logger.info("Created PriceListItem: Rs 50.00 (5000 paise) per packet.")

    return product


def seed_bom(db: Session, family: ProductFamily, product: Product, items: dict[str, Item]) -> BOM:
    """
    Seed Family BOM for Murukku:
    Batch yield = 40,000 g finished output.
    Recipe ingredients (RAW_MATERIAL only):
      - Flour: 40 kg = 40,000 g
      - Cooking oil: 10 L = 10,000 ml
      - Salt and spice mix: 1.2 kg = 1,200 g
    """
    bom = db.scalar(select(BOM).where(BOM.family_id == family.id, BOM.version == 1))
    if not bom:
        bom = BOM(
            family_id=family.id,
            product_id=product.id,
            version=1,
            expected_output_g=40000,
            is_active=True,
        )
        db.add(bom)
        db.flush()
        logger.info("Created Family BOM: Version 1 for Murukku (40,000 g expected output).")
    else:
        bom.product_id = product.id

    # Required recipe ingredients in BASE UNITS (RAW_MATERIAL only)
    required_ingredients = [
        {"item": items["Flour"], "qty_base": 40000, "unit_display": "kg"},           # 40 kg
        {"item": items["Cooking oil"], "qty_base": 10000, "unit_display": "L"},        # 10 L
        {"item": items["Salt and spice mix"], "qty_base": 1200, "unit_display": "kg"}, # 1.2 kg
    ]

    for req in required_ingredients:
        bom_item = db.scalar(
            select(BOMItem).where(
                BOMItem.bom_id == bom.id,
                BOMItem.item_id == req["item"].id,
            )
        )
        if not bom_item:
            bom_item = BOMItem(
                bom_id=bom.id,
                item_id=req["item"].id,
                quantity_per_batch=req["qty_base"],
                unit_for_display=req["unit_display"],
            )
            db.add(bom_item)
            logger.info("Added BOM item: %s (%d base units)", req["item"].name, req["qty_base"])
        else:
            bom_item.quantity_per_batch = req["qty_base"]
            bom_item.unit_for_display = req["unit_display"]

    db.flush()
    return bom


def seed_customers(db: Session, users: dict[str, User]) -> list[Customer]:
    """
    Seed Customers:
    - Retailer A: Tamil Nadu (state code 33), GSTIN present, assigned to Salesman A
    - Distributor B: Karnataka (state code 29), GSTIN present, assigned to Salesman B
    """
    salesman_a = users["salesman.a@foodmfr.local"]
    salesman_b = users["salesman.b@foodmfr.local"]

    customer_defs = [
        {
            "name": "Retailer A (Meenakshi Stores)",
            "customer_type": CustomerType.RETAILER,
            "gstin": "33AAAAA0000A1Z5",
            "state_code": "33",  # Tamil Nadu
            "address": "15 West Masi Street, Madurai, Tamil Nadu - 625001",
            "phone": "+91 94431 11222",
            "assigned_salesman_id": salesman_a.id,
        },
        {
            "name": "Distributor B (Karnataka Snack Distributors)",
            "customer_type": CustomerType.DISTRIBUTOR,
            "gstin": "29BBBBB1111B1Z2",
            "state_code": "29",  # Karnataka
            "address": "88 APMC Yard, Yeshwanthpur, Bengaluru, Karnataka - 560022",
            "phone": "+91 98860 33444",
            "assigned_salesman_id": salesman_b.id,
        },
    ]

    customers = []
    for cdef in customer_defs:
        customer = db.scalar(select(Customer).where(Customer.gstin == cdef["gstin"]))
        if not customer:
            customer = Customer(**cdef, is_active=True)
            db.add(customer)
            db.flush()
            logger.info("Created Customer: %s (State %s)", customer.name, customer.state_code)
        else:
            customer.name = cdef["name"]
            customer.customer_type = cdef["customer_type"]
            customer.state_code = cdef["state_code"]
            customer.assigned_salesman_id = cdef["assigned_salesman_id"]
        customers.append(customer)

    return customers


def seed_supplier(db: Session) -> Supplier:
    supplier = db.scalar(select(Supplier).where(Supplier.gstin == "33AAAAA1111A1Z1"))
    if not supplier:
        supplier = Supplier(
            name="Sri Lakshmi Agro Mills",
            gstin="33AAAAA1111A1Z1",
            state_code="33",
            address="Madurai, Tamil Nadu",
            phone="9876543210",
            is_active=True,
        )
        db.add(supplier)
        db.flush()
    return supplier


def seed_benchmark_transactions(
    db: Session,
    users: dict[str, User],
    items: dict[str, Item],
    product: Product,
    customers: list[Customer],
    supplier: Supplier,
) -> None:
    """Create the Section 5 business transactions once so a fresh install has its benchmark state."""
    from app.models.costing import OverheadCategory, OverheadEntry, OverheadStatus
    from app.models.invoice import Dispatch, DispatchStatus, Invoice
    from app.models.order import Order, OrderStatus
    from app.models.payment import Payment, PaymentMode
    from app.models.production import ProductionRun, ProductionRunStatus
    from app.models.purchase import Purchase
    from app.schemas.invoice import DispatchCreate
    from app.schemas.order import OrderCreate, OrderLineCreate
    from app.schemas.payment import PaymentAllocationCreate, PaymentCreate
    from app.schemas.production import ProductionRunCreate, ProductionRunLineUpdate, ProductionRunUpdate
    from app.schemas.purchase import PurchaseCreate, PurchaseLineCreate
    from app.services import invoicing as invoicing_service
    from app.services import orders as orders_service
    from app.services import production as production_service
    from app.services import purchase as purchase_service
    from app.services import receivables as receivables_service

    admin = users["admin@foodmfr.local"]
    production_user = users["production@foodmfr.local"]
    salesman_a = users["salesman.a@foodmfr.local"]
    salesman_b = users["salesman.b@foodmfr.local"]
    retailer_a, distributor_b = customers
    now = datetime.now(timezone.utc)

    purchase = db.scalar(
        select(Purchase).where(Purchase.supplier_invoice_no == "BENCHMARK-PO-001")
    )
    if not purchase:
        purchase_service.create_and_post_purchase(
            db,
            PurchaseCreate(
                supplier_id=supplier.id,
                supplier_invoice_no="BENCHMARK-PO-001",
                notes="Section 5 benchmark flour purchase",
                lines=[
                    PurchaseLineCreate(
                        item_id=items["Flour"].id,
                        quantity_entered=Decimal("60"),
                        unit_entered="kg",
                        rate_paise=4500,
                    )
                ],
            ),
            admin,
        )

    run = db.scalar(
        select(ProductionRun).where(ProductionRun.notes == "Section 5 benchmark production run")
    )
    if not run:
        run = production_service.create_run(
            db,
            ProductionRunCreate(
                product_id=product.id,
                batches=Decimal("1.0000"),
                run_date=now,
                notes="Section 5 benchmark production run",
            ),
            production_user,
        )
    if run.status == ProductionRunStatus.DRAFT:
        production_service.update_run(
            db,
            run.id,
            ProductionRunUpdate(
                actual_good_packets=188,
                lines=[
                    ProductionRunLineUpdate(item_id=items["Flour"].id, actual_qty_base=40000),
                    ProductionRunLineUpdate(item_id=items["Cooking oil"].id, actual_qty_base=10500),
                    ProductionRunLineUpdate(item_id=items["Salt and spice mix"].id, actual_qty_base=1200),
                    ProductionRunLineUpdate(item_id=items["200 g pouch"].id, damaged_qty_base=6),
                    ProductionRunLineUpdate(item_id=items["Carton"].id, actual_qty_base=9),
                ],
            ),
            production_user,
        )
        production_service.post_run(db, run.id, production_user)

    for category, amount, description in (
        (OverheadCategory.LABOUR, 120000, "Section 5 benchmark labour"),
        (OverheadCategory.GAS, 60000, "Section 5 benchmark gas"),
    ):
        existing = db.scalar(
            select(OverheadEntry).where(
                OverheadEntry.production_run_id == run.id,
                OverheadEntry.category == category,
                OverheadEntry.status == OverheadStatus.ACTIVE,
            )
        )
        if not existing:
            db.add(
                OverheadEntry(
                    entry_date=now,
                    category=category,
                    amount_paise=amount,
                    production_run_id=run.id,
                    description=description,
                    status=OverheadStatus.ACTIVE,
                    created_by=production_user.id,
                )
            )
    db.commit()

    retailer_order = db.scalar(
        select(Order).where(Order.client_uuid == "benchmark-retailer-a-invoice")
    )
    if not retailer_order:
        retailer_order, _ = orders_service.create_order(
            db,
            OrderCreate(
                client_uuid="benchmark-retailer-a-invoice",
                customer_id=retailer_a.id,
                lines=[OrderLineCreate(product_id=product.id, quantity_packets=150)],
            ),
            salesman_a,
        )
    if retailer_order.status == OrderStatus.SUBMITTED:
        orders_service.approve_order(db, retailer_order.id, admin)

    invoice = db.scalar(select(Invoice).where(Invoice.order_id == retailer_order.id))
    if not invoice:
        invoice = invoicing_service.create_invoice_from_order(db, retailer_order.id, admin)
    if not db.scalar(
        select(Dispatch).where(
            Dispatch.invoice_id == invoice.id,
            Dispatch.status == DispatchStatus.DISPATCHED,
        )
    ):
        invoicing_service.dispatch_invoice(db, invoice.id, DispatchCreate(), admin)

    if not db.scalar(
        select(Payment).where(Payment.reference_no == "BENCHMARK-RETAILER-A-PAYMENT")
    ):
        receivables_service.post_payment(
            db,
            PaymentCreate(
                customer_id=retailer_a.id,
                amount_paise=400000,
                mode=PaymentMode.UPI,
                reference_no="BENCHMARK-RETAILER-A-PAYMENT",
                allocations=[PaymentAllocationCreate(invoice_id=invoice.id, amount_paise=400000)],
            ),
            admin,
        )

    if not db.scalar(
        select(Order).where(Order.client_uuid == "benchmark-distributor-b-order")
    ):
        orders_service.create_order(
            db,
            OrderCreate(
                client_uuid="benchmark-distributor-b-order",
                customer_id=distributor_b.id,
                lines=[OrderLineCreate(product_id=product.id, quantity_packets=120)],
            ),
            salesman_b,
        )


def seed_opening_stock_movements(db: Session, items: dict[str, Item], admin_user: User) -> None:
    """
    Posts immutable OPENING movements to stock_movements from seed constants:
    - Flour: 100 kg (100,000 g) @ Rs 42/kg (4.200000 paise/g)
    - Cooking oil: 30 L (30,000 ml) @ Rs 140/L (14.000000 paise/ml)
    - Salt and spice mix: 5 kg (5,000 g) @ Rs 200/kg (20.000000 paise/g)
    - 200 g pouch: 500 pieces @ Rs 2.50 each (250.000000 paise/piece)
    - Carton: 30 pieces @ Rs 15 each (1500.000000 paise/piece)
    - Murukku 200 g: 50 packets @ estimated production cost placeholder (3500.000000 paise/packet = Rs 35)
    Idempotent: skips if OPENING movement already exists for the item.
    """
    from app.services.stock import post_movement
    from app.models.stock import MovementType, StockMovement

    opening_configs = [
        ("Flour", 100000, Decimal("4.200000")),
        ("Cooking oil", 30000, Decimal("14.000000")),
        ("Salt and spice mix", 5000, Decimal("20.000000")),
        ("200 g pouch", 500, Decimal("250.000000")),
        ("Carton", 30, Decimal("1500.000000")),
        ("Murukku 200 g", 50, Decimal("3500.000000")),
    ]

    for item_name, qty_base, unit_cost in opening_configs:
        item = items[item_name]
        existing = db.scalar(
            select(StockMovement).where(
                StockMovement.item_id == item.id,
                StockMovement.movement_type == MovementType.OPENING,
            )
        )
        if not existing:
            post_movement(
                db=db,
                item_id=item.id,
                movement_type=MovementType.OPENING,
                quantity_base=qty_base,
                unit_cost=unit_cost,
                source_type="OPENING",
                source_id="SEED",
                user=admin_user,
                note=f"Opening stock balance: {item.name}",
            )
            logger.info("Posted OPENING stock movement for %s: %d base units @ %s paise/unit", item.name, qty_base, unit_cost)
        else:
            logger.info("OPENING movement for %s already exists; skipping.", item.name)


def run_seed(db: Session | None = None) -> None:
    """Entrypoint function to run complete seed process idempotently."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        logger.info("Beginning master data seeding...")
        seed_company_settings(db)
        users = seed_users(db)
        items = seed_items(db)
        family = seed_product_family(db)
        product = seed_product_and_pricing(db, family, items)
        seed_bom(db, family, product, items)
        customers = seed_customers(db, users)
        supplier = seed_supplier(db)
        seed_opening_stock_movements(db, items, users["admin@foodmfr.local"])
        db.commit()
        seed_benchmark_transactions(db, users, items, product, customers, supplier)
        logger.info("Master data seeding completed successfully!")
        print_credentials_table()
    except Exception as exc:
        db.rollback()
        logger.error("Seeding failed: %s", exc)
        raise
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    run_seed()
