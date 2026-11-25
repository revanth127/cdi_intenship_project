"""create production_runs and production_run_lines tables and add variance_tolerance_pct to bom_items

Revision ID: 0005_production_runs
Revises: 0004_stock_ledger_and_purchases
Create Date: 2026-11-23 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_production_runs'
down_revision: Union[str, None] = '0004_stock_ledger_and_purchases'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add variance_tolerance_pct column to bom_items
    op.add_column(
        'bom_items',
        sa.Column('variance_tolerance_pct', sa.Numeric(precision=5, scale=2), nullable=True)
    )

    # 2. Create production_runs table
    op.create_table(
        'production_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_no', sa.String(length=64), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('bom_id', sa.Integer(), nullable=False),
        sa.Column('bom_version', sa.Integer(), nullable=False),
        sa.Column('run_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('batches', sa.Numeric(precision=10, scale=4), server_default='1.0000', nullable=False),
        sa.Column('batch_size_packets', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='DRAFT', nullable=False),
        sa.Column('expected_output_packets', sa.Integer(), nullable=False),
        sa.Column('actual_good_packets', sa.Integer(), nullable=True),
        sa.Column('wastage_packets', sa.Integer(), nullable=True),
        sa.Column('yield_variance_pct', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('is_yield_flagged', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('total_material_cost_paise', sa.BigInteger(), nullable=True),
        sa.Column('unit_material_cost_paise', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('posted_by', sa.Integer(), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('batches > 0', name='ck_production_runs_batches_positive'),
        sa.CheckConstraint('expected_output_packets >= 0', name='ck_production_runs_expected_output_non_negative'),
        sa.ForeignKeyConstraint(['bom_id'], ['boms.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['posted_by'], ['users.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_no', name='uq_production_runs_run_no'),
    )
    op.create_index(op.f('ix_production_runs_id'), 'production_runs', ['id'], unique=False)
    op.create_index(op.f('ix_production_runs_run_no'), 'production_runs', ['run_no'], unique=True)
    op.create_index(op.f('ix_production_runs_product_id'), 'production_runs', ['product_id'], unique=False)
    op.create_index(op.f('ix_production_runs_bom_id'), 'production_runs', ['bom_id'], unique=False)

    # 3. Create production_run_lines table
    op.create_table(
        'production_run_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('planned_qty_base', sa.BigInteger(), nullable=False),
        sa.Column('actual_qty_base', sa.BigInteger(), nullable=True),
        sa.Column('damaged_qty_base', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('variance_qty_base', sa.BigInteger(), nullable=True),
        sa.Column('variance_pct', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('is_flagged', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('value_paise', sa.BigInteger(), nullable=True),
        sa.Column('unit_for_display', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('planned_qty_base >= 0', name='ck_prod_run_lines_planned_qty_non_negative'),
        sa.CheckConstraint('damaged_qty_base >= 0', name='ck_prod_run_lines_damaged_qty_non_negative'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['run_id'], ['production_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_production_run_lines_id'), 'production_run_lines', ['id'], unique=False)
    op.create_index(op.f('ix_production_run_lines_run_id'), 'production_run_lines', ['run_id'], unique=False)
    op.create_index(op.f('ix_production_run_lines_item_id'), 'production_run_lines', ['item_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_production_run_lines_item_id'), table_name='production_run_lines')
    op.drop_index(op.f('ix_production_run_lines_run_id'), table_name='production_run_lines')
    op.drop_index(op.f('ix_production_run_lines_id'), table_name='production_run_lines')
    op.drop_table('production_run_lines')

    op.drop_index(op.f('ix_production_runs_bom_id'), table_name='production_runs')
    op.drop_index(op.f('ix_production_runs_product_id'), table_name='production_runs')
    op.drop_index(op.f('ix_production_runs_run_no'), table_name='production_runs')
    op.drop_index(op.f('ix_production_runs_id'), table_name='production_runs')
    op.drop_table('production_runs')

    op.drop_column('bom_items', 'variance_tolerance_pct')
