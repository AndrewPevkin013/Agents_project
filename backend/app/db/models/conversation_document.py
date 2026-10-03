from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import utcnow

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.document import Document
    from app.db.models.user import User


class ConversationDocument(Base):
    __tablename__ = "conversation_documents"

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "document_id",
            name="uq_conversation_documents_conversation_document",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attached_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="document_links",
    )

    document: Mapped["Document"] = relationship(
        back_populates="conversation_links",
    )

    attached_by_user: Mapped["User"] = relationship(
        back_populates="attached_documents",
    )