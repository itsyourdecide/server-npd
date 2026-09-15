import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.identity.models import ApplicationSession
from app.users.models import User
from app.db.session import get_db


def create_application_session(
        db: AsyncSession,
        *,
        user_id: UUID
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token.encode()).hexdigest()

    app_session = ApplicationSession(
        user_id = user_id,
        token_hash = token_hash,
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.session_max_age_seconds),

    )

    db.add(app_session)

    return token

async def get_user_by_session_token(
        db: AsyncSession,
        session_token: str,
) -> tuple[User, ApplicationSession] | None:
    token_hash = sha256(session_token.encode()).hexdigest()

    statement = select(ApplicationSession).where(
        ApplicationSession.token_hash == token_hash
    )
    session = await db.scalar(statement)

    if session is None:
        return None
    
    user_id = session.user_id

    statement = select(User).where(
        User.id == user_id
    )
    user = await db.scalar(statement)

    if user is None:
        raise RuntimeError("session references missing user")

    return user, session

async def revoke_user_session(
    db: AsyncSession,
    session_token: str | None,
) -> None:
    if session_token is None:
        return

    token_hash = sha256(session_token.encode()).hexdigest()

    statement = select(ApplicationSession).where(
        ApplicationSession.token_hash == token_hash
    )
    application_session = await db.scalar(statement)

    if application_session is None:
        return

    if application_session.revoked_at is not None:
        return

    application_session.revoked_at = datetime.now(UTC)




    

    
