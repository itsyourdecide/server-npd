from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.identity.oidc import oauth
from app.identity.services import get_or_create_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token["userinfo"]

    if not userinfo["email"] or userinfo["email_verified"] is not True:
        raise HTTPException(status_code=403, detail="Email not verified")
    async with db.begin():
        user = await get_or_create_user(db, issuer=userinfo["iss"], subject=userinfo["sub"], email=userinfo["email"])
        if user.is_active is False:
            raise HTTPException(status_code=403, detail="User is inactive")
        user_id = user.id
    return {"user_id": str(user_id)}
