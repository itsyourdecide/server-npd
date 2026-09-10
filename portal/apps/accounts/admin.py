from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "oidc_issuer",
        "cluster_login",
        "cluster_uid",
        "provisioning_status",
    )
    list_filter = ("provisioning_status", "oidc_issuer")
    search_fields = (
        "user__username",
        "user__email",
        "oidc_subject",
        "cluster_login",
    )
    readonly_fields = ("id", "created_at", "updated_at")
