"""Nutrition profiles and durable external API counters; preserve existing data."""
from alembic import op
import sqlalchemy as sa

revision = "20261010_nutrition"
down_revision = "385c23b07d08"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("careplan", sa.Column("provenance", sa.JSON(), nullable=True))
    op.create_table(
        "petnutritionprofile",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("pet_id", sa.String(), sa.ForeignKey("pet.id"), nullable=False, unique=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active_plan_id", sa.String(), sa.ForeignKey("careplan.id"), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_petnutritionprofile_user_id", "petnutritionprofile", ["user_id"])
    op.create_table(
        "externalapiusage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.UniqueConstraint("provider", "period"),
    )


def downgrade():
    op.drop_table("externalapiusage")
    op.drop_table("petnutritionprofile")
    op.drop_column("careplan", "provenance")
