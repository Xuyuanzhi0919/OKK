"""add ai config table

Revision ID: 006
Revises: 005
Create Date: 2026-02-04 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=True, server_default='deepseek'),
        sa.Column('api_key', sa.String(length=255), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True, server_default='deepseek-chat'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_configs_id'), 'ai_configs', ['id'])
    op.create_index(op.f('ix_ai_configs_user_id'), 'ai_configs', ['user_id'])


def downgrade():
    op.drop_index(op.f('ix_ai_configs_user_id'), table_name='ai_configs')
    op.drop_index(op.f('ix_ai_configs_id'), table_name='ai_configs')
    op.drop_table('ai_configs')
