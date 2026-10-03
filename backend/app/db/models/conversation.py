import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.message import Message
    from app.db.models.user import User
    from app.db.models.workspace import Workspace
    from app.db.models.conversation_document import ConversationDocument
    from app.db.models.agent import Agent

class ConversationParticipantType(str, enum.Enum):
    HANDLER = "handler"
    AGENT = "agent"

class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            """
            (active_participant_type = 'handler' AND active_agent_id IS NULL)
            OR
            (active_participant_type = 'agent' AND active_agent_id IS NOT NULL)
            """,
            name="ck_conversations_active_participant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped["Workspace"] = relationship(
        back_populates="conversations",
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_conversations",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
    )

    document_links: Mapped[list["ConversationDocument"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    active_participant_type: Mapped[ConversationParticipantType] = mapped_column(
        Enum(
            ConversationParticipantType,
            name="conversation_participant_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=ConversationParticipantType.HANDLER,
    )


    active_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    active_agent: Mapped["Agent | None"] = relationship(
        back_populates="active_conversations",
    )