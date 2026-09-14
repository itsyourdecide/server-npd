from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def liveness(request):
    """Report that the Django process can serve HTTP requests."""

    return JsonResponse({"status": "ok"})


@never_cache
def readiness(request):
    """Report whether required dependencies are ready for traffic."""

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {"status": "unavailable", "checks": {"database": "unavailable"}},
            status=503,
        )

    return JsonResponse({"status": "ok", "checks": {"database": "ok"}})


@never_cache
def build_info(request):
    """Expose non-secret build identifiers for diagnostics."""

    return JsonResponse(
        {
            "version": settings.PORTAL_BUILD_VERSION,
            "commit": settings.PORTAL_BUILD_COMMIT,
        }
    )
