import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.user import User
    from app.db.models.agent import Agent


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class MessageResponderType(str, enum.Enum):
    HANDLER = "handler"
    AGENT = "agent"

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint(
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
            name="ck_messages_author",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )

    author: Mapped["User | None"] = relationship(
        back_populates="messages",
    )

    responder_type: Mapped[MessageResponderType | None] = mapped_column(
        Enum(
            MessageResponderType,
            name="message_responder_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=True,
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    agent: Mapped["Agent | None"] = relationship(
        back_populates="messages",
    )