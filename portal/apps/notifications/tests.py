import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import SystemRole
from apps.projects.services import create_project
from apps.requests.models import RequestTransition, ServiceRequest
from apps.requests.services import begin_review, create_request_draft, submit_request

from .models import Notification
from .services import mark_notification_read, notify_request_transition


class NotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="test")
        self.author = User.objects.create_user(username="author")
        self.other = User.objects.create_user(username="other")
        self.reviewer = User.objects.create_user(username="reviewer")
        self.reviewer.groups.add(Group.objects.get(name=SystemRole.REVIEWER.value))
        self.project = create_project(
            actor=self.admin,
            owner=self.author,
            name="Research project",
        )
        self.service_request = create_request_draft(
            actor=self.author,
            project=self.project,
            kind=ServiceRequest.Kind.RESOURCE,
            title="Additional memory",
            idempotency_key=uuid.uuid4(),
        )

    def test_authors_own_transition_does_not_notify_them(self):
        submit_request(
            actor=self.author,
            service_request=self.service_request,
            idempotency_key=uuid.uuid4(),
        )

        self.assertFalse(Notification.objects.exists())

    def test_reviewer_transition_notifies_author_once(self):
        submitted = submit_request(
            actor=self.author,
            service_request=self.service_request,
            idempotency_key=uuid.uuid4(),
        )
        reviewed = begin_review(
            actor=self.reviewer,
            service_request=submitted,
            idempotency_key=uuid.uuid4(),
        )
        transition = RequestTransition.objects.filter(
            request=reviewed,
            to_state=ServiceRequest.State.UNDER_REVIEW,
        ).get()

        first = Notification.objects.get()
        second = notify_request_transition(reviewed, transition)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(first.recipient, self.author)
        self.assertEqual(first.target_id, str(self.service_request.pk))

    def test_only_recipient_can_mark_notification_read(self):
        notification = Notification.objects.create(
            recipient=self.author,
            event=Notification.Event.REQUEST_STATE_CHANGED,
            title="Changed",
            message="Changed",
            target_type="service_request",
            target_id=str(self.service_request.pk),
            deduplication_key="test-notification",
        )

        with self.assertRaises(PermissionDenied):
            mark_notification_read(actor=self.other, notification=notification)

        notification = mark_notification_read(
            actor=self.author,
            notification=notification,
        )
        self.assertIsNotNone(notification.read_at)

    def test_list_shows_only_current_users_notifications(self):
        own_notification = Notification.objects.create(
            recipient=self.author,
            event=Notification.Event.REQUEST_STATE_CHANGED,
            title="Visible notification",
            message="Visible",
            target_type="service_request",
            target_id=str(self.service_request.pk),
            deduplication_key="visible",
        )
        Notification.objects.create(
            recipient=self.other,
            event=Notification.Event.REQUEST_STATE_CHANGED,
            title="Hidden notification",
            message="Hidden",
            target_type="service_request",
            target_id=str(self.service_request.pk),
            deduplication_key="hidden",
        )
        self.client.force_login(self.author)

        response = self.client.get(reverse("notifications:list"))

        self.assertContains(response, own_notification.title)
        self.assertNotContains(response, "Hidden notification")

    def test_recipient_marks_notification_read_through_post(self):
        notification = Notification.objects.create(
            recipient=self.author,
            event=Notification.Event.REQUEST_STATE_CHANGED,
            title="Changed",
            message="Changed",
            target_type="service_request",
            target_id=str(self.service_request.pk),
            deduplication_key="mark-read",
        )
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("notifications:mark-read", args=[notification.pk])
        )

        self.assertRedirects(response, reverse("notifications:list"))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_dashboard_shows_unread_notification_count(self):
        Notification.objects.create(
            recipient=self.author,
            event=Notification.Event.REQUEST_STATE_CHANGED,
            title="Changed",
            message="Changed",
            target_type="service_request",
            target_id=str(self.service_request.pk),
            deduplication_key="dashboard-count",
        )
        self.client.force_login(self.author)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Notifications (1 new)")
