"""Explicit recurring L2 authority, no activation or legacy rewrite."""
from alembic import op
import sqlalchemy as sa
revision='x32x5s6t7u8v'
down_revision='w31w4r5s6t7u'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('genesis_vegetation_renewal',
        sa.Column('campaign_id',sa.String(),sa.ForeignKey('genesis_vegetation_life.campaign_id'),primary_key=True),
        sa.Column('signature',sa.String(),nullable=False),sa.Column('descriptor',sa.JSON(),nullable=False),
        sa.Column('descriptor_checksum',sa.String(),nullable=False),sa.Column('last_minute',sa.Integer(),nullable=False),
        sa.Column('state_checksum',sa.String(),nullable=False))
    op.create_table('genesis_renewing_populations',
        sa.Column('campaign_id',sa.String(),sa.ForeignKey('genesis_vegetation_renewal.campaign_id'),primary_key=True),
        sa.Column('population_id',sa.String(),primary_key=True),sa.Column('community_id',sa.String(),nullable=False),
        sa.Column('species_id',sa.String(),nullable=False),sa.Column('data',sa.JSON(),nullable=False),sa.Column('data_checksum',sa.String(),nullable=False))
    op.create_index('ix_genesis_renewing_populations_community_id','genesis_renewing_populations',['community_id'])


def downgrade():
    op.drop_table('genesis_renewing_populations');op.drop_table('genesis_vegetation_renewal')
