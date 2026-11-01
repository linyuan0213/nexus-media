"""include media type in external ref key

Revision ID: 1b0e0cf3dccc
Revises: b8e53a78e03e
Create Date: 2026-11-01 13:09:08.497983

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "1b0e0cf3dccc"
down_revision = "b8e53a78e03e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    refs = sa.table(
        "MEDIA_EXTERNAL_REF",
        sa.column("ID", sa.Integer),
        sa.column("IDENTITY_ID", sa.String),
        sa.column("MEDIA_TYPE", sa.String),
    )
    identities = sa.table(
        "MEDIA_IDENTITY",
        sa.column("IDENTITY_ID", sa.String),
        sa.column("MEDIA_TYPE", sa.String),
    )
    rows = bind.execute(
        sa.select(refs.c.ID, identities.c.MEDIA_TYPE)
        .select_from(refs.join(identities, refs.c.IDENTITY_ID == identities.c.IDENTITY_ID))
        .where(refs.c.MEDIA_TYPE.is_(None), identities.c.MEDIA_TYPE.is_not(None))
    ).fetchall()
    for ref_id, media_type in rows:
        bind.execute(refs.update().where(refs.c.ID == ref_id).values(MEDIA_TYPE=media_type))

    with op.batch_alter_table("MEDIA_EXTERNAL_REF") as batch_op:
        batch_op.drop_constraint("UQ_MEDIA_EXTERNAL_REF", type_="unique")
        batch_op.create_unique_constraint(
            "UQ_MEDIA_EXTERNAL_REF",
            ["PROVIDER", "EXTERNAL_ID", "SCOPE", "MEDIA_TYPE"],
        )


def downgrade() -> None:
    with op.batch_alter_table("MEDIA_EXTERNAL_REF") as batch_op:
        batch_op.drop_constraint("UQ_MEDIA_EXTERNAL_REF", type_="unique")
        batch_op.create_unique_constraint(
            "UQ_MEDIA_EXTERNAL_REF",
            ["PROVIDER", "EXTERNAL_ID", "SCOPE"],
        )
