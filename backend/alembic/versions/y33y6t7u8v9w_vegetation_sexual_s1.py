"""Explicit S1 extension of L2. Existing campaigns stay unchanged."""
from alembic import op
import sqlalchemy as sa
revision='y33y6t7u8v9w'
down_revision='x32x5s6t7u8v'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('genesis_vegetation_sexual_policy',
        sa.Column('campaign_id',sa.String(),sa.ForeignKey('genesis_vegetation_renewal.campaign_id'),primary_key=True),
        sa.Column('signature',sa.String(),nullable=False),sa.Column('descriptor',sa.JSON(),nullable=False),
        sa.Column('descriptor_checksum',sa.String(),nullable=False))


def downgrade():op.drop_table('genesis_vegetation_sexual_policy')
