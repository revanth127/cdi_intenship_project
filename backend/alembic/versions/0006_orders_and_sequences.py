"""create orders, order_lines, order_status_history, and numbering_sequences tables

Revision ID: 0006_orders_and_sequences
Revises: 0005_production_runs
Create Date: 2026-11-25 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_orders_and_sequences'
down_revision: Union[str, None] = '0005_production_runs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create numbering_sequences table
    op.create_table(
        'numbering_sequences',
        sa.Column('sequence_name', sa.String(length=32), nullable=False),
        sa.Column('financial_year', sa.String(length=16), nullable=False),
        sa.Column('last_number', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('sequence_name', 'financial_year', name='pk_numbering_sequences'),
    )

    # 2. Create orders table
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_no', sa.String(length=64), nullable=False),
        sa.Column('client_uuid', sa.String(length=64), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('salesman_id', sa.Integer(), nullable=False),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='SUBMITTED', nullable=False),
        sa.Column('total_amount_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('total_amount_paise >= 0', name='ck_orders_total_paise_non_negative'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['salesman_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_no', name='uq_orders_order_no'),
        sa.UniqueConstraint('client_uuid', name='uq_orders_client_uuid'),
    )
    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)
    op.create_index(op.f('ix_orders_order_no'), 'orders', ['order_no'], unique=True)
    op.create_index(op.f('ix_orders_client_uuid'), 'orders', ['client_uuid'], unique=True)
    op.create_index(op.f('ix_orders_customer_id'), 'orders', ['customer_id'], unique=False)
    op.create_index(op.f('ix_orders_salesman_id'), 'orders', ['salesman_id'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)

    # 3. Create order_lines table
    op.create_table(
        'order_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity_packets', sa.Integer(), nullable=False),
        sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
        sa.Column('line_total_paise', sa.BigInteger(), nullable=False),
        sa.Column('price_source', sa.String(length=32), server_default='PRICE_LIST', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('quantity_packets > 0', name='ck_order_lines_quantity_positive'),
        sa.CheckConstraint('unit_price_paise >= 0', name='ck_order_lines_unit_price_non_negative'),
        sa.CheckConstraint('line_total_paise >= 0', name='ck_order_lines_line_total_non_negative'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_lines_id'), 'order_lines', ['id'], unique=False)
    op.create_index(op.f('ix_order_lines_order_id'), 'order_lines', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_lines_product_id'), 'order_lines', ['product_id'], unique=False)

    # 4. Create order_status_history table
    op.create_table(
        'order_status_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_status_history_id'), 'order_status_history', ['id'], unique=False)
    op.create_index(op.f('ix_order_status_history_order_id'), 'order_status_history', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_order_status_history_order_id'), table_name='order_status_history')
    op.drop_index(op.f('ix_order_status_history_id'), table_name='order_status_history')
    op.drop_table('order_status_history')

    op.drop_index(op.f('ix_order_lines_product_id'), table_name='order_lines')
    op.drop_index(op.f('ix_order_lines_order_id'), table_name='order_lines')
    op.drop_index(op.f('ix_order_lines_id'), table_name='order_lines')
    op.drop_table('order_lines')

    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_salesman_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_customer_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_client_uuid'), table_name='orders')
    op.drop_index(op.f('ix_orders_order_no'), table_name='orders')
    op.drop_index(op.f('ix_orders_id'), table_name='orders')
    op.drop_table('orders')

    op.drop_table('numbering_sequences')
