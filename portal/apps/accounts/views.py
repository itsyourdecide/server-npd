from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponseNotAllowed
from django.shortcuts import render


class PortalLoginView(LoginView):
    template_name = "registration/login.html"
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
    return render(
        request,
        "accounts/dashboard.html",
        {"profile": getattr(request.user, "profile", None)},
    )
