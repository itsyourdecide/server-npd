import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.test import TestCase

from apps.accounts.roles import SystemRole
from apps.audit.models import AuditEvent
from apps.projects.models import Project, ProjectMembership
from apps.projects.services import create_project

from .models import Approval, RequestMutationError, RequestTransition, ServiceRequest
from .services import (
    begin_execution,
    begin_review,
    create_request_draft,
    decide_request,
    finish_execution,
    submit_request,
)


class RequestWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="test")
        self.author = User.objects.create_user(username="author")
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

    def draft(self, **overrides):
        values = {
            "actor": self.author,
            "project": self.project,
            "kind": ServiceRequest.Kind.CLUSTER_ACCESS,
            "title": "Cluster access",
            "description": "Run simulations",
            "idempotency_key": uuid.uuid4(),
        }
        values.update(overrides)
        return create_request_draft(**values)

    def submitted(self):
        service_request = self.draft()
        return submit_request(
            actor=self.author,
            service_request=service_request,
            idempotency_key=uuid.uuid4(),
        )

    def under_review(self):
        service_request = self.submitted()
        return begin_review(
            actor=self.reviewer,
            service_request=service_request,
            idempotency_key=uuid.uuid4(),
        )

    def approved(self):
        service_request = self.under_review()
        return decide_request(
            actor=self.reviewer,
            service_request=service_request,
            decision=Approval.Decision.APPROVED,
            comment="Approved for the course",
            idempotency_key=uuid.uuid4(),
        )

    def test_creation_is_idempotent_and_has_initial_history(self):
        key = uuid.uuid4()
        first = self.draft(idempotency_key=key)
        second = self.draft(idempotency_key=key)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ServiceRequest.objects.count(), 1)
        transition = RequestTransition.objects.get()
        self.assertEqual(transition.from_state, "")
        self.assertEqual(transition.to_state, ServiceRequest.State.DRAFT)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="request.created",
                target_id=str(first.pk),
            ).exists()
        )

    def test_creation_key_cannot_be_reused_with_different_content(self):
        key = uuid.uuid4()
        self.draft(idempotency_key=key)

        with self.assertRaises(ValidationError):
            self.draft(idempotency_key=key, title="Different request")

    def test_outsider_cannot_create_request_for_private_project(self):
        with self.assertRaises(PermissionDenied):
            self.draft(actor=self.outsider)

    def test_author_submits_and_reviewer_starts_review(self):
        service_request = self.submitted()
        self.assertEqual(service_request.state, ServiceRequest.State.SUBMITTED)

        service_request = begin_review(
            actor=self.reviewer,
            service_request=service_request,
            idempotency_key=uuid.uuid4(),
        )

        self.assertEqual(service_request.state, ServiceRequest.State.UNDER_REVIEW)
        self.assertEqual(service_request.transitions.count(), 3)

    def test_requester_cannot_review_own_request_even_with_reviewer_role(self):
        self.author.groups.add(Group.objects.get(name=SystemRole.REVIEWER.value))
        service_request = self.submitted()

        with self.assertRaises(PermissionDenied):
            begin_review(
                actor=self.author,
                service_request=service_request,
                idempotency_key=uuid.uuid4(),
            )

    def test_reviewer_decision_requires_comment_and_is_append_only(self):
        service_request = self.under_review()

        with self.assertRaises(ValidationError):
            decide_request(
                actor=self.reviewer,
                service_request=service_request,
                decision=Approval.Decision.APPROVED,
                comment="   ",
                idempotency_key=uuid.uuid4(),
            )

        service_request = decide_request(
            actor=self.reviewer,
            service_request=service_request,
            decision=Approval.Decision.APPROVED,
            comment="Approved",
            idempotency_key=uuid.uuid4(),
        )
        approval = Approval.objects.get(request=service_request)
        self.assertEqual(approval.decision, Approval.Decision.APPROVED)

        approval.comment = "Changed"
        with self.assertRaises(RequestMutationError):
            approval.save()

    def test_operator_records_manual_execution_result(self):
        service_request = self.approved()
        service_request = begin_execution(
            actor=self.operator,
            service_request=service_request,
            idempotency_key=uuid.uuid4(),
        )
        service_request = finish_execution(
            actor=self.operator,
            service_request=service_request,
            outcome=ServiceRequest.State.ACTIVE,
            comment="Provisioned manually using the runbook",
            idempotency_key=uuid.uuid4(),
        )

        self.assertEqual(service_request.state, ServiceRequest.State.ACTIVE)
        self.assertEqual(service_request.transitions.count(), 6)

    def test_repeated_transition_key_does_not_create_duplicate(self):
        service_request = self.draft()
        key = uuid.uuid4()
        first = submit_request(
            actor=self.author,
            service_request=service_request,
            idempotency_key=key,
        )
        second = submit_request(
            actor=self.author,
            service_request=service_request,
            idempotency_key=key,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            service_request.transitions.filter(
                to_state=ServiceRequest.State.SUBMITTED
            ).count(),
            1,
        )

    def test_state_change_rolls_back_when_history_write_fails(self):
        service_request = self.draft()

        with patch(
            "apps.requests.services.RequestTransition.objects.create",
            side_effect=DatabaseError("history unavailable"),
        ), self.assertRaises(DatabaseError):
            submit_request(
                actor=self.author,
                service_request=service_request,
                idempotency_key=uuid.uuid4(),
            )

        service_request.refresh_from_db()
        self.assertEqual(service_request.state, ServiceRequest.State.DRAFT)

    def test_direct_state_change_and_history_mutation_are_rejected(self):
        service_request = self.draft()
        transition = service_request.transitions.get()
        service_request.state = ServiceRequest.State.APPROVED

        with self.assertRaises(RequestMutationError):
            service_request.save()
        with self.assertRaises(RequestMutationError):
            ServiceRequest.objects.filter(pk=service_request.pk).update(
                state=ServiceRequest.State.APPROVED
            )
        with self.assertRaises(RequestMutationError):
            transition.delete()
        with self.assertRaises(RequestMutationError):
            RequestTransition.objects.filter(pk=transition.pk).update(comment="x")

    def test_invalid_transition_order_is_rejected(self):
        service_request = self.draft()

        with self.assertRaises(ValidationError):
            begin_execution(
                actor=self.operator,
                service_request=service_request,
                idempotency_key=uuid.uuid4(),
            )
