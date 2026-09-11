from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.roles import can_execute_operations, can_review_requests

from .authorization import visible_requests_for
from .forms import (
    DecisionForm,
    ExecutionResultForm,
    RequestCreateForm,
    TransitionForm,
)
from .models import ServiceRequest
from .services import (
    begin_execution,
    begin_review,
    create_request_draft,
    decide_request,
    finish_execution,
    submit_request,
)


def _request_for(user, request_id):
    return get_object_or_404(
        visible_requests_for(user).select_related("author", "project"),
        pk=request_id,
    )


def _detail_context(service_request, user, **forms):
    context = {
        "service_request": service_request,
        "transitions": service_request.transitions.select_related("actor"),
        "can_submit": (
            service_request.author_id == user.pk
            and service_request.state == ServiceRequest.State.DRAFT
        ),
        "can_begin_review": (
            can_review_requests(user)
            and service_request.author_id != user.pk
            and service_request.state == ServiceRequest.State.SUBMITTED
        ),
        "can_decide": (
            can_review_requests(user)
            and service_request.author_id != user.pk
            and service_request.state == ServiceRequest.State.UNDER_REVIEW
        ),
        "can_begin_execution": (
            can_execute_operations(user)
            and service_request.state == ServiceRequest.State.APPROVED
        ),
        "can_finish_execution": (
            can_execute_operations(user)
            and service_request.state == ServiceRequest.State.EXECUTING
        ),
        "submit_form": TransitionForm(),
        "review_form": TransitionForm(),
        "decision_form": DecisionForm(),
        "execution_form": TransitionForm(),
        "result_form": ExecutionResultForm(),
    }
    context.update(forms)
    return context


def _render_detail(request, service_request, **forms):
    service_request.refresh_from_db()
    return render(
        request,
        "requests/detail.html",
        _detail_context(service_request, request.user, **forms),
    )


@login_required
def request_list(request):
    own_requests = ServiceRequest.objects.filter(author=request.user).select_related(
        "project"
    )
    review_queue = ServiceRequest.objects.none()
    operator_queue = ServiceRequest.objects.none()
    if can_review_requests(request.user):
        review_queue = ServiceRequest.objects.filter(
            state__in=(
                ServiceRequest.State.SUBMITTED,
                ServiceRequest.State.UNDER_REVIEW,
            )
        ).select_related("author", "project")
    if can_execute_operations(request.user):
        operator_queue = ServiceRequest.objects.filter(
            state__in=(
                ServiceRequest.State.APPROVED,
                ServiceRequest.State.EXECUTING,
            )
        ).select_related("author", "project")
    return render(
        request,
        "requests/list.html",
        {
            "own_requests": own_requests,
            "review_queue": review_queue,
            "operator_queue": operator_queue,
        },
    )


@login_required
def request_create(request):
    form = RequestCreateForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            service_request = create_request_draft(
                actor=request.user,
                project=form.cleaned_data["project"],
                kind=form.cleaned_data["kind"],
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                idempotency_key=form.cleaned_data["idempotency_key"],
                http_request=request,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("requests:detail", request_id=service_request.pk)
    return render(request, "requests/create.html", {"form": form})


@login_required
def request_detail(request, request_id):
    service_request = _request_for(request.user, request_id)
    return _render_detail(request, service_request)


def _valid_transition_form(request, service_request, form, callback, **kwargs):
    if form.is_valid():
        try:
            callback(
                actor=request.user,
                service_request=service_request,
                idempotency_key=form.cleaned_data["idempotency_key"],
                http_request=request,
                **kwargs,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("requests:detail", request_id=service_request.pk)
    return None


@login_required
@require_POST
def request_submit(request, request_id):
    service_request = _request_for(request.user, request_id)
    form = TransitionForm(request.POST)
    response = _valid_transition_form(
        request, service_request, form, submit_request
    )
    return response or _render_detail(request, service_request, submit_form=form)


@login_required
@require_POST
def request_begin_review(request, request_id):
    service_request = _request_for(request.user, request_id)
    form = TransitionForm(request.POST)
    response = _valid_transition_form(request, service_request, form, begin_review)
    return response or _render_detail(request, service_request, review_form=form)


@login_required
@require_POST
def request_decide(request, request_id):
    service_request = _request_for(request.user, request_id)
    form = DecisionForm(request.POST)
    response = None
    if form.is_valid():
        response = _valid_transition_form(
            request,
            service_request,
            form,
            decide_request,
            decision=form.cleaned_data["decision"],
            comment=form.cleaned_data["comment"],
        )
    return response or _render_detail(request, service_request, decision_form=form)


@login_required
@require_POST
def request_begin_execution(request, request_id):
    service_request = _request_for(request.user, request_id)
    form = TransitionForm(request.POST)
    response = _valid_transition_form(
        request, service_request, form, begin_execution
    )
    return response or _render_detail(request, service_request, execution_form=form)


@login_required
@require_POST
def request_finish_execution(request, request_id):
    service_request = _request_for(request.user, request_id)
    form = ExecutionResultForm(request.POST)
    response = None
    if form.is_valid():
        response = _valid_transition_form(
            request,
            service_request,
            form,
            finish_execution,
            outcome=form.cleaned_data["outcome"],
            comment=form.cleaned_data["comment"],
        )
    return response or _render_detail(request, service_request, result_form=form)
