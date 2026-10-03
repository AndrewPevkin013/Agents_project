from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select

from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.models.workspace import Workspace
from app.db.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.db.session import AsyncSessionLocal

async def main() -> None:
    identity_subject = os.environ.get("DEV_IDENTITY_SUBJECT")

    if not identity_subject:
        raise RuntimeError(
            "DEV_IDENTITY_SUBJECT is not configured"
        )

    async with AsyncSessionLocal() as session:
        # User
        result = await session.execute(
            select(User).where(
                User.identity_subject == identity_subject
            )
        )

        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                identity_subject=identity_subject,
                email="pilotdev@example.com",
                display_name="Pilot Developer",
                is_active=True,
            )

            session.add(user)
            await session.flush()

        # Organization
        result = await session.execute(
            select(Organization).where(
                Organization.name == "Pilot Organization"
            )
        )

        organization = result.scalar_one_or_none()

        if organization is None:
            organization = Organization(
                id=uuid.uuid4(),
                name="Pilot Organization",
            )

            session.add(organization)
            await session.flush()

        # Workspace
        result = await session.execute(
            select(Workspace).where(
                Workspace.organization_id == organization.id,
                Workspace.name == "Pilot Workspace",
            )
        )

        workspace = result.scalar_one_or_none()

        if workspace is None:
            workspace = Workspace(
                id=uuid.uuid4(),
                organization_id=organization.id,
                name="Pilot Workspace",
                created_by=user.id,
            )

            session.add(workspace)
            await session.flush()

        # Membership
        result = await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id,
            )
        )

        membership = result.scalar_one_or_none()

        if membership is None:
            membership = WorkspaceMember(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            )

            session.add(membership)

        await session.commit()

        print("Dev seed ready")
        print(f"identity_subject={user.identity_subject}")
        print(f"user_id={user.id}")
        print(f"organization_id={organization.id}")
        print(f"workspace_id={workspace.id}")


if __name__ == "__main__":
    asyncio.run(main())