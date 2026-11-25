"""create master data tables and core domain schema

Revision ID: 0002_master_data_tables
Revises: 0001_initial_empty
Create Date: 2026-11-23 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_master_data_tables'
down_revision: Union[str, None] = '0001_initial_empty'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 2. company_settings
    op.create_table(
        'company_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('gstin', sa.String(length=15), nullable=False),
        sa.Column('state_code', sa.String(length=2), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('financial_year_start_month', sa.Integer(), server_default='4', nullable=False),
        sa.Column('variance_tolerance_pct', sa.Numeric(precision=5, scale=2), server_default='3.00', nullable=False),
        sa.Column('invoice_prefix', sa.String(length=16), server_default='INV-', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name=op.f('ck_company_settings_single_row')),
        sa.CheckConstraint('financial_year_start_month BETWEEN 1 AND 12', name=op.f('ck_company_settings_fy_start_month')),
        sa.CheckConstraint('variance_tolerance_pct >= 0', name=op.f('ck_company_settings_variance_tolerance_non_negative')),
        sa.CheckConstraint('length(state_code) = 2', name=op.f('ck_company_settings_state_code_len')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_company_settings'))
    )

    # 3. items (unified inventory item master)
    op.create_table(
        'items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('base_unit', sa.String(length=16), nullable=False),
        sa.Column('display_unit', sa.String(length=16), nullable=False),
        sa.Column('hsn_code', sa.String(length=16), nullable=True),
        sa.Column('gst_rate_bp', sa.Integer(), server_default='0', nullable=False),
        sa.Column('reorder_level', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('opening_balance_qty', sa.BigInteger(), nullable=True),
        sa.Column('opening_rate_paise', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('gst_rate_bp >= 0 AND gst_rate_bp <= 10000', name=op.f('ck_items_gst_rate_bp_range')),
        sa.CheckConstraint('reorder_level IS NULL OR reorder_level >= 0', name=op.f('ck_items_reorder_level_non_negative')),
        sa.CheckConstraint('opening_balance_qty IS NULL OR opening_balance_qty >= 0', name=op.f('ck_items_opening_balance_qty_non_negative')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_items'))
    )
    op.create_index(op.f('ix_items_id'), 'items', ['id'], unique=False)
    op.create_index(op.f('ix_items_item_type'), 'items', ['item_type'], unique=False)
    op.create_index(op.f('ix_items_name'), 'items', ['name'], unique=True)

    # 4. products (finished goods linking 1:1 to item)
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('pack_size_desc', sa.String(length=64), nullable=False),
        sa.Column('packets_per_carton', sa.Integer(), server_default='20', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('packets_per_carton > 0', name=op.f('ck_products_packets_per_carton_positive')),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_products_item_id_items'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
        sa.UniqueConstraint('item_id', name=op.f('uq_products_item_id'))
    )
    op.create_index(op.f('ix_products_id'), 'products', ['id'], unique=False)

    # 5. price_lists
    op.create_table(
        'price_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_price_lists')),
        sa.UniqueConstraint('name', name=op.f('uq_price_lists_name'))
    )
    op.create_index(op.f('ix_price_lists_id'), 'price_lists', ['id'], unique=False)

    # 6. price_list_items
    op.create_table(
        'price_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('price_list_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('price_paise', sa.BigInteger(), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('price_paise >= 0', name=op.f('ck_price_list_items_price_non_negative')),
        sa.ForeignKeyConstraint(['price_list_id'], ['price_lists.id'], name=op.f('fk_price_list_items_price_list_id_price_lists'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_price_list_items_product_id_products'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_price_list_items')),
        sa.UniqueConstraint('price_list_id', 'product_id', 'effective_from', name=op.f('uq_price_list_items_effective'))
    )
    op.create_index(op.f('ix_price_list_items_id'), 'price_list_items', ['id'], unique=False)
    op.create_index(op.f('ix_price_list_items_price_list_id'), 'price_list_items', ['price_list_id'], unique=False)
    op.create_index(op.f('ix_price_list_items_product_id'), 'price_list_items', ['product_id'], unique=False)

    # 7. customers
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('customer_type', sa.String(length=32), nullable=False),
        sa.Column('gstin', sa.String(length=15), nullable=True),
        sa.Column('state_code', sa.String(length=2), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column('assigned_salesman_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('length(state_code) = 2', name=op.f('ck_customers_state_code_len')),
        sa.ForeignKeyConstraint(['assigned_salesman_id'], ['users.id'], name=op.f('fk_customers_assigned_salesman_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customers'))
    )
    op.create_index(op.f('ix_customers_id'), 'customers', ['id'], unique=False)
    op.create_index(op.f('ix_customers_name'), 'customers', ['name'], unique=False)
    op.create_index(op.f('ix_customers_assigned_salesman_id'), 'customers', ['assigned_salesman_id'], unique=False)
    op.create_index('uq_customers_gstin', 'customers', ['gstin'], unique=True, postgresql_where=sa.text('gstin IS NOT NULL'))

    # 8. customer_price_overrides
    op.create_table(
        'customer_price_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('price_paise', sa.BigInteger(), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('price_paise >= 0', name=op.f('ck_customer_price_overrides_price_non_negative')),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_customer_price_overrides_customer_id_customers'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_customer_price_overrides_product_id_products'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_price_overrides')),
        sa.UniqueConstraint('customer_id', 'product_id', 'effective_from', name=op.f('uq_customer_price_overrides_effective'))
    )
    op.create_index(op.f('ix_customer_price_overrides_id'), 'customer_price_overrides', ['id'], unique=False)

    # 9. suppliers
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('gstin', sa.String(length=15), nullable=True),
        sa.Column('state_code', sa.String(length=2), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('length(state_code) = 2', name=op.f('ck_suppliers_state_code_len')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers'))
    )
    op.create_index(op.f('ix_suppliers_id'), 'suppliers', ['id'], unique=False)
    op.create_index(op.f('ix_suppliers_name'), 'suppliers', ['name'], unique=False)
    op.create_index('uq_suppliers_gstin', 'suppliers', ['gstin'], unique=True, postgresql_where=sa.text('gstin IS NOT NULL'))

    # 10. boms
    op.create_table(
        'boms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('batch_output_packets', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('batch_output_packets > 0', name=op.f('ck_boms_batch_output_packets_positive')),
        sa.CheckConstraint('version > 0', name=op.f('ck_boms_version_positive')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_boms_product_id_products'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_boms')),
        sa.UniqueConstraint('product_id', 'version', name=op.f('uq_boms_product_version'))
    )
    op.create_index(op.f('ix_boms_id'), 'boms', ['id'], unique=False)
    op.create_index(op.f('ix_boms_product_id'), 'boms', ['product_id'], unique=False)

    # 11. bom_items
    op.create_table(
        'bom_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bom_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity_per_batch', sa.BigInteger(), nullable=False),
        sa.Column('unit_for_display', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('quantity_per_batch > 0', name=op.f('ck_bom_items_quantity_per_batch_positive')),
        sa.ForeignKeyConstraint(['bom_id'], ['boms.id'], name=op.f('fk_bom_items_bom_id_boms'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_bom_items_item_id_items'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bom_items')),
        sa.UniqueConstraint('bom_id', 'item_id', name=op.f('uq_bom_items_bom_item'))
    )
    op.create_index(op.f('ix_bom_items_id'), 'bom_items', ['id'], unique=False)
    op.create_index(op.f('ix_bom_items_bom_id'), 'bom_items', ['bom_id'], unique=False)
    op.create_index(op.f('ix_bom_items_item_id'), 'bom_items', ['item_id'], unique=False)


def downgrade() -> None:
    op.drop_table('bom_items')
    op.drop_table('boms')
    op.drop_table('suppliers')
    op.drop_table('customer_price_overrides')
    op.drop_table('customers')
    op.drop_table('price_list_items')
    op.drop_table('price_lists')
    op.drop_table('products')
    op.drop_table('items')
    op.drop_table('company_settings')
    op.drop_table('users')
