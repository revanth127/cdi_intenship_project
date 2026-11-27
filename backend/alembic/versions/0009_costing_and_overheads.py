"""create overhead_entries and run_cost_sheets tables

Revision ID: 0009_costing_and_overheads
Revises: 0008_payments_and_allocations
Create Date: 2026-11-26 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_costing_and_overheads'
down_revision: Union[str, None] = '0008_payments_and_allocations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create overhead_entries table
    op.create_table(
        'overhead_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('amount_paise', sa.BigInteger(), nullable=False),
        sa.Column('production_run_id', sa.Integer(), nullable=True),
        sa.Column('month', sa.String(length=7), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='ACTIVE', nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('void_reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint('amount_paise > 0', name='ck_overhead_entries_amount_positive'),
        sa.ForeignKeyConstraint(['production_run_id'], ['production_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_overhead_entries_id'), 'overhead_entries', ['id'], unique=False)
    op.create_index(op.f('ix_overhead_entries_entry_date'), 'overhead_entries', ['entry_date'], unique=False)
    op.create_index(op.f('ix_overhead_entries_category'), 'overhead_entries', ['category'], unique=False)
    op.create_index(op.f('ix_overhead_entries_production_run_id'), 'overhead_entries', ['production_run_id'], unique=False)
    op.create_index(op.f('ix_overhead_entries_month'), 'overhead_entries', ['month'], unique=False)
    op.create_index(op.f('ix_overhead_entries_status'), 'overhead_entries', ['status'], unique=False)

    # 2. Create run_cost_sheets table
    op.create_table(
        'run_cost_sheets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('material_cost_paise', sa.BigInteger(), nullable=False),
        sa.Column('labour_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('gas_power_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('other_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('total_cost_paise', sa.BigInteger(), nullable=False),
        sa.Column('good_packets', sa.Integer(), nullable=False),
        sa.Column('cost_per_packet', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('planned_cost_per_packet', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('cost_of_loss_paise', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['production_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', name='uq_run_cost_sheets_run_id'),
    )
    op.create_index(op.f('ix_run_cost_sheets_id'), 'run_cost_sheets', ['id'], unique=False)
    op.create_index(op.f('ix_run_cost_sheets_run_id'), 'run_cost_sheets', ['run_id'], unique=True)


def downgrade() -> None:
    op.drop_table('run_cost_sheets')
    op.drop_table('overhead_entries')
