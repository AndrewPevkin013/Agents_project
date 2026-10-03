from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workspace_member import WorkspaceMember


class WorkspaceMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_membership(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> WorkspaceMember | None:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )

        result = await self._session.execute(stmt)

        return result.scalar_one_or_none()