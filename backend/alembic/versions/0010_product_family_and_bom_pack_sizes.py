"""product family and bom pack sizes

Revision ID: 0010_product_family_and_bom_pack_sizes
Revises: 0009_costing_and_overheads
Create Date: 2026-11-26 12:00:00.000000

"""
from datetime import datetime, timezone
import math
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010_product_family_and_bom_pack_sizes'
down_revision: Union[str, None] = '0009_costing_and_overheads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create product_families table
    op.create_table(
        'product_families',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('hsn_code', sa.String(length=16), nullable=False),
        sa.Column('gst_rate_bp', sa.Integer(), server_default='500', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_product_families')),
        sa.UniqueConstraint('name', name=op.f('uq_product_families_name'))
    )
    op.create_index(op.f('ix_product_families_id'), 'product_families', ['id'], unique=False)
    op.create_index(op.f('ix_product_families_name'), 'product_families', ['name'], unique=False)

    # 2. Create packaging_specs table
    op.create_table(
        'packaging_specs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('qty_base', sa.BigInteger(), server_default='1', nullable=False),
        sa.Column('per_packets', sa.Integer(), server_default='1', nullable=False),
        sa.Column('unit_for_display', sa.String(length=16), server_default='piece', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('qty_base > 0', name=op.f('ck_packaging_specs_qty_base_positive')),
        sa.CheckConstraint('per_packets > 0', name=op.f('ck_packaging_specs_per_packets_positive')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_packaging_specs_product_id_products'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_packaging_specs_item_id_items'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_packaging_specs')),
        sa.UniqueConstraint('product_id', 'item_id', name=op.f('uq_packaging_specs_product_item'))
    )
    op.create_index(op.f('ix_packaging_specs_id'), 'packaging_specs', ['id'], unique=False)
    op.create_index(op.f('ix_packaging_specs_product_id'), 'packaging_specs', ['product_id'], unique=False)
    op.create_index(op.f('ix_packaging_specs_item_id'), 'packaging_specs', ['item_id'], unique=False)

    # 3. Add columns to products
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('family_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('pack_name', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('net_weight_g', sa.Integer(), server_default='200', nullable=False))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.create_foreign_key(op.f('fk_products_family_id_product_families'), 'product_families', ['family_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(op.f('ix_products_family_id'), ['family_id'], unique=False)

    # 4. Add columns to boms
    with op.batch_alter_table('boms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('family_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('expected_output_g', sa.Integer(), server_default='40000', nullable=False))
        batch_op.alter_column('batch_output_packets', nullable=True)
        batch_op.create_foreign_key(op.f('fk_boms_family_id_product_families'), 'product_families', ['family_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(op.f('ix_boms_family_id'), ['family_id'], unique=False)

    # 5. Data Migration: migrate existing products, BOMs, and packaging lines
    now = datetime.now(timezone.utc)
    products_res = conn.execute(sa.text("SELECT id, item_id, pack_size_desc, packets_per_carton FROM products")).fetchall()
    
    for prod in products_res:
        prod_id, item_id, pack_size_desc, ppc = prod[0], prod[1], prod[2], prod[3]
        item_row = conn.execute(sa.text(f"SELECT name, hsn_code, gst_rate_bp FROM items WHERE id = {item_id}")).fetchone()
        item_name = item_row[0] if item_row else "Product"
        hsn_code = item_row[1] if item_row else "1905"
        gst_rate_bp = item_row[2] if item_row else 500

        # Family name (e.g. 'Murukku' from 'Murukku 200 g')
        family_name = item_name.split()[0] if item_name else "Murukku"

        # Check or create family
        fam_row = conn.execute(sa.text(f"SELECT id FROM product_families WHERE name = '{family_name}'")).fetchone()
        if not fam_row:
            ins_fam = conn.execute(
                sa.text(
                    "INSERT INTO product_families (name, hsn_code, gst_rate_bp, is_active, created_at, updated_at) "
                    "VALUES (:name, :hsn, :gst, :active, :created, :updated)"
                ),
                {
                    "name": family_name,
                    "hsn": hsn_code,
                    "gst": gst_rate_bp,
                    "active": True,
                    "created": now,
                    "updated": now,
                }
            )
            # Fetch generated family id
            fam_id = conn.execute(sa.text(f"SELECT id FROM product_families WHERE name = '{family_name}'")).fetchone()[0]
        else:
            fam_id = fam_row[0]

        # Update product with family_id and pack_name
        conn.execute(
            sa.text(
                "UPDATE products SET family_id = :fam_id, pack_name = :pack_name, net_weight_g = 200 WHERE id = :p_id"
            ),
            {"fam_id": fam_id, "pack_name": item_name, "p_id": prod_id}
        )

        # Move BOMs for this product to the family
        boms_res = conn.execute(
            sa.text(f"SELECT id, version, batch_output_packets FROM boms WHERE product_id = {prod_id}")
        ).fetchall()
        for bom_row in boms_res:
            bom_id, b_ver, b_pkts = bom_row[0], bom_row[1], bom_row[2]
            exp_output_g = b_pkts * 200  # expected_output_g = old batch_output_packets x net_weight_g

            conn.execute(
                sa.text(
                    "UPDATE boms SET family_id = :fam_id, expected_output_g = :exp_g WHERE id = :b_id"
                ),
                {"fam_id": fam_id, "exp_g": exp_output_g, "b_id": bom_id}
            )

            # Convert old packaging BOM lines to PackagingSpec rows
            bom_items_res = conn.execute(
                sa.text(
                    f"SELECT bi.id, bi.item_id, bi.quantity_per_batch, bi.unit_for_display, it.item_type "
                    f"FROM bom_items bi JOIN items it ON bi.item_id = it.id WHERE bi.bom_id = {bom_id}"
                )
            ).fetchall()

            for bi_row in bom_items_res:
                bi_id, bi_item_id, bi_qty, bi_unit, bi_type = bi_row[0], bi_row[1], bi_row[2], bi_row[3], bi_row[4]
                if bi_type == "PACKAGING":
                    # Convert: pouch 200 per 200 pkts -> 1 per 1; carton 10 per 200 -> 1 per 20
                    common = math.gcd(bi_qty, b_pkts)
                    if common > 0:
                        qty_base = bi_qty // common
                        per_packets = b_pkts // common
                    else:
                        qty_base = bi_qty
                        per_packets = b_pkts

                    existing_spec = conn.execute(
                        sa.text(f"SELECT id FROM packaging_specs WHERE product_id = {prod_id} AND item_id = {bi_item_id}")
                    ).fetchone()
                    if not existing_spec:
                        conn.execute(
                            sa.text(
                                "INSERT INTO packaging_specs (product_id, item_id, qty_base, per_packets, unit_for_display, created_at, updated_at) "
                                "VALUES (:pid, :iid, :qb, :pp, :unit, :created, :updated)"
                            ),
                            {
                                "pid": prod_id,
                                "iid": bi_item_id,
                                "qb": qty_base,
                                "pp": per_packets,
                                "unit": bi_unit or "piece",
                                "created": now,
                                "updated": now,
                            }
                        )
                    # Remove packaging line from BOMItem
                    conn.execute(sa.text(f"DELETE FROM bom_items WHERE id = {bi_id}"))

    # 6. Apply constraints and clean up
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('family_id', nullable=False)
        batch_op.alter_column('pack_name', nullable=False)

    with op.batch_alter_table('boms', schema=None) as batch_op:
        batch_op.alter_column('family_id', nullable=False)
        try:
            batch_op.drop_constraint('uq_boms_product_version', type_='unique')
        except Exception:
            pass
        batch_op.create_unique_constraint(op.f('uq_boms_family_version'), ['family_id', 'version'])


def downgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    # 1. Restore product_id in boms and transfer packaging lines back
    products_res = conn.execute(sa.text("SELECT id, family_id, net_weight_g FROM products")).fetchall()
    prod_family_map = {row[1]: (row[0], row[2]) for row in products_res}

    # For each family, map boms back to product_id
    for fam_id, (prod_id, net_weight) in prod_family_map.items():
        conn.execute(
            sa.text(f"UPDATE boms SET product_id = {prod_id} WHERE family_id = {fam_id}")
        )
        # Restore packaging lines from packaging_specs back to bom_items
        specs = conn.execute(sa.text(f"SELECT item_id, qty_base, per_packets, unit_for_display FROM packaging_specs WHERE product_id = {prod_id}")).fetchall()
        boms_for_prod = conn.execute(sa.text(f"SELECT id, expected_output_g FROM boms WHERE product_id = {prod_id}")).fetchall()
        for b in boms_for_prod:
            bom_id, exp_g = b[0], b[1]
            exp_pkts = exp_g // (net_weight or 200)
            for s in specs:
                item_id, qb, pp, unit = s[0], s[1], s[2], s[3]
                planned_qty = (exp_pkts * qb) // pp
                conn.execute(
                    sa.text(
                        "INSERT INTO bom_items (bom_id, item_id, quantity_per_batch, unit_for_display, created_at, updated_at) "
                        "VALUES (:bid, :iid, :qty, :unit, :created, :updated)"
                    ),
                    {"bid": bom_id, "iid": item_id, "qty": planned_qty, "unit": unit, "created": now, "updated": now}
                )

    with op.batch_alter_table('boms', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('uq_boms_family_version', type_='unique')
        except Exception:
            pass
        batch_op.drop_column('expected_output_g')
        batch_op.drop_column('family_id')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('net_weight_g')
        batch_op.drop_column('pack_name')
        batch_op.drop_column('family_id')

    op.drop_table('packaging_specs')
    op.drop_table('product_families')
