from django.urls import path

from . import views


app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path(
        "<uuid:notification_id>/read/",
        views.notification_mark_read,
        name="mark-read",
    ),
]
