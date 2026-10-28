"""Optional TP1 site and route contracts. No campaign conversion."""
from alembic import op
import sqlalchemy as sa

revision = 'z35_genesis_territory'
down_revision = 'z34_ap1_profile'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('locations', sa.Column('genesis_site', sa.JSON(), nullable=True))
    op.add_column('location_connections', sa.Column('spatial_contract', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('location_connections', 'spatial_contract')
    op.drop_column('locations', 'genesis_site')
