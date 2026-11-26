from unittest.mock import patch
import test_admin_security

class DashboardTests(test_admin_security.LocalAdminSecurityTests):
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
            self.assertIn("No jobs are accepted", page.text)
        self.assertEqual(self.client.get("/concat/production").status_code, 404)
