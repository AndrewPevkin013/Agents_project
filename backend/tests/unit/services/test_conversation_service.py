from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AccessDeniedError, NotFoundError
from app.db.models.conversation import Conversation
from app.db.models.message import MessageRole
from app.services.conversation import ConversationService


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def conversation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def dependencies():
    session = AsyncMock()
    conversation_repository = AsyncMock()
    message_repository = AsyncMock()
    authorization_service = AsyncMock()

    return (
        session,
        conversation_repository,
        message_repository,
        authorization_service,
    )


@pytest.fixture
def service(dependencies) -> ConversationService:
    (
        session,
        conversation_repository,
        message_repository,
        authorization_service,
    ) = dependencies

    return ConversationService(
        session=session,
        conversation_repository=conversation_repository,
        message_repository=message_repository,
        authorization_service=authorization_service,
    )


@pytest.mark.asyncio
async def test_create_conversation(
    service,
    dependencies,
    workspace_id,
    user_id,
):
    session, conversations, _, authorization = dependencies

    result = await service.create_conversation(
        workspace_id=workspace_id,
        user_id=user_id,
        title="Architecture discussion",
    )

    authorization.require_workspace_write.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
    )

    conversations.create.assert_awaited_once()

    created = conversations.create.await_args.args[0]

    assert created.workspace_id == workspace_id
    assert created.created_by == user_id
    assert created.title == "Architecture discussion"

    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)

    assert result is created


@pytest.mark.asyncio
async def test_create_conversation_does_not_write_when_access_denied(
    service,
    dependencies,
    workspace_id,
    user_id,
):
    session, conversations, _, authorization = dependencies

    authorization.require_workspace_write.side_effect = AccessDeniedError(
        "Access denied"
    )

    with pytest.raises(AccessDeniedError):
        await service.create_conversation(
            workspace_id=workspace_id,
            user_id=user_id,
            title="Forbidden conversation",
        )

    conversations.create.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_conversation(
    service,
    dependencies,
    workspace_id,
    conversation_id,
    user_id,
):
    _, conversations, _, authorization = dependencies

    conversation = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Test conversation",
    )

    conversations.get_by_id.return_value = conversation

    result = await service.get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    conversations.get_by_id.assert_awaited_once_with(conversation_id)

    authorization.require_workspace_read.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
    )

    assert result is conversation


@pytest.mark.asyncio
async def test_get_conversation_raises_not_found(
    service,
    dependencies,
    conversation_id,
    user_id,
):
    _, conversations, _, authorization = dependencies

    conversations.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await service.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

    authorization.require_workspace_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_conversations(
    service,
    dependencies,
    workspace_id,
    user_id,
):
    _, conversations, _, authorization = dependencies

    expected = []
    conversations.list_by_workspace.return_value = expected

    result = await service.list_conversations(
        workspace_id=workspace_id,
        user_id=user_id,
        limit=25,
        offset=10,
    )

    authorization.require_workspace_read.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
    )

    conversations.list_by_workspace.assert_awaited_once_with(
        workspace_id,
        limit=25,
        offset=10,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_list_conversations_does_not_query_when_access_denied(
    service,
    dependencies,
    workspace_id,
    user_id,
):
    _, conversations, _, authorization = dependencies

    authorization.require_workspace_read.side_effect = AccessDeniedError(
        "Access denied"
    )

    with pytest.raises(AccessDeniedError):
        await service.list_conversations(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    conversations.list_by_workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_user_message(
    service,
    dependencies,
    workspace_id,
    conversation_id,
    user_id,
):
    session, conversations, messages, authorization = dependencies

    conversation = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Test conversation",
    )

    conversations.get_by_id.return_value = conversation

    result = await service.add_user_message(
        conversation_id=conversation_id,
        user_id=user_id,
        content="Hello",
    )

    authorization.require_workspace_write.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
    )

    messages.create.assert_awaited_once()

    created = messages.create.await_args.args[0]

    assert created.conversation_id == conversation_id
    assert created.author_user_id == user_id
    assert created.role == MessageRole.USER
    assert created.content == "Hello"
    assert created.responder_type is None
    assert created.agent_id is None

    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)

    assert result is created


@pytest.mark.asyncio
async def test_add_user_message_raises_not_found(
    service,
    dependencies,
    conversation_id,
    user_id,
):
    session, conversations, messages, authorization = dependencies

    conversations.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await service.add_user_message(
            conversation_id=conversation_id,
            user_id=user_id,
            content="Hello",
        )

    authorization.require_workspace_write.assert_not_awaited()
    messages.create.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_user_message_does_not_write_when_access_denied(
    service,
    dependencies,
    workspace_id,
    conversation_id,
    user_id,
):
    session, conversations, messages, authorization = dependencies

    conversation = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Test conversation",
    )

    conversations.get_by_id.return_value = conversation

    authorization.require_workspace_write.side_effect = AccessDeniedError(
        "Access denied"
    )

    with pytest.raises(AccessDeniedError):
        await service.add_user_message(
            conversation_id=conversation_id,
            user_id=user_id,
            content="Forbidden",
        )

    messages.create.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_messages(
    service,
    dependencies,
    workspace_id,
    conversation_id,
    user_id,
):
    _, conversations, messages, authorization = dependencies

    conversation = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Test conversation",
    )

    conversations.get_by_id.return_value = conversation

    expected = []
    messages.list_by_conversation.return_value = expected

    result = await service.list_messages(
        conversation_id=conversation_id,
        user_id=user_id,
        limit=40,
        offset=5,
    )

    authorization.require_workspace_read.assert_awaited_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
    )

    messages.list_by_conversation.assert_awaited_once_with(
        conversation_id,
        limit=40,
        offset=5,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_list_messages_raises_not_found(
    service,
    dependencies,
    conversation_id,
    user_id,
):
    _, conversations, messages, authorization = dependencies

    conversations.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await service.list_messages(
            conversation_id=conversation_id,
            user_id=user_id,
        )

    authorization.require_workspace_read.assert_not_awaited()
    messages.list_by_conversation.assert_not_awaited()