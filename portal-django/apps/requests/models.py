import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _

from apps.projects.models import Project


class RequestMutationError(ValidationError):
    """Raised when request history is changed outside the domain service."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RequestMutationError("History records cannot be updated")

    def delete(self):
        raise RequestMutationError("History records cannot be deleted")


class ServiceRequestQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RequestMutationError(
            "Service requests must be updated through the domain service"
        )

    def delete(self):
        raise RequestMutationError("Service requests cannot be deleted")


class ServiceRequest(models.Model):
    class Kind(models.TextChoices):
        CLUSTER_ACCESS = "cluster_access", "Cluster access"
        RESOURCE = "resource", "Resource"

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXECUTING = "executing", "Executing"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creation_key = models.UUIDField(unique=True, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    kind = models.CharField(max_length=32, choices=Kind)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    state = models.CharField(
        max_length=32,
        choices=State,
        default=State.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ServiceRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["state", "created_at"],
                name="requests_state_time_idx",
            ),
            models.Index(
                fields=["author", "created_at"],
                name="requests_author_time_idx",
            ),
        ]

    @property
    def state_color(self):
        return {
            self.State.DRAFT: "secondary",
            self.State.SUBMITTED: "azure",
            self.State.UNDER_REVIEW: "yellow",
            self.State.APPROVED: "green",
            self.State.REJECTED: "red",
            self.State.EXECUTING: "orange",
            self.State.ACTIVE: "green",
            self.State.FAILED: "red",
        }.get(self.state, "secondary")

    @property
    def state_label(self):
        return _(self.get_state_display())

    @property
    def kind_label(self):
        return _(self.get_kind_display())

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = ServiceRequest.objects.only(
                "author_id",
                "project_id",
                "kind",
                "creation_key",
                "state",
            ).get(pk=self.pk)
            immutable_fields = ("author_id", "project_id", "kind", "creation_key")
            if any(getattr(self, field) != getattr(original, field) for field in immutable_fields):
                raise RequestMutationError(
                    "Author, project, kind and creation key are immutable"
                )
            if self.state != original.state and not getattr(
                self, "_allow_state_transition", False
            ):
                raise RequestMutationError(
                    "Request state can only be changed by the transition service"
                )
        try:
            return super().save(*args, **kwargs)
        finally:
            if hasattr(self, "_allow_state_transition"):
                del self._allow_state_transition

    def delete(self, *args, **kwargs):
        raise RequestMutationError("Service requests cannot be deleted")

    def __str__(self) -> str:
        return f"{self.title} ({self.get_state_display()})"


class RequestTransition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.PROTECT,
        related_name="transitions",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="request_transitions",
    )
    from_state = models.CharField(max_length=32, blank=True)
    to_state = models.CharField(max_length=32, choices=ServiceRequest.State)
    comment = models.TextField(blank=True)
    idempotency_key = models.UUIDField(unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["request", "created_at"],
                name="requests_transition_time_idx",
            ),
        ]

    @property
    def from_state_label(self):
        if not self.from_state:
            return _("Created")
        return _(ServiceRequest.State(self.from_state).label)

    @property
    def to_state_label(self):
        return _(ServiceRequest.State(self.to_state).label)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RequestMutationError("Request transitions cannot be updated")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RequestMutationError("Request transitions cannot be deleted")

    def __str__(self) -> str:
        return f"{self.from_state or 'created'} -> {self.to_state}"


class Approval(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.PROTECT,
        related_name="approvals",
    )
    transition = models.OneToOneField(
        RequestTransition,
        on_delete=models.PROTECT,
        related_name="approval",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="request_approvals",
    )
    decision = models.CharField(max_length=16, choices=Decision)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RequestMutationError("Approvals cannot be updated")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RequestMutationError("Approvals cannot be deleted")

    def __str__(self) -> str:
        return f"{self.get_decision_display()} by {self.reviewer.get_username()}"
