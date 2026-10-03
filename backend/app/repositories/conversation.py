from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        conversation_id: uuid.UUID,
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
        )

        result = await self._session.execute(stmt)

        return result.scalar_one_or_none()

    async def create(
        self,
        conversation: Conversation,
    ) -> Conversation:
        self._session.add(conversation)

        await self._session.flush()

        return conversation

    async def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.archived_at.is_(None),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(stmt)

        return list(result.scalars().all())