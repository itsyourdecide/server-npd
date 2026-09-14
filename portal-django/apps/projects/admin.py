from django.contrib import admin

from .models import Project, ProjectMembership


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "state", "created_at")
    list_filter = ("state",)
    search_fields = ("name", "owner__username", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (ProjectMembershipInline,)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields.append("owner")
        return fields

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            ProjectMembership.objects.get_or_create(
                project=obj,
                user=obj.owner,
                defaults={"role": ProjectMembership.Role.LEAD},
            )


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("project__name", "user__username", "user__email")
    readonly_fields = ("id", "created_at")
