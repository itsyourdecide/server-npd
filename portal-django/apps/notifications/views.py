from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification
from .services import mark_notification_read


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications},
    )


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(
        Notification.objects.filter(recipient=request.user),
        pk=notification_id,
    )
    mark_notification_read(actor=request.user, notification=notification)
    return redirect("notifications:list")
