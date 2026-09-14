from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "category",
        "action",
        "actor_label",
        "authentication_method",
        "source_ip",
        "request_id",
    )
    list_filter = ("category", "action", "authentication_method")
    search_fields = ("actor_label", "target_type", "target_id", "request_id")
    readonly_fields = (
        "id",
        "created_at",
        "category",
        "action",
        "actor",
        "actor_label",
        "authentication_method",
        "request_id",
        "source_ip",
        "target_type",
        "target_id",
        "details",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
