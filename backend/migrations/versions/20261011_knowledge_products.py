"""Breed taxonomy, multi-source knowledge and private assessments; retain existing data."""
from alembic import op
import sqlalchemy as sa

revision = "20261011_products"
down_revision = "20261010_nutrition"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("breed",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("species", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("article_id", sa.String(), nullable=False))
    op.create_index("ix_breed_species", "breed", ["species"])
    # SQLite cannot add a FK with ALTER TABLE. Inline REFERENCES needs no rebuild
    # and works on both SQLite and PostgreSQL, including offline compilation.
    if op.get_context().dialect.name == "sqlite":
        op.execute("ALTER TABLE pet ADD COLUMN breed_id VARCHAR REFERENCES breed(id)")
    else:
        op.add_column("pet", sa.Column("breed_id", sa.String(), sa.ForeignKey("breed.id", name="fk_pet_breed"), nullable=True))
    op.create_index("ix_pet_breed_id", "pet", ["breed_id"])
    op.add_column("knowledgearticle", sa.Column("content_kind", sa.String(), nullable=False, server_default="care"))
    op.add_column("knowledgearticle", sa.Column("breed_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("knowledgearticle", sa.Column("references", sa.JSON(), nullable=False, server_default="[]"))
    op.create_index("ix_knowledgearticle_content_kind", "knowledgearticle", ["content_kind"])
    op.create_table("productassessment",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("pet_id", sa.String(), sa.ForeignKey("pet.id"), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_productassessment_user_id", "productassessment", ["user_id"])
    op.create_index("ix_productassessment_pet_id", "productassessment", ["pet_id"])


def downgrade():
    op.drop_table("productassessment")
    op.drop_index("ix_knowledgearticle_content_kind", "knowledgearticle")
    for name in ("references", "breed_ids", "content_kind"):
        op.drop_column("knowledgearticle", name)
    op.drop_index("ix_pet_breed_id", "pet")
    if op.get_context().dialect.name != "sqlite":
        op.drop_constraint("fk_pet_breed", "pet", type_="foreignkey")
    op.drop_column("pet", "breed_id")
    op.drop_table("breed")
