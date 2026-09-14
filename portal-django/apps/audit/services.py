from collections.abc import Mapping
from ipaddress import ip_address

from .models import AuditEvent


SENSITIVE_DETAIL_FRAGMENTS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
}


def _validate_details(details: Mapping[str, object]) -> dict[str, object]:
    def validate_value(value):
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                normalized_key = str(key).casefold()
                if any(
                    fragment in normalized_key
                    for fragment in SENSITIVE_DETAIL_FRAGMENTS
                ):
                    raise ValueError(
                        f"Sensitive audit detail key is not allowed: {key}"
                    )
                validate_value(nested_value)
        elif isinstance(value, (list, tuple)):
            for nested_value in value:
                validate_value(nested_value)

    validate_value(details)
    return dict(details)


def source_ip_from_request(request):
    if request is None:
        return None

    remote_address = request.META.get("REMOTE_ADDR", "")
    candidate = remote_address
    try:
        remote_ip = ip_address(remote_address)
    except ValueError:
        remote_ip = None

    if remote_ip is not None and remote_ip.is_loopback:
        candidate = request.META.get("HTTP_X_REAL_IP", remote_address)

    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


def record_event(
    *,
    category,
    action,
    actor=None,
    authentication_method="",
    request=None,
    target_type="",
    target_id="",
    details=None,
):
    """Create one immutable audit event from already validated application data."""

    request_id = getattr(request, "audit_request_id", None) if request else None
    actor_label = actor.get_username()[:150] if actor is not None else ""
    safe_details = _validate_details(details or {})

    return AuditEvent.objects.create(
        category=category,
        action=action,
        actor=actor,
        actor_label=actor_label,
        authentication_method=authentication_method,
        request_id=request_id,
        source_ip=source_ip_from_request(request),
        target_type=target_type,
        target_id=str(target_id)[:128],
        details=safe_details,
    )
