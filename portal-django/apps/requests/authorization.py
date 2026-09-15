from django.db.models import Q, QuerySet

from apps.accounts.roles import can_execute_operations, can_review_requests

from .models import ServiceRequest


def _active_user(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def visible_requests_for(user) -> QuerySet[ServiceRequest]:
    if not _active_user(user):
        return ServiceRequest.objects.none()
    if user.is_superuser:
        return ServiceRequest.objects.all()

    visibility = Q(author=user)
    if can_review_requests(user):
        visibility |= ~Q(state=ServiceRequest.State.DRAFT)
    if can_execute_operations(user):
        visibility |= Q(
            state__in=(
                ServiceRequest.State.APPROVED,
                ServiceRequest.State.EXECUTING,
                ServiceRequest.State.ACTIVE,
                ServiceRequest.State.FAILED,
            )
        )
    return ServiceRequest.objects.filter(visibility).distinct()


def can_view_request(user, service_request: ServiceRequest) -> bool:
    if not _active_user(user):
        return False
    return visible_requests_for(user).filter(pk=service_request.pk).exists()
