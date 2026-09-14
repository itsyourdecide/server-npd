from django.contrib import admin

from .models import ExternalIdentity, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cluster_login",
        "cluster_uid",
        "provisioning_status",
    )
    list_filter = ("provisioning_status",)
    search_fields = (
        "user__username",
        "user__email",
        "cluster_login",
    )
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "issuer", "email", "updated_at")
    list_filter = ("provider", "issuer")
    search_fields = ("user__username", "user__email", "subject", "email")
    readonly_fields = (
        "id",
        "user",
        "provider",
        "issuer",
        "subject",
        "email",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
