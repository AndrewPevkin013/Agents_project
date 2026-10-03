import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.workspace import Workspace
    from app.db.models.conversation import Conversation
    from app.db.models.message import Message


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_agents_workspace_name",
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

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    workspace: Mapped["Workspace"] = relationship(
        back_populates="agents",
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_agents",
    )

    active_conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="active_agent",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="agent",
    )