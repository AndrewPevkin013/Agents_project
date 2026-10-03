import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.workspace import Workspace
    from app.db.models.conversation_document import ConversationDocument


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

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

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    original_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        unique=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        index=True,
    )

    workspace: Mapped["Workspace"] = relationship(
        back_populates="documents",
    )

    uploader: Mapped["User"] = relationship(
        back_populates="uploaded_documents",
    )

    conversation_links: Mapped[list["ConversationDocument"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )