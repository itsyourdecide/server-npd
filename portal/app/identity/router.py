from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.identity.csrf import verify_csrf
from app.identity.dependencies import get_current_user
from app.identity.oidc import oauth
from app.identity.services import get_or_create_user
from app.identity.sessions import create_application_session, revoke_user_session
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)

@router.get("/register")
async def register(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri, prompt="create")

@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token["userinfo"]

    email = userinfo.get("email")
    email_verified = userinfo.get("email_verified")

    if not email or email_verified is not True:
        raise HTTPException(status_code=403, detail="Email not verified")
    async with db.begin():
        user = await get_or_create_user(
            db,
            issuer=userinfo["iss"],
            subject=userinfo["sub"],
            email=email,
        )

        if user.is_active is False:
            raise HTTPException(
                status_code=403,
                detail="User is inactive"
            )

        session_token = create_application_session(
            db,
            user_id=user.id,
        )

    response = RedirectResponse(
        url=str(request.url_for("dashboard")),
        status_code=303,
    )

    response.set_cookie(
        key="npd_session",
        value=session_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.oidc_cookie_secure,
        samesite="lax",
        path="/",
    )
        
    return response

@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"user_id": str(user.id)}

@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(
    request: Request,
    session_token: str | None = Cookie(
        default=None,
        alias="npd_session",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    async with db.begin():
        await revoke_user_session(db, session_token)

    metadata = await oauth.keycloak.load_server_metadata()
    end_session_endpoint = metadata["end_session_endpoint"]

    post_logout_redirect_uri = str(
        request.url_for("logged_out")
    )

    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
    )

    keycloak_logout_url = (
        f"{end_session_endpoint}?{query}"
    )

    response = RedirectResponse(
        url=keycloak_logout_url,
        status_code=303,
    )

    response.delete_cookie(
        key="npd_session",
        path="/"
    )
    return response

@router.get("/logged-out", name="logged_out")
async def logged_out() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=303)
