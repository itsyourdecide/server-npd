import jwt
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .identity import InvalidOIDCClaims, VerifiedOIDCClaims, sync_user_from_oidc


class PortalOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Authenticate by verified issuer+subject instead of mutable email."""

    def _verify_jws(self, token, key):
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header["alg"]
            if algorithm != self.OIDC_RP_SIGN_ALGO:
                raise SuspiciousOperation("Unexpected OIDC signing algorithm")

            return jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=self.OIDC_RP_CLIENT_ID,
                issuer=settings.OIDC_OP_ISSUER,
                options={"require": ["aud", "exp", "iat", "iss", "sub"]},
            )
        except SuspiciousOperation:
            raise
        except (KeyError, jwt.PyJWTError) as exc:
            raise SuspiciousOperation("OIDC ID token validation failed") from exc

    def get_or_create_user(self, access_token, id_token, payload):
        user_info = self.get_userinfo(access_token, id_token, payload)
        token_subject = payload.get("sub")
        if token_subject != user_info.get("sub"):
            raise SuspiciousOperation("OIDC subject mismatch")

        try:
            claims = VerifiedOIDCClaims.from_mapping(
                issuer=payload.get("iss"),
                claims=user_info,
            )
        except InvalidOIDCClaims as exc:
            raise SuspiciousOperation("Required OIDC claims are invalid") from exc

        user = sync_user_from_oidc(claims)
        if not self.user_can_authenticate(user):
            return None
        return user
