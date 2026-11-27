"""audit log append-only triggers and columns

Revision ID: 0011_audit_log_append_only_and_columns
Revises: 0010_product_family_and_bom_pack_sizes
Create Date: 2026-11-26 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0011_audit_log_append_only_and_columns'
down_revision: Union[str, None] = '0010_product_family_and_bom_pack_sizes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add request_id and ip_address columns to audit_logs
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('request_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('ip_address', sa.String(length=45), nullable=True))
        batch_op.create_index(op.f('ix_audit_logs_request_id'), ['request_id'], unique=False)

    # 2. Append-only triggers blocking UPDATE and DELETE on audit_logs
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_logs_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Audit logs are strictly immutable. UPDATE and DELETE operations are forbidden.';
        END;
        $$ LANGUAGE plpgsql;
        """)

        op.execute("""
        CREATE TRIGGER trg_prevent_audit_logs_update_delete
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_logs_modification();
        """)
    elif dialect_name == 'sqlite':
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_update
        BEFORE UPDATE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'Audit logs are strictly immutable. UPDATE operations are forbidden.');
        END;
        """)
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_logs_delete
        BEFORE DELETE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'Audit logs are strictly immutable. DELETE operations are forbidden.');
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_update_delete ON audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_logs_modification();")
    elif dialect_name == 'sqlite':
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_update;")
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_delete;")

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_audit_logs_request_id'))
        batch_op.drop_column('ip_address')
        batch_op.drop_column('request_id')
