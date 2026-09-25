from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness_reports_process_is_alive(self):
        response = self.client.get(reverse("health-liveness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private")

    def test_readiness_reports_database_is_available(self):
        response = self.client.get(reverse("health-readiness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "checks": {"database": "ok"}},
        )

    @patch("config.health.connection")
    def test_readiness_returns_503_when_database_is_unavailable(self, connection):
        connection.cursor.side_effect = DatabaseError("database unavailable")

        response = self.client.get(reverse("health-readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unavailable", "checks": {"database": "unavailable"}},
        )

    @override_settings(
        PORTAL_BUILD_VERSION="0.1.0",
        PORTAL_BUILD_COMMIT="abc1234",
    )
    def test_build_info_reports_configured_identifiers(self):
        response = self.client.get(reverse("health-build-info"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"version": "0.1.0", "commit": "abc1234"},
        )
