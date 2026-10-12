from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from app.db.session import SessionLocal
from app.identity.dependencies import (
    LAST_SEEN_UPDATE_INTERVAL,
    get_current_user,
)
from app.identity.models import ApplicationSession
from app.identity.sessions import create_application_session, revoke_user_session
from fastapi import HTTPException
from sqlalchemy import select


async def _commit_with_last_seen(db, user_id, *, last_seen_at) -> str:
    """Создать сессию с заданным last_seen_at и зафиксировать её в БД."""
    token = create_application_session(db, user_id=user_id)
    row = await db.scalar(
        select(ApplicationSession).where(ApplicationSession.user_id == user_id)
    )
    row.last_seen_at = last_seen_at
    await db.commit()
    return token


async def _committed_session_row(token: str) -> ApplicationSession:
    """Прочитать строку сессии новой сессией, мимо identity map теста.

    get_current_user обновляет last_seen_at Core-UPDATE и коммитит;
    чтобы увидеть реальное состояние БД, читать нужно из fresh-сессии.
    """
    token_hash = sha256(token.encode()).hexdigest()
    async with SessionLocal() as fresh:
        return await fresh.scalar(
            select(ApplicationSession).where(
                ApplicationSession.token_hash == token_hash
            )
        )


@pytest.mark.asyncio
async def test_missing_cookie_is_rejected(db, user) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session_token=None, db=db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_token_is_rejected(db, user) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session_token="unknown-token", db=db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_owner(db, user) -> None:
    token = create_application_session(db, user_id=user.id)

    current = await get_current_user(session_token=token, db=db)

    assert current.id == user.id


@pytest.mark.asyncio
async def test_revoked_session_is_rejected_and_last_seen_untouched(db, user) -> None:
    stale = datetime.now(UTC) - LAST_SEEN_UPDATE_INTERVAL - timedelta(minutes=1)
    token = await _commit_with_last_seen(db, user.id, last_seen_at=stale)
    await revoke_user_session(db, token)
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session_token=token, db=db)

    assert exc_info.value.status_code == 401

    committed = await _committed_session_row(token)
    assert committed.revoked_at is not None
    assert committed.last_seen_at == stale


@pytest.mark.asyncio
async def test_expired_session_is_rejected(db, user) -> None:
    token = create_application_session(db, user_id=user.id)
    row = await db.scalar(
        select(ApplicationSession).where(ApplicationSession.user_id == user.id)
    )
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session_token=token, db=db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_is_rejected(db, user) -> None:
    token = create_application_session(db, user_id=user.id)
    await db.commit()

    user.is_active = False
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session_token=token, db=db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_recent_last_seen_is_not_rewritten(db, user) -> None:
    recent = datetime.now(UTC) - timedelta(seconds=30)
    token = await _commit_with_last_seen(db, user.id, last_seen_at=recent)

    current = await get_current_user(session_token=token, db=db)

    assert current.id == user.id

    committed = await _committed_session_row(token)
    assert committed.last_seen_at == recent


@pytest.mark.asyncio
async def test_stale_last_seen_is_refreshed(db, user) -> None:
    stale = datetime.now(UTC) - LAST_SEEN_UPDATE_INTERVAL - timedelta(minutes=1)
    token = await _commit_with_last_seen(db, user.id, last_seen_at=stale)

    current = await get_current_user(session_token=token, db=db)

    assert current.id == user.id

    committed = await _committed_session_row(token)
    assert committed.last_seen_at != stale
    assert datetime.now(UTC) - committed.last_seen_at < timedelta(seconds=5)
