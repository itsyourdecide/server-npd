from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class PortalAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Username")
        self.fields["password"].label = _("Password")
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": _("Username"),
                "autofocus": True,
            }
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "placeholder": _("Password")}
        )
