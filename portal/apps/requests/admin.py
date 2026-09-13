from django.contrib import admin

from .models import Approval, RequestTransition, ServiceRequest


class RequestTransitionInline(admin.TabularInline):
    model = RequestTransition
    extra = 0
    can_delete = False
    readonly_fields = (
        "id",
        "actor",
        "from_state",
        "to_state",
        "comment",
        "idempotency_key",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


class ApprovalInline(admin.TabularInline):
    model = Approval
    extra = 0
    can_delete = False
    readonly_fields = (
        "id",
        "transition",
        "reviewer",
        "decision",
        "comment",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "project", "author", "state", "created_at")
    list_filter = ("kind", "state")
    search_fields = ("title", "description", "author__username", "project__name")
    readonly_fields = (
        "id",
        "creation_key",
        "author",
        "project",
        "kind",
        "title",
        "description",
        "state",
        "created_at",
        "updated_at",
    )
    inlines = (RequestTransitionInline, ApprovalInline)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestTransition)
class RequestTransitionAdmin(admin.ModelAdmin):
    list_display = ("request", "from_state", "to_state", "actor", "created_at")
    readonly_fields = (
        "id",
        "request",
        "actor",
        "from_state",
        "to_state",
        "comment",
        "idempotency_key",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ("request", "decision", "reviewer", "created_at")
    readonly_fields = (
        "id",
        "request",
        "transition",
        "reviewer",
        "decision",
        "comment",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
