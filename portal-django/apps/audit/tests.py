import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import AuditEvent, AuditEventImmutableError
from .services import record_event
from .signals import LOGIN_FAILED, LOGIN_SUCCEEDED, LOGOUT


class AuditEventModelTests(TestCase):
    def test_event_cannot_be_changed_or_deleted_through_application_model(self):
        event = AuditEvent.objects.create(
            category=AuditEvent.Category.SYSTEM,
            action="system.test",
        )
        event.action = "system.changed"

        with self.assertRaises(AuditEventImmutableError):
            event.save()
        with self.assertRaises(AuditEventImmutableError):
            event.delete()
        with self.assertRaises(AuditEventImmutableError):
            AuditEvent.objects.filter(pk=event.pk).update(action="system.changed")
        with self.assertRaises(AuditEventImmutableError):
            AuditEvent.objects.filter(pk=event.pk).delete()

    def test_sensitive_detail_names_are_rejected(self):
        with self.assertRaises(ValueError):
            record_event(
                category=AuditEvent.Category.SYSTEM,
                action="system.test",
                details={"access_token": "must-not-be-stored"},
            )


class RequestIDTests(TestCase):
    def test_every_response_has_server_generated_request_id(self):
        response = self.client.get(reverse("health-liveness"))

        self.assertEqual(response.status_code, 200)
        uuid.UUID(response.headers["X-Request-ID"])


class AuthenticationAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alice",
            password="correct-password",
        )

    def test_successful_local_login_is_recorded(self):
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "correct-password"},
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REAL_IP="192.0.2.10",
        )

        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(action=LOGIN_SUCCEEDED)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.actor_label, "alice")
        self.assertEqual(
            event.authentication_method,
            AuditEvent.AuthenticationMethod.LOCAL,
        )
        self.assertEqual(event.source_ip, "192.0.2.10")
        self.assertIsNotNone(event.request_id)

    def test_failed_login_does_not_store_submitted_identifier(self):
        response = self.client.post(
            reverse("login"),
            {"username": "private-name", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(action=LOGIN_FAILED)
        self.assertIsNone(event.actor)
        self.assertEqual(
            event.authentication_method,
            AuditEvent.AuthenticationMethod.LOCAL,
        )
        self.assertNotIn("private-name", str(event.details))
        self.assertEqual(len(event.details["identifier_fingerprint"]), 64)

    def test_logout_is_recorded_with_original_login_method(self):
        self.client.post(
            reverse("login"),
            {"username": "alice", "password": "correct-password"},
        )

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(action=LOGOUT)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(
            event.authentication_method,
            AuditEvent.AuthenticationMethod.LOCAL,
        )

    def test_oidc_login_is_distinguished_from_local_login(self):
        request = RequestFactory().get("/oidc/callback/")
        request.session = self.client.session
        request.audit_request_id = uuid.uuid4()
        self.user.backend = "apps.accounts.oidc.PortalOIDCAuthenticationBackend"

        user_logged_in.send(
            sender=self.user.__class__,
            request=request,
            user=self.user,
        )

        event = AuditEvent.objects.get(action=LOGIN_SUCCEEDED)
        self.assertEqual(
            event.authentication_method,
            AuditEvent.AuthenticationMethod.OIDC,
        )
