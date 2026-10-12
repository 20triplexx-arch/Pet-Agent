"""Conversation evidence summaries and model turn audit; preserve existing data."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_deep_chat"
down_revision = "20261011_products"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversation", sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table("modelattempt", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_modelattempt_user_id", "modelattempt", ["user_id"])
    op.create_index("ix_modelattempt_created_at", "modelattempt", ["created_at"])


def downgrade():
    op.drop_table("modelattempt")
    op.drop_column("conversation", "summary_json")
