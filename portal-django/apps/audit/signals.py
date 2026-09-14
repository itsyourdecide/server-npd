from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.core.signing import salted_hmac
from django.dispatch import receiver

from .models import AuditEvent
from .services import record_event


LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
LOGOUT = "auth.logout"
AUTH_METHOD_SESSION_KEY = "npd_authentication_method"


def _authentication_method(request, user=None):
    if request is not None:
        session = getattr(request, "session", {})
        session_method = session.get(AUTH_METHOD_SESSION_KEY)
        if session_method:
            return session_method

    backend = getattr(user, "backend", "") if user is not None else ""
    if "PortalOIDCAuthenticationBackend" in backend:
        return AuditEvent.AuthenticationMethod.OIDC
    if "ModelBackend" in backend:
        return AuditEvent.AuthenticationMethod.LOCAL

    path = getattr(request, "path", "") if request is not None else ""
    if path.startswith("/oidc/"):
        return AuditEvent.AuthenticationMethod.OIDC
    return AuditEvent.AuthenticationMethod.UNKNOWN


def _identifier_fingerprint(credentials):
    identifier = credentials.get("username") if credentials else None
    if not isinstance(identifier, str) or not identifier:
        return ""
    normalized_identifier = identifier.strip().casefold()
    return salted_hmac(
        "npd.audit.login-identifier",
        normalized_identifier,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


@receiver(user_logged_in, dispatch_uid="npd.audit.login_succeeded")
def record_login_succeeded(sender, request, user, **kwargs):
    method = _authentication_method(request, user)
    request.session[AUTH_METHOD_SESSION_KEY] = method
    record_event(
        category=AuditEvent.Category.AUTHENTICATION,
        action=LOGIN_SUCCEEDED,
        actor=user,
        authentication_method=method,
        request=request,
    )


@receiver(user_login_failed, dispatch_uid="npd.audit.login_failed")
def record_login_failed(sender, credentials, request, **kwargs):
    details = {}
    identifier_fingerprint = _identifier_fingerprint(credentials)
    if identifier_fingerprint:
        details["identifier_fingerprint"] = identifier_fingerprint

    path = getattr(request, "path", "") if request is not None else ""
    if path.startswith("/oidc/"):
        method = AuditEvent.AuthenticationMethod.OIDC
    elif credentials and "username" in credentials:
        method = AuditEvent.AuthenticationMethod.LOCAL
    else:
        method = AuditEvent.AuthenticationMethod.UNKNOWN

    record_event(
        category=AuditEvent.Category.AUTHENTICATION,
        action=LOGIN_FAILED,
        authentication_method=method,
        request=request,
        details=details,
    )


@receiver(user_logged_out, dispatch_uid="npd.audit.logout")
def record_logout(sender, request, user, **kwargs):
    record_event(
        category=AuditEvent.Category.AUTHENTICATION,
        action=LOGOUT,
        actor=user if getattr(user, "is_authenticated", False) else None,
        authentication_method=_authentication_method(request, user),
        request=request,
    )
