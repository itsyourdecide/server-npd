import uuid

from django.conf import settings
from django.db import models


class AuditEventImmutableError(TypeError):
    """Raised when application code tries to modify audit history."""


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditEventImmutableError("Audit events cannot be updated")

    def delete(self):
        raise AuditEventImmutableError("Audit events cannot be deleted")


class AuditEvent(models.Model):
    """Append-only record of a security or domain event."""

    class Category(models.TextChoices):
        AUTHENTICATION = "authentication", "Authentication"
        PROJECT = "project", "Project"
        REQUEST = "request", "Request"
        OPERATION = "operation", "Operation"
        SYSTEM = "system", "System"

    class AuthenticationMethod(models.TextChoices):
        LOCAL = "local", "Local account"
        OIDC = "oidc", "OpenID Connect"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=32, choices=Category)
    action = models.CharField(max_length=64)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor_label = models.CharField(max_length=150, blank=True)
    authentication_method = models.CharField(
        max_length=16,
        choices=AuthenticationMethod,
        blank=True,
    )
    request_id = models.UUIDField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=128, blank=True)
    details = models.JSONField(default=dict, blank=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["category", "action", "created_at"],
                name="audit_category_action_time_idx",
            ),
            models.Index(
                fields=["actor", "created_at"],
                name="audit_actor_time_idx",
            ),
            models.Index(fields=["request_id"], name="audit_request_id_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditEventImmutableError("Audit events cannot be updated")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditEventImmutableError("Audit events cannot be deleted")

    def __str__(self) -> str:
        return f"{self.created_at}: {self.action}"
