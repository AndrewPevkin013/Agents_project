from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.message import (
    MessageResponderType,
    MessageRole,
)


class MessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
    )


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID

    author_user_id: uuid.UUID | None

    role: MessageRole
    content: str

    responder_type: MessageResponderType | None
    agent_id: uuid.UUID | None

    created_at: datetime