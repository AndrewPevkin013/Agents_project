import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.organization import Organization
    from app.db.models.user import User
    from app.db.models.workspace_member import WorkspaceMember
    from app.db.models.conversation import Conversation
    from app.db.models.document import Document
    from app.db.models.agent import Agent


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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


    organization: Mapped["Organization"] = relationship(
        back_populates="workspaces",
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_workspaces",
    )

    memberships: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="workspace",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="workspace",
    )

    agents: Mapped[list["Agent"]] = relationship(
        back_populates="workspace",
    )