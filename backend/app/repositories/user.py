from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_identity_subject(self, identity_subject: str) -> User | None:
        stmt = select(User).where(User.identity_subject == identity_subject)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()