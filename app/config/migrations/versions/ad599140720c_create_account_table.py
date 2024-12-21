"""create account table

Revision ID: ad599140720c
Revises:
Create Date: 2024-12-16 02:17:10.241220

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ad599140720c"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
    op.create_table(
        "task",
        sa.Column("id", sa.Text(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("submit", sa.BOOLEAN(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_created_time"), "task", ["created_time"], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_task_created_time"), table_name="task")
    op.drop_table("task")
    # ### end Alembic commands ###