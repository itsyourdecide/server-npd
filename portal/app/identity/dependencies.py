from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.identity.sessions import get_user_by_session_token
from app.users.models import User


async def get_current_user(
    session_token: str | None = Cookie(
        default=None,
        alias="npd_session",
    ),
    db: AsyncSession = Depends(get_db),
) -> User:
    if session_token is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    result = await get_user_by_session_token(db, session_token)

    if result is None:
        raise HTTPException(status_code=401, detail="Invalid session")

    user, application_session = result
    now = datetime.now(UTC)

    if application_session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid session")

    if application_session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid session")

    if user.is_active is False:
        raise HTTPException(status_code=401, detail="Invalid session")

    return user