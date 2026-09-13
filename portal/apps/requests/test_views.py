import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import SystemRole
from apps.projects.services import create_project

from .models import Approval, RequestTransition, ServiceRequest
from .services import create_request_draft, submit_request


class RequestViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="test")
        self.author = User.objects.create_user(
            username="author",
            password="author-password",
        )
        self.outsider = User.objects.create_user(username="outsider")
        self.reviewer = User.objects.create_user(username="reviewer")
        self.operator = User.objects.create_user(username="operator")
        self.reviewer.groups.add(Group.objects.get(name=SystemRole.REVIEWER.value))
        self.operator.groups.add(Group.objects.get(name=SystemRole.OPERATOR.value))
        self.project = create_project(
            actor=self.admin,
            owner=self.author,
            name="Research project",
        )

    def draft(self, title="Cluster access"):
        return create_request_draft(
            actor=self.author,
            project=self.project,
            kind=ServiceRequest.Kind.CLUSTER_ACCESS,
            title=title,
            description="Run simulations",
            idempotency_key=uuid.uuid4(),
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("requests:list"))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("requests:list")}',
        )

    def test_user_creates_request_for_visible_project(self):
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("requests:create"),
            {
                "project": self.project.pk,
                "kind": ServiceRequest.Kind.CLUSTER_ACCESS,
                "title": "Cluster access",
                "description": "Run simulations",
                "idempotency_key": uuid.uuid4(),
            },
        )

        service_request = ServiceRequest.objects.get()
        self.assertRedirects(
            response,
            reverse("requests:detail", args=[service_request.pk]),
        )
        self.assertEqual(service_request.author, self.author)

    def test_user_cannot_open_someone_elses_draft(self):
        service_request = self.draft()
        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse("requests:detail", args=[service_request.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_reviewer_queue_contains_submitted_but_not_draft_requests(self):
        draft = self.draft(title="Still draft")
        submitted = self.draft(title="Ready for review")
        submit_request(
            actor=self.author,
            service_request=submitted,
            idempotency_key=uuid.uuid4(),
        )
        self.client.force_login(self.reviewer)

        response = self.client.get(reverse("requests:list"))

        self.assertContains(response, "Review queue")
        self.assertContains(response, submitted.title)
        self.assertNotContains(response, draft.title)

    def test_full_manual_workflow_through_http_views(self):
        service_request = self.draft()

        self.client.force_login(self.author)
        response = self.client.post(
            reverse("requests:submit", args=[service_request.pk]),
            {"idempotency_key": uuid.uuid4()},
        )
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.reviewer)
        response = self.client.post(
            reverse("requests:begin-review", args=[service_request.pk]),
            {"idempotency_key": uuid.uuid4()},
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("requests:decide", args=[service_request.pk]),
            {
                "idempotency_key": uuid.uuid4(),
                "decision": Approval.Decision.APPROVED,
                "comment": "Approved for the course",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.operator)
        response = self.client.post(
            reverse("requests:begin-execution", args=[service_request.pk]),
            {"idempotency_key": uuid.uuid4()},
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("requests:finish-execution", args=[service_request.pk]),
            {
                "idempotency_key": uuid.uuid4(),
                "outcome": ServiceRequest.State.ACTIVE,
                "comment": "Provisioned manually",
            },
        )
        self.assertEqual(response.status_code, 302)

        service_request.refresh_from_db()
        self.assertEqual(service_request.state, ServiceRequest.State.ACTIVE)
        self.assertEqual(service_request.transitions.count(), 6)
        self.assertEqual(service_request.approvals.count(), 1)

    def test_repeated_submit_post_does_not_duplicate_transition(self):
        service_request = self.draft()
        key = uuid.uuid4()
        self.client.force_login(self.author)
        url = reverse("requests:submit", args=[service_request.pk])

        first = self.client.post(url, {"idempotency_key": key})
        second = self.client.post(url, {"idempotency_key": key})

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            RequestTransition.objects.filter(
                request=service_request,
                to_state=ServiceRequest.State.SUBMITTED,
            ).count(),
            1,
        )
