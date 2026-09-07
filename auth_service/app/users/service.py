from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.security import hash_password
from app.db.models import User

async def get_user_by_username_or_email(db: AsyncSession, login: str) -> User | None:
    value = login.strip()
    result = await db.execute(select(User).where(or_(User.username == value, User.email == value.lower())))
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, user_id) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, username: str, email: str, password: str) -> User:
    user = User(username=username.strip(), email=email.strip().lower(), password_hash=hash_password(password), role="user", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
