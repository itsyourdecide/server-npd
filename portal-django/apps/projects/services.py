from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import Project, ProjectMembership


@transaction.atomic
def create_project(*, actor, owner, name: str, description: str = "") -> Project:
    """Create a project and its owner membership as one database operation."""

    if not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Only a portal admin can create projects")
    if not owner.is_active:
        raise ValidationError("Project owner must be active")

    project = Project(
        name=name.strip(),
        description=description.strip(),
        owner=owner,
    )
    project.full_clean()
    project.save()
    ProjectMembership.objects.create(
        project=project,
        user=owner,
        role=ProjectMembership.Role.LEAD,
    )
    return project
