"""Opt-in AP1 descriptor; NULL retains legacy campaigns and authorities."""
from alembic import op
import sqlalchemy as sa

revision = 'z34_ap1_profile'
down_revision = 'y33y6t7u8v9w'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('campaigns', sa.Column('world_profile', sa.String(), nullable=True))
    op.add_column('campaigns', sa.Column('playable_state', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('campaigns', 'playable_state')
    op.drop_column('campaigns', 'world_profile')
