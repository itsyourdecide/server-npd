from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.identity.oidc import oauth

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    redirect_uri = request.url_for("auth_callback")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request) -> dict[str, object]:
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token["userinfo"]

    return {
        "issuer": userinfo["iss"],
        "subject": userinfo["sub"],
        "email": userinfo["email"],
        "email_verified": userinfo["email_verified"],
        "given_name": userinfo.get("given_name"),
        "family_name": userinfo.get("family_name"),
    }
