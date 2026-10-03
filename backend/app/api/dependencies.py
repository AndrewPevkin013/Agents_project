from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.identity import CurrentIdentity
from app.db.session import get_db
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.repositories.user import UserRepository
from app.services.conversation import ConversationService
from app.authz.service import AuthorizationService
from app.repositories.workspace_member import WorkspaceMemberRepository

async def get_current_identity(
    payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CurrentIdentity:
    identity_subject = payload["sub"]

    repository = UserRepository(session)

    user = await repository.get_by_identity_subject(
        identity_subject,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user is not registered in the product",
        )

    return CurrentIdentity(
        user_id=user.id,
        identity_subject=user.identity_subject,
    )

def get_conversation_service(session: AsyncSession = Depends(get_db)) -> ConversationService:
    workspace_member_repository = WorkspaceMemberRepository(session)

    authorization_service = AuthorizationService(
        workspace_member_repository=workspace_member_repository,
    )

    return ConversationService(
        session=session,
        conversation_repository=ConversationRepository(session),
        message_repository=MessageRepository(session),
        authorization_service=authorization_service,
    )
