import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import can_execute_operations, can_review_requests
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.projects.authorization import can_view_project
from apps.projects.models import Project

from .models import Approval, RequestTransition, ServiceRequest


def _active_user(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def _uuid(value, field_name):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field_name: "A valid UUID is required"}) from exc


def _existing_creation(*, key, actor, project, kind, title, description):
    existing = ServiceRequest.objects.filter(creation_key=key).first()
    if existing is None:
        return None
    expected = (
        actor.pk,
        project.pk,
        kind,
        title,
        description,
    )
    actual = (
        existing.author_id,
        existing.project_id,
        existing.kind,
        existing.title,
        existing.description,
    )
    if actual != expected:
        raise ValidationError("Creation key was already used for another request")
    return existing


def create_request_draft(
    *,
    actor,
    project,
    kind,
    title,
    description="",
    idempotency_key,
    http_request=None,
):
    if not _active_user(actor):
        raise PermissionDenied("An active user is required")
    if project.state != Project.State.ACTIVE or not can_view_project(actor, project):
        raise PermissionDenied("The project is not available to this user")

    key = _uuid(idempotency_key, "idempotency_key")
    clean_title = title.strip()
    clean_description = description.strip()
    existing = _existing_creation(
        key=key,
        actor=actor,
        project=project,
        kind=kind,
        title=clean_title,
        description=clean_description,
    )
    if existing is not None:
        return existing

    try:
        with transaction.atomic():
            service_request = ServiceRequest(
                creation_key=key,
                author=actor,
                project=project,
                kind=kind,
                title=clean_title,
                description=clean_description,
            )
            service_request.full_clean()
            service_request.save()
            transition = RequestTransition.objects.create(
                request=service_request,
                actor=actor,
                from_state="",
                to_state=ServiceRequest.State.DRAFT,
                idempotency_key=key,
            )
            record_event(
                category=AuditEvent.Category.REQUEST,
                action="request.created",
                actor=actor,
                request=http_request,
                target_type="service_request",
                target_id=service_request.pk,
                details={"kind": kind, "transition_id": str(transition.pk)},
            )
            return service_request
    except IntegrityError:
        existing = _existing_creation(
            key=key,
            actor=actor,
            project=project,
            kind=kind,
            title=clean_title,
            description=clean_description,
        )
        if existing is None:
            raise
        return existing


def _existing_transition(*, key, request_id, actor, to_state):
    transition = RequestTransition.objects.select_related("request").filter(
        idempotency_key=key
    ).first()
    if transition is None:
        return None
    if (
        transition.request_id != request_id
        or transition.actor_id != actor.pk
        or transition.to_state != to_state
    ):
        raise ValidationError("Idempotency key was already used for another action")
    return transition.request


def _change_state(
    *,
    actor,
    service_request,
    expected_state,
    target_state,
    idempotency_key,
    authorize,
    comment="",
    decision="",
    require_comment=False,
    http_request=None,
):
    if not _active_user(actor):
        raise PermissionDenied("An active user is required")

    key = _uuid(idempotency_key, "idempotency_key")
    clean_comment = comment.strip()
    if require_comment and not clean_comment:
        raise ValidationError({"comment": "A comment is required"})

    existing = _existing_transition(
        key=key,
        request_id=service_request.pk,
        actor=actor,
        to_state=target_state,
    )
    if existing is not None:
        return existing

    with transaction.atomic():
        locked = ServiceRequest.objects.select_for_update().select_related(
            "project"
        ).get(pk=service_request.pk)
        existing = _existing_transition(
            key=key,
            request_id=locked.pk,
            actor=actor,
            to_state=target_state,
        )
        if existing is not None:
            return existing
        authorize(actor, locked)
        if locked.state != expected_state:
            raise ValidationError(
                f"Request must be in {expected_state!r}, not {locked.state!r}"
            )

        locked.state = target_state
        locked.updated_at = timezone.now()
        locked._allow_state_transition = True
        locked.save(update_fields=["state", "updated_at"])
        transition = RequestTransition.objects.create(
            request=locked,
            actor=actor,
            from_state=expected_state,
            to_state=target_state,
            comment=clean_comment,
            idempotency_key=key,
        )
        if decision:
            Approval.objects.create(
                request=locked,
                transition=transition,
                reviewer=actor,
                decision=decision,
                comment=clean_comment,
            )
        record_event(
            category=AuditEvent.Category.REQUEST,
            action="request.state_changed",
            actor=actor,
            request=http_request,
            target_type="service_request",
            target_id=locked.pk,
            details={
                "from_state": expected_state,
                "to_state": target_state,
                "transition_id": str(transition.pk),
            },
        )
        return locked


