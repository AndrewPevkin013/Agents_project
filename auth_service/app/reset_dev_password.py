import asyncio
import getpass

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.models import User
from app.db.session import AsyncSessionLocal


async def main() -> None:
    username = input("Username: ").strip()
    password = getpass.getpass("New password: ")
    password_repeat = getpass.getpass("Repeat password: ")

    if password != password_repeat:
        raise RuntimeError("Passwords do not match")

    if len(password) < 10:
        raise RuntimeError("Password must contain at least 10 characters")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise RuntimeError(f"User {username!r} was not found")

        user.password_hash = hash_password(password)

        await session.commit()

        print(f"Password updated for {username!r}")


if __name__ == "__main__":
    asyncio.run(main())