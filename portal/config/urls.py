"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts import views as account_views

from . import health

urlpatterns = [
    path('', account_views.dashboard, name='dashboard'),
    path('health/live', health.liveness, name='health-liveness'),
    path('health/ready', health.readiness, name='health-readiness'),
    path('health/build', health.build_info, name='health-build-info'),
    path('admin/', admin.site.urls),
]

if settings.LOCAL_AUTH_ENABLED:
    urlpatterns.append(path('auth/', include('django.contrib.auth.urls')))

if settings.OIDC_ENABLED:
    urlpatterns.append(path('oidc/', include('mozilla_django_oidc.urls')))
