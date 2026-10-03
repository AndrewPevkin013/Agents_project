import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from app.db.models.workspace import Workspace
    from app.db.models.workspace_member import WorkspaceMember
    from app.db.models.conversation import Conversation
    from app.db.models.message import Message
    from app.db.models.document import Document
    from app.db.models.agent import Agent
    from app.db.models.conversation_document import ConversationDocument


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    identity_subject: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


    created_workspaces: Mapped[list["Workspace"]] = relationship(
        back_populates="creator",
    )

    workspace_memberships: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="user",
    )

    created_conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="creator",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="author",
    )

    uploaded_documents: Mapped[list["Document"]] = relationship(
        back_populates="uploader",
    )

    created_agents: Mapped[list["Agent"]] = relationship(
        back_populates="creator",
    )

    attached_documents: Mapped[list["ConversationDocument"]] = relationship(
        back_populates="attached_by_user",
    )