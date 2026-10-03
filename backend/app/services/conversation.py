from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.conversation import Conversation
from app.db.models.message import Message, MessageRole
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.authz.service import AuthorizationService


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        authorization_service: AuthorizationService,
    ) -> None:
        self._session = session
        self._conversations = conversation_repository
        self._messages = message_repository
        self._authorization = authorization_service

    async def create_conversation(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
    ) -> Conversation:
        await self._authorization.require_workspace_write(
            user_id=user_id,
            workspace_id=workspace_id,
        )

        conversation = Conversation(
            workspace_id=workspace_id,
            created_by=user_id,
            title=title,
        )

        await self._conversations.create(conversation)

        await self._session.commit()
        await self._session.refresh(conversation)

        return conversation

    async def get_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Conversation:
        conversation = await self._conversations.get_by_id(conversation_id)

        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} was not found")

        await self._authorization.require_workspace_read(
            user_id=user_id,
            workspace_id=conversation.workspace_id,
        )

        return conversation

    async def list_conversations(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        await self._authorization.require_workspace_read(
            user_id=user_id,
            workspace_id=workspace_id,
        )

        return await self._conversations.list_by_workspace(
            workspace_id,
            limit=limit,
            offset=offset,
        )

    
    async def add_user_message(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
    ) -> Message:
        conversation = await self._conversations.get_by_id(conversation_id)

        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} was not found")


        await self._authorization.require_workspace_write(
            user_id=user_id,
            workspace_id=conversation.workspace_id,
        )

        message = Message(
            conversation_id=conversation.id,
            author_user_id=user_id,
            role=MessageRole.USER,
            content=content,
            responder_type=None,
            agent_id=None,
        )

        await self._messages.create(message)

        await self._session.commit()
        await self._session.refresh(message)

        return message

    async def list_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        conversation = await self._conversations.get_by_id(conversation_id)

        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} was not found")


        await self._authorization.require_workspace_read(
            user_id=user_id,
            workspace_id=conversation.workspace_id,
        )

        return await self._messages.list_by_conversation(
            conversation_id,
            limit=limit,
            offset=offset,
        )