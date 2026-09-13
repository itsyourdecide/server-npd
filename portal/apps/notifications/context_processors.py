from .models import Notification


def notifications(request):
    user = request.user
    if not user.is_authenticated or not user.is_active:
        return {"unread_notification_count": 0}
    return {
        "unread_notification_count": Notification.objects.filter(
            recipient=user,
            read_at__isnull=True,
        ).count()
    }
