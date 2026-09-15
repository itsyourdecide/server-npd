from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .models import Notification


def notify_request_transition(service_request, transition):
    """Create one in-app notification for a transition made by someone else."""

    if transition.actor_id == service_request.author_id:
        return None

    state_label = service_request.get_state_display()
    notification, _ = Notification.objects.get_or_create(
        deduplication_key=(
            f"request-transition:{transition.pk}:recipient:{service_request.author_id}"
        ),
        defaults={
            "recipient": service_request.author,
            "event": Notification.Event.REQUEST_STATE_CHANGED,
            "title": f"Request status: {state_label}",
            "message": (
                f'Your request "{service_request.title}" changed to {state_label}.'
            ),
            "target_type": "service_request",
            "target_id": str(service_request.pk),
        },
    )
    return notification


@transaction.atomic
def mark_notification_read(*, actor, notification):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("An active user is required")

    locked = Notification.objects.select_for_update().get(pk=notification.pk)
    if locked.recipient_id != actor.pk:
        raise PermissionDenied("Only the recipient can update this notification")
    if locked.read_at is None:
        locked.read_at = timezone.now()
        locked.save(update_fields=["read_at"])
    return locked
