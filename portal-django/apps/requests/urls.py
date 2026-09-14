from django.urls import path

from . import views


app_name = "requests"

urlpatterns = [
    path("", views.request_list, name="list"),
    path("new/", views.request_create, name="create"),
    path("<uuid:request_id>/", views.request_detail, name="detail"),
    path("<uuid:request_id>/submit/", views.request_submit, name="submit"),
    path(
        "<uuid:request_id>/begin-review/",
        views.request_begin_review,
        name="begin-review",
    ),
    path("<uuid:request_id>/decide/", views.request_decide, name="decide"),
    path(
        "<uuid:request_id>/begin-execution/",
        views.request_begin_execution,
        name="begin-execution",
    ),
    path(
        "<uuid:request_id>/finish-execution/",
        views.request_finish_execution,
        name="finish-execution",
    ),
]
