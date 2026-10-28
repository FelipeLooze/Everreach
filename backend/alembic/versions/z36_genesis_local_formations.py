"""WGS1 persisted local natural formations and finite instance water."""
from alembic import op
import sqlalchemy as sa

revision = 'z36_genesis_local_formations'
down_revision = 'z35_genesis_territory'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'genesis_natural_formations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('location_id', sa.String(), sa.ForeignKey('locations.id'), nullable=False, unique=True),
        sa.Column('stable_key', sa.String(), nullable=False),
        sa.Column('archetype_id', sa.String(), nullable=False),
        sa.Column('generator_version', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.UniqueConstraint('campaign_id','stable_key',name='uq_natural_formation_key'),
    )
    op.create_index('ix_natural_formation_campaign','genesis_natural_formations',['campaign_id'])
    op.create_table(
        'genesis_local_water_bodies',
        sa.Column('formation_id', sa.String(), sa.ForeignKey('genesis_natural_formations.id'), primary_key=True),
        sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('capacity_litres', sa.Integer(), nullable=False),
        sa.Column('stored_litres', sa.Integer(), nullable=False),
        sa.Column('source_origin', sa.String(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('capacity_litres > 0 AND stored_litres >= 0 AND stored_litres <= capacity_litres',
                           name='ck_local_water_bounds'),
    )
    op.create_index('ix_genesis_local_water_bodies_campaign_id','genesis_local_water_bodies',['campaign_id'])


def downgrade():
    op.drop_index('ix_genesis_local_water_bodies_campaign_id',table_name='genesis_local_water_bodies')
    op.drop_table('genesis_local_water_bodies')
    op.drop_index('ix_natural_formation_campaign',table_name='genesis_natural_formations')
    op.drop_table('genesis_natural_formations')
