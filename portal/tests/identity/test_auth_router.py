from hashlib import sha256
from urllib.parse import parse_qs, urlparse

import app.identity.router as identity_router
import pytest
from app.core.config import settings
from app.db.session import SessionLocal
from app.identity.csrf import make_csrf_token
from app.identity.models import ApplicationSession
from app.identity.oidc import oauth
from app.identity.sessions import create_application_session, get_or_create_user
from fastapi import HTTPException  # noqa: F401  (см. мутации веток 401)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

END_SESSION_ENDPOINT = "https://keycloak.test/protocol/openid-connect/logout"


async def _committed_user_with_session(db):
    """User и session, закоммиченные в БД, — иначе приложение их не увидит."""
    user = await get_or_create_user(
        db=db,
        issuer="issuer",
        subject="subject",
        email="email@example.com",
    )
    token = create_application_session(db, user_id=user.id)
    await db.commit()
    return user, token


async def _committed_session_row(token: str) -> ApplicationSession:
    """Свежее чтение из БД мимо identity map тестовой сессии."""
    token_hash = sha256(token.encode()).hexdigest()
    async with SessionLocal() as fresh:
        return await fresh.scalar(
            select(ApplicationSession).where(
                ApplicationSession.token_hash == token_hash
            )
        )


def _keycloak_token(monkeypatch, userinfo: dict) -> None:
    """Подменить обмен кода на токен; сеть Keycloak не участвует."""
    async def fake_access_token(request):
        return {"userinfo": userinfo}

    monkeypatch.setattr(oauth.keycloak, "authorize_access_token", fake_access_token)


def _keycloak_logout(monkeypatch) -> None:
    async def fake_metadata():
        return {"end_session_endpoint": END_SESSION_ENDPOINT}

    monkeypatch.setattr(oauth.keycloak, "load_server_metadata", fake_metadata)


def _assert_session_cookie_flags(response) -> None:
    set_cookie = response.headers.get("set-cookie", "")
    assert "npd_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert f"Max-Age={settings.session_max_age_seconds}" in set_cookie
    if settings.oidc_cookie_secure:
        assert "Secure" in set_cookie
    else:
        assert "Secure" not in set_cookie


@pytest.mark.asyncio
async def test_me_requires_session_cookie(client) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_id(client, db) -> None:
    user, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}


@pytest.mark.asyncio
async def test_csrf_requires_session_cookie(client) -> None:
    response = await client.get("/auth/csrf")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_csrf_returns_token_and_is_never_cached(client, db) -> None:
    _, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.get("/auth/csrf")

    assert response.status_code == 200
    assert response.json() == {"csrf_token": make_csrf_token(token)}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_logout_without_csrf_token_is_rejected(client, db) -> None:
    _, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.post("/auth/logout")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_logout_revokes_session_and_redirects_without_id_token_hint(
    client, db, monkeypatch
) -> None:
    _, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)
    _keycloak_logout(monkeypatch)

    response = await client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": make_csrf_token(token)},
    )

    assert response.status_code == 303

    # Портал отзывает свою сессию на стороне сервера.
    committed = await _committed_session_row(token)
    assert committed.revoked_at is not None

    # Браузер больше не должен носить токен.
    assert "npd_session=" in response.headers.get("set-cookie", "")

    # Редирект идёт в end_session Keycloak; id_token_hint отсутствует —
    # осознанное решение ID-002: Portal не хранит id_token.
    location = response.headers["location"]
    assert location.startswith(END_SESSION_ENDPOINT)
    params = parse_qs(urlparse(location).query)
    assert params["client_id"] == [settings.oidc_client_id]
    assert params["post_logout_redirect_uri"] == [
        "http://testserver/auth/logged-out"
    ]
    assert "id_token_hint" not in params


@pytest.mark.asyncio
async def test_callback_rejects_missing_email(client, monkeypatch) -> None:
    _keycloak_token(
        monkeypatch,
        {"iss": "issuer", "sub": "subject", "email": None, "email_verified": True},
    )

    response = await client.get("/auth/callback")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_callback_rejects_unverified_email(client, monkeypatch) -> None:
    _keycloak_token(
        monkeypatch,
        {"iss": "issuer", "sub": "subject", "email": "a@b.c", "email_verified": False},
    )

    response = await client.get("/auth/callback")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_callback_logs_in_and_sets_cookie(client, monkeypatch) -> None:
    _keycloak_token(
        monkeypatch,
        {"iss": "issuer", "sub": "subject", "email": "a@b.c", "email_verified": True},
    )

    response = await client.get("/auth/callback")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/dashboard")

    _assert_session_cookie_flags(response)

    token = response.cookies.get("npd_session")
    committed = await _committed_session_row(token)
    assert committed is not None


@pytest.mark.asyncio
async def test_callback_retries_when_parallel_login_wins(
    client, monkeypatch
) -> None:
    _keycloak_token(
        monkeypatch,
        {"iss": "issuer", "sub": "subject", "email": "a@b.c", "email_verified": True},
    )

    real_login = identity_router._login_and_create_session
    calls = {"count": 0}

    async def losing_the_race(db, *, issuer, subject, email):
        calls["count"] += 1
        if calls["count"] == 1:
            # Параллельный логин той же identity закоммитился первым.
            raise IntegrityError("INSERT ...", None, Exception("duplicate key"))
        return await real_login(db, issuer=issuer, subject=subject, email=email)

    monkeypatch.setattr(
        identity_router, "_login_and_create_session", losing_the_race
    )

    response = await client.get("/auth/callback")

    assert response.status_code == 303
    assert calls["count"] == 2
    _assert_session_cookie_flags(response)
