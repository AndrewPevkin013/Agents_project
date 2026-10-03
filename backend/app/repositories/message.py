from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        message: Message,
    ) -> Message:
        self._session.add(message)

        await self._session.flush()

        return message

    async def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(stmt)

        return list(result.scalars().all())