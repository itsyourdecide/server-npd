from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "event", "channel", "read_at")
    list_filter = ("channel", "event", "read_at")
    search_fields = ("recipient__username", "title", "target_id")
    readonly_fields = (
        "id",
        "recipient",
        "channel",
        "event",
        "title",
        "message",
        "target_type",
        "target_id",
        "deduplication_key",
        "created_at",
        "read_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
