import uuid

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.projects.authorization import visible_projects_for
from apps.projects.models import Project

from .models import Approval, ServiceRequest


class IdempotentForm(forms.Form):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and "idempotency_key" not in self.initial:
            self.initial["idempotency_key"] = uuid.uuid4()
        for field in self.visible_fields():
            css_class = (
                "form-select"
                if isinstance(field.field.widget, forms.Select)
                else "form-control"
            )
            field.field.widget.attrs["class"] = css_class
            if isinstance(field.field.widget, forms.Textarea):
                field.field.widget.attrs.setdefault("rows", 4)


class RequestCreateForm(IdempotentForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        label=_("Project"),
        help_text=_(
            "Select the project that will own the requested access or resources."
        ),
    )
    kind = forms.ChoiceField(
        choices=(
            (ServiceRequest.Kind.CLUSTER_ACCESS, _("Cluster access")),
            (ServiceRequest.Kind.RESOURCE, _("Resource")),
        ),
        label=_("Request type"),
        help_text=_(
            "Choose cluster access for a new account, or resource for an "
            "infrastructure request."
        ),
    )
    title = forms.CharField(
        max_length=200,
        label=_("Title"),
        help_text=_(
            "Use a short, specific name so reviewers can understand the request "
            "at a glance."
        ),
    )
    description = forms.CharField(
        widget=forms.Textarea,
        required=False,
        label=_("Description"),
        help_text=_(
            "Explain what you need, why you need it, and any relevant limits or "
            "deadlines."
        ),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = visible_projects_for(user).filter(
            state=Project.State.ACTIVE
        )


class TransitionForm(IdempotentForm):
    pass


class DecisionForm(IdempotentForm):
    decision = forms.ChoiceField(
        choices=(
            (Approval.Decision.APPROVED, _("Approved")),
            (Approval.Decision.REJECTED, _("Rejected")),
        ),
        label=_("Decision"),
    )
    comment = forms.CharField(
        widget=forms.Textarea,
        label=_("Comment"),
        help_text=_(
            "Record the reason for the decision. This becomes part of the permanent "
            "history."
        ),
    )


class ExecutionResultForm(IdempotentForm):
    outcome = forms.ChoiceField(
        choices=(
            (ServiceRequest.State.ACTIVE, _("Completed successfully")),
            (ServiceRequest.State.FAILED, _("Failed")),
        ),
        label=_("Outcome"),
    )
    comment = forms.CharField(
        widget=forms.Textarea,
        label=_("Comment"),
        help_text=_("Summarize what was done or why execution failed."),
    )
