"""create stock_movements and purchase tables with immutability trigger

Revision ID: 0004_stock_ledger_and_purchases
Revises: 0003_audit_log_and_roles
Create Date: 2026-11-23 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_stock_ledger_and_purchases'
down_revision: Union[str, None] = '0003_audit_log_and_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create stock_movements table
    op.create_table(
        'stock_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('movement_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('movement_type', sa.String(length=32), nullable=False),
        sa.Column('quantity_base', sa.BigInteger(), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('value_paise', sa.BigInteger(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=True),
        sa.Column('reverses_movement_id', sa.Integer(), nullable=True),
        sa.Column('batch_no', sa.String(length=64), nullable=True),
        sa.Column('expiry_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_stock_movements_created_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_stock_movements_item_id_items'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reverses_movement_id'], ['stock_movements.id'], name=op.f('fk_stock_movements_reverses_movement_id_stock_movements'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_movements'))
    )
    op.create_index(op.f('ix_stock_movements_id'), 'stock_movements', ['id'], unique=False)
    op.create_index(op.f('ix_stock_movements_item_id'), 'stock_movements', ['item_id'], unique=False)
    op.create_index(op.f('ix_stock_movements_movement_type'), 'stock_movements', ['movement_type'], unique=False)
    op.create_index('ix_stock_movements_item_date', 'stock_movements', ['item_id', 'movement_date'], unique=False)
    op.create_index('ix_stock_movements_source', 'stock_movements', ['source_type', 'source_id'], unique=False)

    # 2. Create purchases table
    op.create_table(
        'purchases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_no', sa.String(length=64), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('supplier_invoice_no', sa.String(length=64), nullable=True),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('total_paise', sa.BigInteger(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_purchases_created_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchases_supplier_id_suppliers'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchases')),
        sa.UniqueConstraint('purchase_no', name=op.f('uq_purchases_purchase_no'))
    )
    op.create_index(op.f('ix_purchases_id'), 'purchases', ['id'], unique=False)
    op.create_index(op.f('ix_purchases_purchase_no'), 'purchases', ['purchase_no'], unique=True)
    op.create_index(op.f('ix_purchases_supplier_id'), 'purchases', ['supplier_id'], unique=False)

    # 3. Create purchase_lines table
    op.create_table(
        'purchase_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity_base', sa.BigInteger(), nullable=False),
        sa.Column('unit_entered', sa.String(length=16), nullable=False),
        sa.Column('rate_paise', sa.BigInteger(), nullable=False),
        sa.Column('line_total_paise', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_purchase_lines_item_id_items'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], name=op.f('fk_purchase_lines_purchase_id_purchases'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_lines'))
    )
    op.create_index(op.f('ix_purchase_lines_id'), 'purchase_lines', ['id'], unique=False)
    op.create_index(op.f('ix_purchase_lines_item_id'), 'purchase_lines', ['item_id'], unique=False)
    op.create_index(op.f('ix_purchase_lines_purchase_id'), 'purchase_lines', ['purchase_id'], unique=False)

    # 4. Add DB-level protection against UPDATE/DELETE on stock_movements
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        op.execute("""
        CREATE OR REPLACE FUNCTION prevent_stock_movements_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Stock movements are strictly immutable. UPDATE and DELETE operations are forbidden.';
        END;
        $$ LANGUAGE plpgsql;
        """)

        op.execute("""
        CREATE TRIGGER trg_prevent_stock_movements_update_delete
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW
        EXECUTE FUNCTION prevent_stock_movements_modification();
        """)
    elif dialect_name == 'sqlite':
        op.execute("""
        CREATE TRIGGER trg_prevent_stock_movements_update
        BEFORE UPDATE ON stock_movements
        BEGIN
            SELECT RAISE(ABORT, 'Stock movements are strictly immutable. UPDATE operations are forbidden.');
        END;
        """)
        op.execute("""
        CREATE TRIGGER trg_prevent_stock_movements_delete
        BEFORE DELETE ON stock_movements
        BEGIN
            SELECT RAISE(ABORT, 'Stock movements are strictly immutable. DELETE operations are forbidden.');
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_stock_movements_update_delete ON stock_movements;")
        op.execute("DROP FUNCTION IF EXISTS prevent_stock_movements_modification();")
    elif dialect_name == 'sqlite':
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_stock_movements_update;")
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_stock_movements_delete;")

    op.drop_table('purchase_lines')
    op.drop_table('purchases')
    op.drop_table('stock_movements')
