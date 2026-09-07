from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenPairResponse, UserResponse
from app.auth.security import create_access_token, generate_refresh_token, hash_refresh_token, hash_password, needs_rehash, refresh_expiration, verify_password
from app.config import settings
from app.db.models import RefreshSession, User
from app.db.session import get_db
from app.users.service import create_user, get_user_by_username_or_email

router = APIRouter(prefix="/auth", tags=["auth"])

async def issue_token_pair(db: AsyncSession, user: User) -> TokenPairResponse:
    access = create_access_token(user.id, user.role)
    refresh = generate_refresh_token()
    db.add(RefreshSession(user_id=user.id, token_hash=hash_refresh_token(refresh), expires_at=refresh_expiration()))
    await db.commit()
    return TokenPairResponse(access_token=access, refresh_token=refresh, expires_in=settings.access_token_expire_minutes * 60, user=UserResponse.model_validate(user))

@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await get_user_by_username_or_email(db, req.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    if await get_user_by_username_or_email(db, req.email.lower()):
        raise HTTPException(status_code=409, detail="Email already exists")
    try:
        user = await create_user(db, req.username, req.email, req.password)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="User already exists")
    return await issue_token_pair(db, user)

@router.post("/login", response_model=TokenPairResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username_or_email(db, req.login)
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
        await db.commit()
    return await issue_token_pair(db, user)

@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_refresh_token(req.refresh_token)
    result = await db.execute(select(RefreshSession).where(RefreshSession.token_hash == token_hash))
    session = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or does not exist")
    session.revoked_at = now
    await db.commit()
    return await issue_token_pair(db, user)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: LogoutRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_refresh_token(req.refresh_token)
    result = await db.execute(select(RefreshSession).where(RefreshSession.token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()

@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
