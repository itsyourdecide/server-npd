import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import UserProfile


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

# Create your tests here.
