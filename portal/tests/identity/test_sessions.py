from datetime import timedelta
from hashlib import sha256

import pytest
from app.core.config import settings
from app.identity.models import ApplicationSession
from app.identity.services import get_or_create_user
from app.identity.sessions import (
    create_application_session,
    get_user_by_session_token,
    revoke_user_session,
)
from sqlalchemy import select


@pytest.mark.asyncio
async def test_create_session_stores_hash_not_token(db, user) -> None:

    token = create_application_session(db, user_id=user.id)

    statement = select(ApplicationSession).where(
        ApplicationSession.user_id == user.id
    )
    stored_session = await db.scalar(statement)

    token_hash = stored_session.token_hash
    lifetime = stored_session.expires_at - stored_session.created_at
    expected = timedelta(seconds=settings.session_max_age_seconds)

    assert token_hash != token
    assert token_hash == sha256(token.encode()).hexdigest()
    assert expected - timedelta(seconds=5) <= lifetime <= expected + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_get_user_by_session_token_returns_owner(db, user) -> None:

    token = create_application_session(db, user_id=user.id)

    result = await get_user_by_session_token(db, token)

    assert result[0].id == user.id

@pytest.mark.asyncio
async def test_get_user_by_session_token_unknown_token_returns_none(db) -> None:

    result = await get_user_by_session_token(db, "unknown-token")

    assert result is None

@pytest.mark.asyncio
async def test_revoke_user_session_happy_path(db, user) -> None:

    token = create_application_session(db, user_id=user.id)

    await revoke_user_session(db, token)

    statement = select(ApplicationSession).where(
        ApplicationSession.user_id == user.id
    )
    stored_session = await db.scalar(statement)

    assert stored_session.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_user_session_unknown_token_does_nothing(db, user) -> None:

    create_application_session(db, user_id=user.id)

    statement = select(ApplicationSession).where(
        ApplicationSession.user_id == user.id
    )
    stored_session = await db.scalar(statement)

    await revoke_user_session(db, "unknown-token")
    
    assert stored_session.revoked_at is None


@pytest.mark.asyncio
async def test_revoke_user_session_none_token_does_nothing(db, user) -> None:
    
    create_application_session(db, user_id=user.id)

    statement = select(ApplicationSession).where(
        ApplicationSession.user_id == user.id
    )
    stored_session = await db.scalar(statement)

    await revoke_user_session(db, None)
    
    assert stored_session.revoked_at is None

@pytest.mark.asyncio
async def test_revoke_user_session_retries(db, user) -> None:

    token = create_application_session(db, user_id=user.id)

    await revoke_user_session(db, token)
    
    statement = select(ApplicationSession).where(
        ApplicationSession.user_id == user.id
    )
    stored_session = await db.scalar(statement)

    revoked_at = stored_session.revoked_at

    await revoke_user_session(db, token)

    statement = select(ApplicationSession).where(
            ApplicationSession.user_id == user.id
        )
    stored_session = await db.scalar(statement)

    assert revoked_at == stored_session.revoked_at