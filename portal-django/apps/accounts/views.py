from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponseNotAllowed
from django.shortcuts import render

from apps.projects.authorization import visible_projects_for
from apps.requests.models import ServiceRequest

from .forms import PortalAuthenticationForm


class PortalLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = PortalAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "local_auth_enabled": settings.LOCAL_AUTH_ENABLED,
                "oidc_enabled": settings.OIDC_ENABLED,
                "oidc_provider_name": settings.OIDC_PROVIDER_NAME,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        if not settings.LOCAL_AUTH_ENABLED:
            return HttpResponseNotAllowed(["GET"])
        return super().post(request, *args, **kwargs)


@login_required
def dashboard(request):
    own_requests = ServiceRequest.objects.filter(author=request.user)
    return render(
        request,
        "accounts/dashboard.html",
        {
            "profile": getattr(request.user, "profile", None),
            "project_count": visible_projects_for(request.user).count(),
            "request_count": own_requests.count(),
            "open_request_count": own_requests.exclude(
                state__in=(
                    ServiceRequest.State.ACTIVE,
                    ServiceRequest.State.FAILED,
                    ServiceRequest.State.REJECTED,
                )
            ).count(),
        },
    )
