"""create invoices, invoice_lines, dispatches, dispatch_lines, credit_notes, and credit_note_lines tables

Revision ID: 0007_invoices_dispatches_credit_notes
Revises: 0006_orders_and_sequences
Create Date: 2026-11-25 21:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_invoices_dispatches_credit_notes'
down_revision: Union[str, None] = '0006_orders_and_sequences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_no', sa.String(length=64), nullable=False),
        sa.Column('financial_year', sa.String(length=16), nullable=False),
        sa.Column('invoice_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='POSTED', nullable=False),
        sa.Column('seller_name', sa.String(length=255), nullable=False),
        sa.Column('seller_gstin', sa.String(length=15), nullable=False),
        sa.Column('seller_address', sa.Text(), nullable=False),
        sa.Column('seller_state_code', sa.String(length=4), nullable=False),
        sa.Column('buyer_name', sa.String(length=255), nullable=False),
        sa.Column('buyer_gstin', sa.String(length=15), nullable=True),
        sa.Column('buyer_address', sa.Text(), nullable=False),
        sa.Column('buyer_state_code', sa.String(length=4), nullable=False),
        sa.Column('place_of_supply_state_code', sa.String(length=4), nullable=False),
        sa.Column('is_igst', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('taxable_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('cgst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('sgst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('igst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('round_off_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('grand_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_reason', sa.Text(), nullable=True),
        sa.CheckConstraint('taxable_total_paise >= 0', name='ck_invoices_taxable_non_negative'),
        sa.CheckConstraint('grand_total_paise >= 0', name='ck_invoices_grand_total_non_negative'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invoice_no', name='uq_invoices_invoice_no'),
    )
    op.create_index(op.f('ix_invoices_id'), 'invoices', ['id'], unique=False)
    op.create_index(op.f('ix_invoices_invoice_no'), 'invoices', ['invoice_no'], unique=True)
    op.create_index(op.f('ix_invoices_financial_year'), 'invoices', ['financial_year'], unique=False)
    op.create_index(op.f('ix_invoices_order_id'), 'invoices', ['order_id'], unique=False)
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)

    # 2. Create invoice_lines table
    op.create_table(
        'invoice_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('hsn_code', sa.String(length=16), nullable=False),
        sa.Column('quantity_packets', sa.Integer(), nullable=False),
        sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
        sa.Column('taxable_paise', sa.BigInteger(), nullable=False),
        sa.Column('gst_rate_bp', sa.Integer(), nullable=False),
        sa.Column('cgst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('sgst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('igst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('line_total_paise', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('quantity_packets > 0', name='ck_invoice_lines_quantity_positive'),
        sa.CheckConstraint('unit_price_paise >= 0', name='ck_invoice_lines_unit_price_non_negative'),
        sa.CheckConstraint('taxable_paise >= 0', name='ck_invoice_lines_taxable_non_negative'),
        sa.CheckConstraint('line_total_paise >= 0', name='ck_invoice_lines_line_total_non_negative'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoice_lines_id'), 'invoice_lines', ['id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_invoice_id'), 'invoice_lines', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_product_id'), 'invoice_lines', ['product_id'], unique=False)

    # 3. Create dispatches table
    op.create_table(
        'dispatches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dispatch_no', sa.String(length=64), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('dispatch_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('vehicle_no', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='DISPATCHED', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dispatch_no', name='uq_dispatches_dispatch_no'),
    )
    op.create_index(op.f('ix_dispatches_id'), 'dispatches', ['id'], unique=False)
    op.create_index(op.f('ix_dispatches_dispatch_no'), 'dispatches', ['dispatch_no'], unique=True)
    op.create_index(op.f('ix_dispatches_invoice_id'), 'dispatches', ['invoice_id'], unique=False)

    # 4. Create dispatch_lines table
    op.create_table(
        'dispatch_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dispatch_id', sa.Integer(), nullable=False),
        sa.Column('invoice_line_id', sa.Integer(), nullable=False),
        sa.Column('quantity_packets', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dispatch_id'], ['dispatches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_line_id'], ['invoice_lines.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dispatch_lines_id'), 'dispatch_lines', ['id'], unique=False)
    op.create_index(op.f('ix_dispatch_lines_dispatch_id'), 'dispatch_lines', ['dispatch_id'], unique=False)
    op.create_index(op.f('ix_dispatch_lines_invoice_line_id'), 'dispatch_lines', ['invoice_line_id'], unique=False)

    # 5. Create credit_notes table
    op.create_table(
        'credit_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('credit_note_no', sa.String(length=64), nullable=False),
        sa.Column('financial_year', sa.String(length=16), nullable=False),
        sa.Column('credit_note_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('return_stock', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='POSTED', nullable=False),
        sa.Column('seller_name', sa.String(length=255), nullable=False),
        sa.Column('seller_gstin', sa.String(length=15), nullable=False),
        sa.Column('seller_address', sa.Text(), nullable=False),
        sa.Column('seller_state_code', sa.String(length=4), nullable=False),
        sa.Column('buyer_name', sa.String(length=255), nullable=False),
        sa.Column('buyer_gstin', sa.String(length=15), nullable=True),
        sa.Column('buyer_address', sa.Text(), nullable=False),
        sa.Column('buyer_state_code', sa.String(length=4), nullable=False),
        sa.Column('place_of_supply_state_code', sa.String(length=4), nullable=False),
        sa.Column('is_igst', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('taxable_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('cgst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('sgst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('igst_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('round_off_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('grand_total_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('taxable_total_paise >= 0', name='ck_credit_notes_taxable_non_negative'),
        sa.CheckConstraint('grand_total_paise >= 0', name='ck_credit_notes_grand_total_non_negative'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credit_note_no', name='uq_credit_notes_credit_note_no'),
    )
    op.create_index(op.f('ix_credit_notes_id'), 'credit_notes', ['id'], unique=False)
    op.create_index(op.f('ix_credit_notes_credit_note_no'), 'credit_notes', ['credit_note_no'], unique=True)
    op.create_index(op.f('ix_credit_notes_financial_year'), 'credit_notes', ['financial_year'], unique=False)
    op.create_index(op.f('ix_credit_notes_invoice_id'), 'credit_notes', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_credit_notes_customer_id'), 'credit_notes', ['customer_id'], unique=False)

    # 6. Create credit_note_lines table
    op.create_table(
        'credit_note_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('credit_note_id', sa.Integer(), nullable=False),
        sa.Column('invoice_line_id', sa.Integer(), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('hsn_code', sa.String(length=16), nullable=False),
        sa.Column('quantity_packets', sa.Integer(), nullable=False),
        sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
        sa.Column('taxable_paise', sa.BigInteger(), nullable=False),
        sa.Column('gst_rate_bp', sa.Integer(), nullable=False),
        sa.Column('cgst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('sgst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('igst_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('line_total_paise', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('quantity_packets > 0', name='ck_credit_note_lines_quantity_positive'),
        sa.CheckConstraint('unit_price_paise >= 0', name='ck_credit_note_lines_unit_price_non_negative'),
        sa.CheckConstraint('taxable_paise >= 0', name='ck_credit_note_lines_taxable_non_negative'),
        sa.CheckConstraint('line_total_paise >= 0', name='ck_credit_note_lines_line_total_non_negative'),
        sa.ForeignKeyConstraint(['credit_note_id'], ['credit_notes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_line_id'], ['invoice_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credit_note_lines_id'), 'credit_note_lines', ['id'], unique=False)
    op.create_index(op.f('ix_credit_note_lines_credit_note_id'), 'credit_note_lines', ['credit_note_id'], unique=False)
    op.create_index(op.f('ix_credit_note_lines_product_id'), 'credit_note_lines', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_table('credit_note_lines')
    op.drop_table('credit_notes')
    op.drop_table('dispatch_lines')
    op.drop_table('dispatches')
    op.drop_table('invoice_lines')
    op.drop_table('invoices')
