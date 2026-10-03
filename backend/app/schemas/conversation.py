from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.conversation import ConversationParticipantType


class ConversationCreate(BaseModel):
    workspace_id: uuid.UUID

    title: str = Field(
        min_length=1,
        max_length=255,
    )


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by: uuid.UUID

    title: str
    archived_at: datetime | None

    active_participant_type: ConversationParticipantType
    active_agent_id: uuid.UUID | None

    created_at: datetime
    updated_at: datetime