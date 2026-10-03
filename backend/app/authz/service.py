from __future__ import annotations

import uuid

from app.core.exceptions import AccessDeniedError
from app.db.models.workspace_member import WorkspaceRole
from app.repositories.workspace_member import WorkspaceMemberRepository


class AuthorizationService:
    _READ_ROLES = frozenset(
        {
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
            WorkspaceRole.MEMBER,
            WorkspaceRole.VIEWER,
        }
    )

    _WRITE_ROLES = frozenset(
        {
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
            WorkspaceRole.MEMBER,
        }
    )

    def __init__(
        self,
        workspace_member_repository: WorkspaceMemberRepository,
    ) -> None:
        self._workspace_members = workspace_member_repository

    async def require_workspace_read(
        self,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        membership = await self._workspace_members.get_membership(
            workspace_id=workspace_id,
            user_id=user_id,
        )

        if membership is None or membership.role not in self._READ_ROLES:
            raise AccessDeniedError(
                "User does not have read access to this workspace"
            )

    async def require_workspace_write(
        self,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        membership = await self._workspace_members.get_membership(
            workspace_id=workspace_id,
            user_id=user_id,
        )

        if membership is None or membership.role not in self._WRITE_ROLES:
            raise AccessDeniedError(
                "User does not have write access to this workspace"
            )