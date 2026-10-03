"""add conversation context

Revision ID: 4d63e0d400b2
Revises: fff28bc17f0f
Create Date: 2026-10-03 14:28:48.223780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4d63e0d400b2'
down_revision: Union[str, Sequence[str], None] = 'fff28bc17f0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add conversation context and message responder attribution."""

    bind = op.get_bind()

    conversation_participant_type = postgresql.ENUM(
        "handler",
        "agent",
        name="conversation_participant_type",
    )
    message_responder_type = postgresql.ENUM(
        "handler",
        "agent",
        name="message_responder_type",
    )

    conversation_participant_type.create(bind, checkfirst=True)
    message_responder_type.create(bind, checkfirst=True)

    # Conversation documents
    op.create_table(
        "conversation_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("attached_by", sa.UUID(), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attached_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "document_id",
            name="uq_conversation_documents_conversation_document",
        ),
    )

    op.create_index(
        op.f("ix_conversation_documents_attached_by"),
        "conversation_documents",
        ["attached_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_documents_conversation_id"),
        "conversation_documents",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_documents_document_id"),
        "conversation_documents",
        ["document_id"],
        unique=False,
    )

    # Conversation active participant

    # Nullable first so the migration also works when conversations
    # already exist.
    op.add_column(
        "conversations",
        sa.Column(
            "active_participant_type",
            postgresql.ENUM(
                "handler",
                "agent",
                name="conversation_participant_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "conversations",
        sa.Column(
            "active_agent_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    # Existing conversations become Handler conversations.
    op.execute(
        """
        UPDATE conversations
        SET active_participant_type = 'handler'
        WHERE active_participant_type IS NULL
        """
    )

    op.alter_column(
        "conversations",
        "active_participant_type",
        nullable=False,
    )

    op.create_index(
        op.f("ix_conversations_active_agent_id"),
        "conversations",
        ["active_agent_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_conversations_active_agent_id_agents",
        "conversations",
        "agents",
        ["active_agent_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_check_constraint(
        "ck_conversations_active_participant",
        "conversations",
        """
        (active_participant_type = 'handler' AND active_agent_id IS NULL)
        OR
        (active_participant_type = 'agent' AND active_agent_id IS NOT NULL)
        """,
    )

    # Message responder attribution

    op.add_column(
        "messages",
        sa.Column(
            "responder_type",
            postgresql.ENUM(
                "handler",
                "agent",
                name="message_responder_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "agent_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    # Legacy assistant messages were produced before explicit
    # agent attribution existed, so classify them as Handler responses.
    op.execute(
        """
        UPDATE messages
        SET responder_type = 'handler'
        WHERE role = 'assistant'
          AND responder_type IS NULL
        """
    )

    op.create_index(
        op.f("ix_messages_agent_id"),
        "messages",
        ["agent_id"],
        unique=False,
    )

    # Replace the old SET NULL FK with RESTRICT.
    op.drop_constraint(
        op.f("messages_author_user_id_fkey"),
        "messages",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_messages_author_user_id_users",
        "messages",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_messages_agent_id_agents",
        "messages",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_check_constraint(
        "ck_messages_author",
        "messages",
        """
        (role = 'user'
            AND author_user_id IS NOT NULL
            AND responder_type IS NULL
            AND agent_id IS NULL)
        OR
        (role = 'assistant'
            AND author_user_id IS NULL
            AND responder_type = 'handler'
            AND agent_id IS NULL)
        OR
        (role = 'assistant'
            AND author_user_id IS NULL
            AND responder_type = 'agent'
            AND agent_id IS NOT NULL)
        OR
        (role = 'system'
            AND author_user_id IS NULL
            AND responder_type IS NULL
            AND agent_id IS NULL)
        """,
    )


def downgrade() -> None:
    """Remove conversation context and message responder attribution."""

    # Messages

    op.drop_constraint(
        "ck_messages_author",
        "messages",
        type_="check",
    )

    op.drop_constraint(
        "fk_messages_agent_id_agents",
        "messages",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_messages_author_user_id_users",
        "messages",
        type_="foreignkey",
    )

    op.create_foreign_key(
        op.f("messages_author_user_id_fkey"),
        "messages",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index(
        op.f("ix_messages_agent_id"),
        table_name="messages",
    )

    op.drop_column("messages", "agent_id")
    op.drop_column("messages", "responder_type")

    # Conversations

    op.drop_constraint(
        "ck_conversations_active_participant",
        "conversations",
        type_="check",
    )

    op.drop_constraint(
        "fk_conversations_active_agent_id_agents",
        "conversations",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_conversations_active_agent_id"),
        table_name="conversations",
    )

    op.drop_column("conversations", "active_agent_id")
    op.drop_column("conversations", "active_participant_type")

    # Conversation documents

    op.drop_index(
        op.f("ix_conversation_documents_document_id"),
        table_name="conversation_documents",
    )
    op.drop_index(
        op.f("ix_conversation_documents_conversation_id"),
        table_name="conversation_documents",
    )
    op.drop_index(
        op.f("ix_conversation_documents_attached_by"),
        table_name="conversation_documents",
    )

    op.drop_table("conversation_documents")

    # PostgreSQL enum types survive column deletion unless explicitly
    # removed.
    postgresql.ENUM(
        name="message_responder_type",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )

    postgresql.ENUM(
        name="conversation_participant_type",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )