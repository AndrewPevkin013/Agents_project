from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AccessDeniedError
from app.authz.service import AuthorizationService
from app.db.models.workspace_member import WorkspaceRole


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def make_service(role: WorkspaceRole | None) -> AuthorizationService:
    repository = AsyncMock()

    if role is None:
        repository.get_membership.return_value = None
    else:
        repository.get_membership.return_value = SimpleNamespace(role=role)

    return AuthorizationService(
        workspace_member_repository=repository,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
        WorkspaceRole.VIEWER,
    ],
)
async def test_workspace_read_is_allowed_for_members(
    role: WorkspaceRole,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    service = make_service(role)

    await service.require_workspace_read(
        user_id=user_id,
        workspace_id=workspace_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    ],
)
async def test_workspace_write_is_allowed_for_writers(
    role: WorkspaceRole,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    service = make_service(role)

    await service.require_workspace_write(
        user_id=user_id,
        workspace_id=workspace_id,
    )


@pytest.mark.asyncio
async def test_workspace_write_is_denied_for_viewer(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    service = make_service(WorkspaceRole.VIEWER)

    with pytest.raises(AccessDeniedError):
        await service.require_workspace_write(
            user_id=user_id,
            workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_workspace_read_is_denied_for_non_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    service = make_service(None)

    with pytest.raises(AccessDeniedError):
        await service.require_workspace_read(
            user_id=user_id,
            workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_workspace_write_is_denied_for_non_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    service = make_service(None)

    with pytest.raises(AccessDeniedError):
        await service.require_workspace_write(
            user_id=user_id,
            workspace_id=workspace_id,
        )