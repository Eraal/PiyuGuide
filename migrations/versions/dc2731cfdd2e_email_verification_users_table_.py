"""email verification: users table + verification_tokens

Revision ID: dc2731cfdd2e
Revises: 
Create Date: 2025-11-01 03:12:22.793483

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dc2731cfdd2e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Minimal, safe migration: create verification_tokens + add email verification columns on users
    op.create_table(
        'verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(length=50), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('max_attempts', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_verification_tokens_created_at', 'verification_tokens', ['created_at'], unique=False)
    op.create_index('ix_verification_tokens_expires_at', 'verification_tokens', ['expires_at'], unique=False)
    op.create_index('ix_verification_tokens_purpose', 'verification_tokens', ['purpose'], unique=False)
    op.create_index('ix_verification_tokens_token_hash', 'verification_tokens', ['token_hash'], unique=True)
    op.create_index('ix_verification_tokens_user_id', 'verification_tokens', ['user_id'], unique=False)

    # Add user columns (nullable to avoid backfill issues); we can enforce defaults at app level
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('email_verification_sent_at', sa.DateTime(), nullable=True))
    # Helpful index for lookups
    op.create_index('ix_users_email_verified', 'users', ['email_verified'], unique=False)


def downgrade():
    # Revert only what we added above
    op.drop_index('ix_users_email_verified', table_name='users')
    op.drop_column('users', 'email_verification_sent_at')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'email_verified')

    op.drop_index('ix_verification_tokens_user_id', table_name='verification_tokens')
    op.drop_index('ix_verification_tokens_token_hash', table_name='verification_tokens')
    op.drop_index('ix_verification_tokens_purpose', table_name='verification_tokens')
    op.drop_index('ix_verification_tokens_expires_at', table_name='verification_tokens')
    op.drop_index('ix_verification_tokens_created_at', table_name='verification_tokens')
    op.drop_table('verification_tokens')
