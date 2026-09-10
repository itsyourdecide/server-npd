import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .identity import InvalidOIDCClaims, VerifiedOIDCClaims, sync_user_from_oidc
from .models import UserProfile
from .oidc import PortalOIDCAuthenticationBackend
from .roles import (
    SystemRole,
    can_assign_system_roles,
    can_execute_operations,
    can_review_requests,
)


class UserProfileModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice")

    def make_profile(self, **overrides):
        values = {
            "user": self.user,
            "oidc_issuer": "https://identity.example.edu",
            "oidc_subject": "oidc-subject-alice",
        }
        values.update(overrides)
        return UserProfile.objects.create(**values)

    def test_profile_has_public_uuid_and_safe_initial_state(self):
        profile = self.make_profile()

        self.assertIsInstance(profile.id, uuid.UUID)
        self.assertEqual(
            profile.provisioning_status,
            UserProfile.ProvisioningStatus.NOT_REQUESTED,
        )
        self.assertIsNone(profile.cluster_login)
        self.assertIsNone(profile.cluster_uid)

    def test_oidc_issuer_and_subject_pair_is_unique(self):
        self.make_profile()
        second_user = get_user_model().objects.create_user(username="bob")

        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.create(
                user=second_user,
                oidc_issuer="https://identity.example.edu",
                oidc_subject="oidc-subject-alice",
            )

    def test_cluster_login_uses_provisioning_script_format(self):
        profile = UserProfile(
            user=self.user,
            oidc_issuer="https://identity.example.edu",
            oidc_subject="oidc-subject-alice",
            cluster_login="Alice.Invalid",
            cluster_uid=20_000,
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_cluster_uid_must_be_in_allocated_range(self):
        profile = UserProfile(
            user=self.user,
            oidc_issuer="https://identity.example.edu",
            oidc_subject="oidc-subject-alice",
            cluster_login="alice",
            cluster_uid=19_999,
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_cluster_login_and_uid_are_stored_together(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_profile(cluster_login="alice")


class OIDCIdentityTests(TestCase):
    def claims(self, **overrides):
        values = {
            "issuer": "https://identity.example.edu",
            "subject": "subject-123",
            "email": "alice@example.edu",
            "given_name": "Alice",
            "family_name": "Example",
        }
        values.update(overrides)
        return VerifiedOIDCClaims(**values)

    def test_first_login_creates_user_and_profile(self):
        user = sync_user_from_oidc(self.claims())

        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "alice@example.edu")
        self.assertEqual(user.profile.oidc_issuer, "https://identity.example.edu")
        self.assertEqual(user.profile.oidc_subject, "subject-123")

    def test_repeated_login_updates_mutable_claims_without_changing_identity(self):
        first_user = sync_user_from_oidc(self.claims())
        second_user = sync_user_from_oidc(
            self.claims(email="alice.renamed@example.edu", given_name="Alicia")
        )

        self.assertEqual(second_user.pk, first_user.pk)
        self.assertEqual(second_user.username, first_user.username)
        self.assertEqual(second_user.email, "alice.renamed@example.edu")
        self.assertEqual(second_user.first_name, "Alicia")
        self.assertEqual(UserProfile.objects.count(), 1)

    def test_same_subject_from_different_issuer_is_a_different_identity(self):
        first_user = sync_user_from_oidc(self.claims())
        second_user = sync_user_from_oidc(
            self.claims(issuer="https://other-identity.example.edu")
        )

        self.assertNotEqual(second_user.pk, first_user.pk)
        self.assertEqual(UserProfile.objects.count(), 2)

    def test_claim_mapping_requires_subject(self):
        with self.assertRaises(InvalidOIDCClaims):
            VerifiedOIDCClaims.from_mapping(
                issuer="https://identity.example.edu",
                claims={},
            )


@override_settings(
    OIDC_OP_TOKEN_ENDPOINT="https://identity.example.edu/token",
    OIDC_OP_USER_ENDPOINT="https://identity.example.edu/userinfo",
    OIDC_RP_CLIENT_ID="portal-client",
    OIDC_RP_CLIENT_SECRET="test-secret-at-least-32-bytes-long",
    OIDC_RP_SIGN_ALGO="HS256",
    OIDC_OP_ISSUER="https://identity.example.edu",
)
class PortalOIDCBackendTests(TestCase):
    def token(self, **overrides):
        now = datetime.now(UTC)
        payload = {
            "iss": "https://identity.example.edu",
            "sub": "subject-123",
            "aud": "portal-client",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        payload.update(overrides)
        return jwt.encode(
            payload,
            "test-secret-at-least-32-bytes-long",
            algorithm="HS256",
        )

    def test_token_validation_checks_audience_and_issuer(self):
        backend = PortalOIDCAuthenticationBackend()

        key = "test-secret-at-least-32-bytes-long"
        payload = backend._verify_jws(self.token(), key)

        self.assertEqual(payload["sub"], "subject-123")

        with self.assertRaises(SuspiciousOperation):
            backend._verify_jws(self.token(aud="other-client"), key)
        with self.assertRaises(SuspiciousOperation):
            backend._verify_jws(
                self.token(iss="https://attacker.example"),
                key,
            )

    def test_userinfo_subject_must_match_verified_id_token(self):
        backend = PortalOIDCAuthenticationBackend()
        backend.get_userinfo = Mock(return_value={"sub": "different-subject"})

        with self.assertRaises(SuspiciousOperation):
            backend.get_or_create_user(
                "access-token",
                "id-token",
                {
                    "iss": "https://identity.example.edu",
                    "sub": "subject-123",
                },
            )


class LocalAuthenticationTests(TestCase):
    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("dashboard")}',
        )

    def test_local_login_form_is_available_in_test_environment(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_authenticated_user_can_open_dashboard(self):
        user = get_user_model().objects.create_user(username="alice")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Signed in as alice")


class SystemRoleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice")

    def test_system_role_groups_are_created_by_migration(self):
        self.assertTrue(Group.objects.filter(name=SystemRole.REVIEWER.value).exists())
        self.assertTrue(Group.objects.filter(name=SystemRole.OPERATOR.value).exists())

    def test_anonymous_and_regular_users_have_no_privileged_actions(self):
        for user in (AnonymousUser(), self.user):
            self.assertFalse(can_review_requests(user))
            self.assertFalse(can_execute_operations(user))
            self.assertFalse(can_assign_system_roles(user))

    def test_reviewer_can_review_but_cannot_execute_or_assign_roles(self):
        self.user.groups.add(Group.objects.get(name=SystemRole.REVIEWER.value))

        self.assertTrue(can_review_requests(self.user))
        self.assertFalse(can_execute_operations(self.user))
        self.assertFalse(can_assign_system_roles(self.user))

    def test_operator_can_execute_but_review_is_denied_by_default(self):
        self.user.groups.add(Group.objects.get(name=SystemRole.OPERATOR.value))

        self.assertTrue(can_execute_operations(self.user))
        self.assertFalse(can_review_requests(self.user))
        self.assertFalse(can_assign_system_roles(self.user))

    def test_active_superuser_has_all_system_capabilities(self):
        admin = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.edu",
            password="not-used-outside-test",
        )

        self.assertTrue(can_review_requests(admin))
        self.assertTrue(can_execute_operations(admin))
        self.assertTrue(can_assign_system_roles(admin))

    def test_inactive_superuser_has_no_system_capabilities(self):
        admin = get_user_model().objects.create_superuser(
            username="disabled-admin",
            email="admin@example.edu",
            password="not-used-outside-test",
        )
        admin.is_active = False
        admin.save(update_fields=["is_active"])

        self.assertFalse(can_review_requests(admin))
        self.assertFalse(can_execute_operations(admin))
        self.assertFalse(can_assign_system_roles(admin))

# Create your tests here.