def submit_request(*, actor, service_request, idempotency_key, http_request=None):
    def authorize(user, locked):
        if locked.author_id != user.pk:
            raise PermissionDenied("Only the author can submit this request")
        if locked.project.state != Project.State.ACTIVE:
            raise ValidationError("Requests cannot be submitted for an archived project")

    return _change_state(
        actor=actor,
        service_request=service_request,
        expected_state=ServiceRequest.State.DRAFT,
        target_state=ServiceRequest.State.SUBMITTED,
        idempotency_key=idempotency_key,
        authorize=authorize,
        http_request=http_request,
    )


def begin_review(*, actor, service_request, idempotency_key, http_request=None):
    def authorize(user, locked):
        if not can_review_requests(user):
            raise PermissionDenied("Reviewer role is required")
        if locked.author_id == user.pk:
            raise PermissionDenied("A requester cannot review their own request")

    return _change_state(
        actor=actor,
        service_request=service_request,
        expected_state=ServiceRequest.State.SUBMITTED,
        target_state=ServiceRequest.State.UNDER_REVIEW,
        idempotency_key=idempotency_key,
        authorize=authorize,
        http_request=http_request,
    )


def decide_request(
    *,
    actor,
    service_request,
    decision,
    comment,
    idempotency_key,
    http_request=None,
):
    if decision not in Approval.Decision.values:
        raise ValidationError({"decision": "Unsupported decision"})

    def authorize(user, locked):
        if not can_review_requests(user):
            raise PermissionDenied("Reviewer role is required")
        if locked.author_id == user.pk:
            raise PermissionDenied("A requester cannot approve their own request")

    return _change_state(
        actor=actor,
        service_request=service_request,
        expected_state=ServiceRequest.State.UNDER_REVIEW,
        target_state=decision,
        idempotency_key=idempotency_key,
        authorize=authorize,
        comment=comment,
        decision=decision,
        require_comment=True,
        http_request=http_request,
    )


def begin_execution(*, actor, service_request, idempotency_key, http_request=None):
    def authorize(user, locked):
        if not can_execute_operations(user):
            raise PermissionDenied("Operator role is required")

    return _change_state(
        actor=actor,
        service_request=service_request,
        expected_state=ServiceRequest.State.APPROVED,
        target_state=ServiceRequest.State.EXECUTING,
        idempotency_key=idempotency_key,
        authorize=authorize,
        http_request=http_request,
    )


def finish_execution(
    *,
    actor,
    service_request,
    outcome,
    comment,
    idempotency_key,
    http_request=None,
):
    if outcome not in (ServiceRequest.State.ACTIVE, ServiceRequest.State.FAILED):
        raise ValidationError({"outcome": "Unsupported execution outcome"})

    def authorize(user, locked):
        if not can_execute_operations(user):
            raise PermissionDenied("Operator role is required")

    return _change_state(
        actor=actor,
        service_request=service_request,
        expected_state=ServiceRequest.State.EXECUTING,
        target_state=outcome,
        idempotency_key=idempotency_key,
        authorize=authorize,
        comment=comment,
        require_comment=True,
        http_request=http_request,
    )
