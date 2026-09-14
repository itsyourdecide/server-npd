from django.db.models import Q, QuerySet

from .models import Project, ProjectMembership


def _is_active_user(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def visible_projects_for(user) -> QuerySet[Project]:
    if not _is_active_user(user):
        return Project.objects.none()
    if user.is_superuser:
        return Project.objects.all()
    return Project.objects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).distinct()


def can_view_project(user, project: Project) -> bool:
    if not _is_active_user(user):
        return False
    if user.is_superuser or project.owner_id == user.pk:
        return True
    return project.memberships.filter(user=user).exists()


def can_manage_project(user, project: Project) -> bool:
    if not _is_active_user(user):
        return False
    if user.is_superuser or project.owner_id == user.pk:
        return True
    return project.memberships.filter(
        user=user,
        role=ProjectMembership.Role.LEAD,
    ).exists()
