import uuid

from django import forms

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
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    kind = forms.ChoiceField(choices=ServiceRequest.Kind)
    title = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = visible_projects_for(user).filter(
            state=Project.State.ACTIVE
        )


class TransitionForm(IdempotentForm):
    pass


class DecisionForm(IdempotentForm):
    decision = forms.ChoiceField(choices=Approval.Decision)
    comment = forms.CharField(widget=forms.Textarea)


class ExecutionResultForm(IdempotentForm):
    outcome = forms.ChoiceField(
        choices=(
            (ServiceRequest.State.ACTIVE, "Completed successfully"),
            (ServiceRequest.State.FAILED, "Failed"),
        )
    )
    comment = forms.CharField(widget=forms.Textarea)
