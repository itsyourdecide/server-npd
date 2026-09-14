import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.accounts.roles import SystemRole

from .authorization import can_manage_project, can_view_project, visible_projects_for
from .models import Project, ProjectMembership
from .services import create_project


class ProjectModelAndServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="test")
        self.owner = User.objects.create_user(username="owner")

    def test_admin_creates_project_with_lead_membership_for_owner(self):
        project = create_project(
            actor=self.admin,
            owner=self.owner,
            name="  Research project  ",
            description="  Simulation work  ",
        )

        self.assertIsInstance(project.id, uuid.UUID)
        self.assertEqual(project.name, "Research project")
        self.assertEqual(project.description, "Simulation work")
        self.assertEqual(project.state, Project.State.ACTIVE)
        membership = ProjectMembership.objects.get(project=project, user=self.owner)
        self.assertEqual(membership.role, ProjectMembership.Role.LEAD)

    def test_regular_user_cannot_create_project(self):
        with self.assertRaises(PermissionDenied):
            create_project(actor=self.owner, owner=self.owner, name="Denied")

        self.assertFalse(Project.objects.exists())

    def test_project_name_cannot_be_blank(self):
        with self.assertRaises(ValidationError):
            create_project(actor=self.admin, owner=self.owner, name="   ")

    def test_project_owner_must_be_active(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            create_project(actor=self.admin, owner=self.owner, name="Denied")

    @patch("apps.projects.services.ProjectMembership.objects.create")
    def test_project_creation_rolls_back_if_membership_creation_fails(self, create):
        create.side_effect = IntegrityError("membership failure")

        with self.assertRaises(IntegrityError):
            create_project(actor=self.admin, owner=self.owner, name="Atomic project")

        self.assertFalse(Project.objects.exists())

    def test_membership_is_unique_per_project_and_user(self):
        project = create_project(
            actor=self.admin,
            owner=self.owner,
            name="Research project",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectMembership.objects.create(
                project=project,
                user=self.owner,
                role=ProjectMembership.Role.MEMBER,
            )

    def test_owner_cannot_be_deleted_while_project_exists(self):
        create_project(actor=self.admin, owner=self.owner, name="Research project")

        with self.assertRaises(ProtectedError):
            self.owner.delete()


class ProjectAuthorizationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="test")
        self.owner = User.objects.create_user(username="owner")
        self.member = User.objects.create_user(username="member")
        self.lead = User.objects.create_user(username="lead")
        self.outsider = User.objects.create_user(username="outsider")
        self.project = create_project(
            actor=self.admin,
            owner=self.owner,
            name="Private project",
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            role=ProjectMembership.Role.MEMBER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.lead,
            role=ProjectMembership.Role.LEAD,
        )

    def test_visible_queryset_contains_only_accessible_projects(self):
        other_owner = get_user_model().objects.create_user(username="other-owner")
        other_project = create_project(
            actor=self.admin,
            owner=other_owner,
            name="Other project",
        )

        self.assertQuerySetEqual(
            visible_projects_for(self.member),
            [self.project],
            ordered=False,
        )
        self.assertNotIn(other_project, visible_projects_for(self.member))

    def test_member_can_view_but_cannot_manage_project(self):
        self.assertTrue(can_view_project(self.member, self.project))
        self.assertFalse(can_manage_project(self.member, self.project))

    def test_owner_and_lead_can_manage_project(self):
        self.assertTrue(can_manage_project(self.owner, self.project))
        self.assertTrue(can_manage_project(self.lead, self.project))

    def test_outsider_and_anonymous_user_have_no_access(self):
        for user in (self.outsider, AnonymousUser()):
            self.assertFalse(can_view_project(user, self.project))
            self.assertFalse(can_manage_project(user, self.project))
            self.assertFalse(visible_projects_for(user).exists())

    def test_reviewer_has_no_implicit_access_to_unrelated_project(self):
        self.outsider.groups.add(Group.objects.get(name=SystemRole.REVIEWER.value))

        self.assertFalse(can_view_project(self.outsider, self.project))
        self.assertFalse(can_manage_project(self.outsider, self.project))

    def test_admin_can_view_and_manage_every_project(self):
        self.assertTrue(can_view_project(self.admin, self.project))
        self.assertTrue(can_manage_project(self.admin, self.project))
        self.assertIn(self.project, visible_projects_for(self.admin))

    def test_inactive_member_has_no_access(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])

        self.assertFalse(can_view_project(self.member, self.project))
        self.assertFalse(can_manage_project(self.member, self.project))
        self.assertFalse(visible_projects_for(self.member).exists())
