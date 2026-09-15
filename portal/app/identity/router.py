from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.identity.oidc import oauth
from app.identity.services import get_or_create_user
from app.identity.sessions import create_application_session
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
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
        user_id = user.id

    response = JSONResponse(
        content={"user_id": str(user_id)}
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