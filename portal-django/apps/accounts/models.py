import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


CLUSTER_UID_MIN = 20_000
CLUSTER_UID_MAX = 29_999

cluster_login_validator = RegexValidator(
    regex=r"^[a-z_][a-z0-9_-]{0,31}$",
    message="Use a lowercase Linux login, for example: denis",
)


class UserProfile(models.Model):
    """Portal user data and its optional provisioned cluster identity."""

    class ProvisioningStatus(models.TextChoices):
        NOT_REQUESTED = "not_requested", "Not requested"
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"
        DISABLED = "disabled", "Disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    cluster_login = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        unique=True,
        validators=[cluster_login_validator],
    )
    cluster_uid = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        validators=[
            MinValueValidator(CLUSTER_UID_MIN),
            MaxValueValidator(CLUSTER_UID_MAX),
        ],
    )
    provisioning_status = models.CharField(
        max_length=20,
        choices=ProvisioningStatus,
        default=ProvisioningStatus.NOT_REQUESTED,
    )
    provisioned_at = models.DateTimeField(null=True, blank=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(cluster_uid__isnull=True)
                    | models.Q(
                        cluster_uid__gte=CLUSTER_UID_MIN,
                        cluster_uid__lte=CLUSTER_UID_MAX,
                    )
                ),
                name="accounts_profile_cluster_uid_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(cluster_login__isnull=True, cluster_uid__isnull=True)
                    | models.Q(
                        cluster_login__isnull=False,
                        cluster_uid__isnull=False,
                    )
                ),
                name="accounts_profile_cluster_identity_pair",
            ),
        ]

    def __str__(self) -> str:
        return self.user.get_username()


class ExternalIdentity(models.Model):
    """An OIDC identity owned by one portal user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_identities",
    )
    provider = models.SlugField(max_length=50)
    issuer = models.URLField(max_length=512)
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "subject"],
                name="accounts_identity_unique_issuer_subject",
            ),
        ]
        indexes = [models.Index(fields=["provider"], name="accounts_identity_provider_idx")]

    def __str__(self) -> str:
        return f"{self.provider}: {self.user.get_username()}"
