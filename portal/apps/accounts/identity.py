import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from .models import UserProfile


class InvalidOIDCClaims(ValueError):
    """Raised when verified OIDC claims cannot identify a portal user."""


@dataclass(frozen=True, slots=True)
class VerifiedOIDCClaims:
    issuer: str
    subject: str
    email: str = ""
    given_name: str = ""
    family_name: str = ""

    @classmethod
    def from_mapping(
        cls,
        *,
        issuer: object,
        claims: Mapping[str, object],
    ) -> "VerifiedOIDCClaims":
        subject = claims.get("sub")
        if not isinstance(issuer, str) or not issuer or len(issuer) > 512:
            raise InvalidOIDCClaims("OIDC issuer is missing or invalid")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise InvalidOIDCClaims("OIDC subject is missing or invalid")

        return cls(
            issuer=issuer,
            subject=subject,
            email=_optional_text(claims, "email", max_length=254),
            given_name=_optional_text(claims, "given_name", max_length=150),
            family_name=_optional_text(claims, "family_name", max_length=150),
        )


def _optional_text(
    claims: Mapping[str, object],
    name: str,
    *,
    max_length: int,
) -> str:
    value = claims.get(name)
    if not isinstance(value, str):
        return ""
    return value[:max_length]


def _username_for(claims: VerifiedOIDCClaims) -> str:
    identity = f"{claims.issuer}\0{claims.subject}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:32]
    return f"oidc_{digest}"


def _update_user(user, claims: VerifiedOIDCClaims):
    changed_fields = []
    values = {
        "email": claims.email,
        "first_name": claims.given_name,
        "last_name": claims.family_name,
    }
    for field, value in values.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed_fields.append(field)

    if changed_fields:
        user.save(update_fields=changed_fields)
    return user


def _sync_user_once(claims: VerifiedOIDCClaims):
    profile = (
        UserProfile.objects.select_for_update()
        .select_related("user")
        .filter(oidc_issuer=claims.issuer, oidc_subject=claims.subject)
        .first()
    )
    if profile is not None:
        return _update_user(profile.user, claims)

    User = get_user_model()
    user = User(
        username=_username_for(claims),
        email=claims.email,
        first_name=claims.given_name,
        last_name=claims.family_name,
    )
    user.set_unusable_password()
    user.save()
    UserProfile.objects.create(
        user=user,
        oidc_issuer=claims.issuer,
        oidc_subject=claims.subject,
    )
    return user


def sync_user_from_oidc(claims: VerifiedOIDCClaims):
    """Create or refresh a user using only the immutable OIDC identity."""

    try:
        with transaction.atomic():
            return _sync_user_once(claims)
    except IntegrityError:
        # A concurrent first login may have created the same profile. Retry only
        # when that exact immutable identity now exists; propagate other conflicts.
        with transaction.atomic():
            profile = (
                UserProfile.objects.select_for_update()
                .select_related("user")
                .filter(oidc_issuer=claims.issuer, oidc_subject=claims.subject)
                .first()
            )
            if profile is None:
                raise
            return _update_user(profile.user, claims)
