"""empty message

Revision ID: cd7bf0db6762
Revises: 
Create Date: 2024-09-08 14:15:52.584194

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'cd7bf0db6762'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('background_job_execution',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('started', sa.DateTime(), nullable=False),
    sa.Column('completed', sa.DateTime(), nullable=False),
    sa.Column('successful_queries', sa.Integer(), nullable=False),
    sa.Column('failed_queries', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('image_to_scrape',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('endpoint', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('image', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tag', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint', 'image', 'tag', name='endpoint_image_tag')
    )
    with op.batch_alter_table('image_to_scrape', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_image_to_scrape_endpoint'), ['endpoint'], unique=False)
        batch_op.create_index(batch_op.f('ix_image_to_scrape_image'), ['image'], unique=False)
        batch_op.create_index(batch_op.f('ix_image_to_scrape_tag'), ['tag'], unique=False)

    op.create_table('image_update',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scraped_at', sa.DateTime(), nullable=False),
    sa.Column('image_id', sa.Integer(), nullable=False),
    sa.Column('digest', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.ForeignKeyConstraint(['image_id'], ['image_to_scrape.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('image_update', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_image_update_image_id'), ['image_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('image_update', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_image_update_image_id'))

    op.drop_table('image_update')
    with op.batch_alter_table('image_to_scrape', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_image_to_scrape_tag'))
        batch_op.drop_index(batch_op.f('ix_image_to_scrape_image'))
        batch_op.drop_index(batch_op.f('ix_image_to_scrape_endpoint'))

    op.drop_table('image_to_scrape')
    op.drop_table('background_job_execution')
    # ### end Alembic commands ###
