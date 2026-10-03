from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_conversation_service, get_current_identity
from app.auth.identity import CurrentIdentity
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.services.conversation import ConversationService
from app.schemas.message import MessageCreate, MessageResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    conversation = await service.create_conversation(
        workspace_id=request.workspace_id,
        user_id=identity.user_id,
        title=request.title,
    )

    return ConversationResponse.model_validate(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(conversation_id: uuid.UUID, identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)) -> ConversationResponse:
    conversation = await service.get_conversation(conversation_id=conversation_id, user_id=identity.user_id)

    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    workspace_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationResponse]:
    conversations = await service.list_conversations(
        workspace_id=workspace_id,
        user_id=identity.user_id,
        limit=limit,
        offset=offset,
    )

    return [
        ConversationResponse.model_validate(conversation)
        for conversation in conversations
    ]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: uuid.UUID,
    request: MessageCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    message = await service.add_user_message(conversation_id=conversation_id, user_id=identity.user_id, content=request.content)

    return MessageResponse.model_validate(message)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
) -> list[MessageResponse]:
    messages = await service.list_messages(conversation_id=conversation_id, user_id=identity.user_id, limit=limit, offset=offset)
    
    return [
        MessageResponse.model_validate(message)
        for message in messages
    ]