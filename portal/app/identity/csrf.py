import hmac

from fastapi import Cookie, Header, HTTPException, Request

from app.core.config import settings


def make_csrf_token(session_token: str) -> str:
    return hmac.new(
        settings.csrf_secret.get_secret_value().encode(),
        ("csrf-v1:" + session_token).encode(),
        digestmod="sha256",
    ).hexdigest()


async def verify_csrf(
    request: Request,
    session_token: str | None = Cookie(default=None, alias="npd_session"),
    header_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if session_token is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    submitted_token = header_token

    if submitted_token is None:
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type == "application/x-www-form-urlencoded":
            form = await request.form()
            value = form.get("csrf_token")
            if isinstance(value, str):
                submitted_token = value

    if not submitted_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")

    expected_token = make_csrf_token(session_token)

    if not hmac.compare_digest(submitted_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")