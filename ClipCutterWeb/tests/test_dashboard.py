from unittest.mock import patch
import test_admin_security

import unittest
from app.modules.dashboard.system_metrics import _vps_dashboard_metrics

class HostMetricsTests(unittest.TestCase):
    def test_os_name_preserves_n_and_stops_at_newline(self):
        for value in ('PRETTY_NAME="Ubuntu Linux 24.04"\nNAME=Ubuntu\n',
                      'PRETTY_NAME=Ubuntu Linux 24.04\nNAME=Ubuntu\n'):
            readings = {
                "/proc/meminfo": "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n",
                "/proc/uptime": "12345 0\n",
                "/etc/os-release": value,
            }
            with self.subTest(value=value), patch(
                "app.modules.dashboard.system_metrics.Path.read_text",
                autospec=True, side_effect=lambda path, **kw: readings[str(path)]
            ), patch("app.modules.dashboard.system_metrics._read_cpu_percent", return_value=3):
                self.assertEqual(_vps_dashboard_metrics()["os"], "Ubuntu Linux 24.04")

class DashboardTests(unittest.TestCase):
    setUp = test_admin_security.LocalAdminSecurityTests.setUp
    _form = test_admin_security.LocalAdminSecurityTests._form
    _login = test_admin_security.LocalAdminSecurityTests._login
    _signed_in = test_admin_security.LocalAdminSecurityTests._signed_in

    def test_dashboard_requires_login_and_reports_unavailable(self):
        self.assertEqual(self.client.get("/api/v1/dashboard/system").status_code, 401)
        self._signed_in()
        with patch("app.modules.dashboard.routes.system_dashboard_snapshot", side_effect=RuntimeError("probe")):
            self.assertEqual(self.client.get("/api/v1/dashboard/system").status_code, 503)
        fixture = {"ok": True, "vps": {"cpu_percent": 3}, "services": []}
        with patch("app.modules.dashboard.routes.system_dashboard_snapshot", return_value=fixture):
            self.assertEqual(self.client.get("/api/v1/dashboard/system").json(), fixture)

    def test_two_studio_tabs(self):
        self._signed_in()
        for path in ("/studio/extractor", "/studio/analyzer"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Clip Extractor", page.text)
            self.assertIn("Person Analyzer", page.text)
            self.assertIn("Save request", page.text)
        self.assertEqual(self.client.get("/concat/production").status_code, 404)
